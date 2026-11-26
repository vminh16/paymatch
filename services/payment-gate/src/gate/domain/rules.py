"""Pure three-layer Payment Gate rule engine ('strictest wins').

Layers (docs/02-architecture/payment-gate.md §2):
  1. Hard rules (non-configurable code)
  2. Platform policy (PlatformLimits 30M/50M ceiling + KillSwitches, fail-closed)
  3. Tenant mandate (versioned, can only tighten limits)

Precedence: DENY > REQUIRE_APPROVAL > ALLOW.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from paymatch_contracts.gate import (
    AllowedMethod,
    Channel,
    Code as GateReasonCode,
    EscrowStatus,
    GateDecision,
    Layer as GateReasonLayer,
)

from gate.domain.channel import is_account_valid_for_channel, resolve_payee_account, select_channel
from gate.domain.hashing import compute_escrow_intent_hash, compute_invoice_intent_hash
from gate.domain.models import (
    ApprovalSnapshot,
    DailyBudgetSnapshot,
    EscrowRecord,
    EvaluationResult,
    GateReasonItem,
    GoodsReceiptSnapshot,
    IndicatorRef,
    InvoiceSnapshot,
    KillSwitchSnapshot,
    MandateSnapshot,
    PolicyState,
    PurchaseOrderSnapshot,
    RiskSignals,
    VendorAccountSnapshot,
    VendorSnapshot,
)

VN_TZ = timezone(timedelta(hours=7))
MAX_SAFE_MONEY_VND = 9_007_199_254_740_991  # 2^53 - 1 per contracts/schemas/money-vnd.schema.json

# Red reason codes from docs/03-agents/agent-runtime.md §5a — never auto-pay or bulk-approvable.
RED_REASON_CODES: frozenset[str] = frozenset(
    {
        "DUPLICATE_INVOICE",
        "PAYEE_CHANGE_REQUEST",
        "PERSONAL_ACCOUNT",
        "HIDDEN_INSTRUCTION",
        "OFFICIAL_FRAUD_LIST",
        "TAX_RISK_LIST",
        "MST_INACTIVE",
        "INVOICE_NOT_FOUND_ON_PORTAL",
    }
)


def compute_effective_auto_pay_limits(
    *,
    policy: PolicyState,
    mandate: MandateSnapshot | None,
) -> tuple[int, int]:
    """Compute effective (per_invoice_vnd, per_day_vnd) = min(platform_ceiling, mandate)."""
    if not policy.available or policy.platform_limits is None:
        return (0, 0)
    plat_inv = policy.platform_limits.auto_pay_per_invoice_vnd
    plat_day = policy.platform_limits.auto_pay_per_day_vnd
    if mandate is None:
        return (plat_inv, plat_day)
    return (
        min(plat_inv, mandate.per_invoice_vnd),
        min(plat_day, mandate.per_day_vnd),
    )


def is_within_time_window(now: datetime, start_hhmm: str, end_hhmm: str) -> bool:
    """Check if Vietnam local time of `now` is within [start_hhmm, end_hhmm]."""
    local_now = now.astimezone(VN_TZ)
    cur_min = local_now.hour * 60 + local_now.minute
    sh, sm = (int(p) for p in start_hhmm.split(":"))
    eh, em = (int(p) for p in end_hhmm.split(":"))
    start_min = sh * 60 + sm
    end_min = eh * 60 + em
    if start_min <= end_min:
        return start_min <= cur_min <= end_min
    return cur_min >= start_min or cur_min <= end_min


def _match_kill_switches(
    *,
    kill_switches: Sequence[KillSwitchSnapshot],
    tenant_id: str,
    indicators: Sequence[IndicatorRef],
    matched_indicator_ids: frozenset[str],
) -> tuple[list[GateReasonItem], list[GateReasonItem]]:
    """Return (hard_blocking_kill_switches, auto_pay_only_kill_switches).

    Per spec:
      - tenant / indicator kill switches block ALL money movement.
      - auto_pay_global blocks ONLY auto-pay (method=mandate); manual approvals remain allowed.
      - bot / tool kill switches are not Gate concerns.
    """
    hard_reasons: list[GateReasonItem] = []
    auto_pay_reasons: list[GateReasonItem] = []
    indicator_hashes = {ind.value_hash.lower() for ind in indicators}
    indicator_pairs = {(ind.kind, ind.value_hash.lower()) for ind in indicators}

    for ks in kill_switches:
        if ks.scope == "tenant" and ks.target_id == tenant_id:
            hard_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.KILL_SWITCH,
                    layer=GateReasonLayer.platform_policy,
                    detail=f"Kill switch phạm vi tenant đang bật ({ks.kill_switch_id}).",
                )
            )
        elif ks.scope == "indicator":
            matched = False
            if ks.target_id and (
                ks.target_id in matched_indicator_ids
                or ks.target_id.lower() in indicator_hashes
            ):
                matched = True
            elif ks.value_hash:
                vh = ks.value_hash.lower()
                if ks.indicator_kind:
                    matched = (ks.indicator_kind, vh) in indicator_pairs
                else:
                    matched = vh in indicator_hashes
            if matched:
                hard_reasons.append(
                    GateReasonItem(
                        code=GateReasonCode.KILL_SWITCH,
                        layer=GateReasonLayer.platform_policy,
                        detail=f"Kill switch phạm vi indicator đang bật ({ks.kill_switch_id}).",
                    )
                )
        elif ks.scope == "auto_pay_global":
            auto_pay_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.KILL_SWITCH,
                    layer=GateReasonLayer.platform_policy,
                    detail=f"Kill switch phạm vi auto_pay_global đang bật ({ks.kill_switch_id}).",
                )
            )

    return hard_reasons, auto_pay_reasons


def is_invoice_bulk_approvable(
    *,
    invoice: InvoiceSnapshot,
    amount_vnd: int,
    mandate: MandateSnapshot | None,
    verification_required: bool,
) -> bool:
    """Check bulk-approval eligibility against the current mandate."""
    if mandate is None or mandate.mode == "review_only":
        return False
    if verification_required:
        return False
    if invoice.status == "blocked" or invoice.severity == "red":
        return False
    if any(code in RED_REASON_CODES for code in invoice.reason_codes):
        return False

    non_ok = [c for c in invoice.reason_codes if c != "OK"]
    if invoice.severity == "green" and not non_ok:
        return True

    if invoice.severity == "yellow" and non_ok:
        # Every non-OK reason code must be covered by a mandate bulk_approvable rule whose max_amount_vnd >= amount_vnd.
        for code in non_ok:
            covered = any(
                code in rule.reason_codes and amount_vnd <= rule.max_amount_vnd
                for rule in mandate.bulk_approvable
            )
            if not covered:
                return False
        return True

    return False


def _dedup_reasons(reasons: Sequence[GateReasonItem]) -> tuple[GateReasonItem, ...]:
    seen: set[tuple[GateReasonCode, GateReasonLayer]] = set()
    result: list[GateReasonItem] = []
    for r in reasons:
        key = (r.code, r.layer)
        if key not in seen:
            seen.add(key)
            result.append(r)
    return tuple(result)


def _check_auto_pay_conditions(
    *,
    invoice: InvoiceSnapshot,
    amount_vnd: int,
    mandate: MandateSnapshot | None,
    policy: PolicyState,
    daily_budget: DailyBudgetSnapshot,
    vendor_suspended: bool,
    auto_pay_ks_reasons: Sequence[GateReasonItem],
    now: datetime,
    already_reserved_for_intent: bool = False,
) -> list[GateReasonItem]:
    """Evaluate all conditions required for mandate auto-pay."""
    reasons: list[GateReasonItem] = []

    if auto_pay_ks_reasons:
        reasons.extend(auto_pay_ks_reasons)

    if mandate is None or mandate.mode != "auto_pay":
        reasons.append(
            GateReasonItem(
                code=GateReasonCode.MANDATE_NOT_AUTO_PAY,
                layer=GateReasonLayer.mandate,
                detail="Mandate hiện tại không bật chế độ tự chi (auto_pay).",
            )
        )

    if vendor_suspended:
        reasons.append(
            GateReasonItem(
                code=GateReasonCode.VENDOR_SUSPENDED,
                layer=GateReasonLayer.mandate,
                detail="Nhà cung cấp đang bị tạm loại khỏi danh sách tự chi (QT-03).",
            )
        )

    if mandate is not None and (
        invoice.vendor_id is None or invoice.vendor_id not in mandate.auto_pay_vendor_ids
    ):
        reasons.append(
            GateReasonItem(
                code=GateReasonCode.VENDOR_NOT_IN_AUTO_PAY,
                layer=GateReasonLayer.mandate,
                detail="Nhà cung cấp không nằm trong danh sách tự chi của mandate.",
            )
        )

    if invoice.severity != "green":
        reasons.append(
            GateReasonItem(
                code=GateReasonCode.APPROVAL_MISSING,
                layer=GateReasonLayer.mandate,
                detail="Hóa đơn không ở mức xanh nên cần Chủ chuỗi duyệt trước khi chi.",
            )
        )

    assert policy.platform_limits is not None
    plat_per_invoice = policy.platform_limits.auto_pay_per_invoice_vnd
    plat_per_day = policy.platform_limits.auto_pay_per_day_vnd

    # Per-invoice limit: platform ceiling strictly dominates mandate limit.
    if amount_vnd > plat_per_invoice:
        reasons.append(
            GateReasonItem(
                code=GateReasonCode.ABOVE_PER_INVOICE_LIMIT,
                layer=GateReasonLayer.platform_policy,
                detail=f"Số tiền {amount_vnd:,}đ vượt trần nền tảng {plat_per_invoice:,}đ/hóa đơn.",
            )
        )
    elif mandate is not None and amount_vnd > mandate.per_invoice_vnd:
        reasons.append(
            GateReasonItem(
                code=GateReasonCode.ABOVE_PER_INVOICE_LIMIT,
                layer=GateReasonLayer.mandate,
                detail=f"Số tiền {amount_vnd:,}đ vượt hạn mức mandate {mandate.per_invoice_vnd:,}đ/hóa đơn.",
            )
        )

    # Daily limit: account for reserved auto-pay budget without double-counting an already-reserved intent.
    projected_daily = daily_budget.auto_pay_used_vnd + daily_budget.auto_pay_reserved_vnd
    if not already_reserved_for_intent:
        projected_daily += amount_vnd

    if projected_daily > plat_per_day:
        reasons.append(
            GateReasonItem(
                code=GateReasonCode.ABOVE_DAILY_LIMIT,
                layer=GateReasonLayer.platform_policy,
                detail=f"Tổng tự chi trong ngày ({projected_daily:,}đ) vượt trần nền tảng {plat_per_day:,}đ/ngày.",
            )
        )
    elif mandate is not None and projected_daily > mandate.per_day_vnd:
        reasons.append(
            GateReasonItem(
                code=GateReasonCode.ABOVE_DAILY_LIMIT,
                layer=GateReasonLayer.mandate,
                detail=f"Tổng tự chi trong ngày ({projected_daily:,}đ) vượt hạn mức mandate {mandate.per_day_vnd:,}đ/ngày.",
            )
        )

    if mandate is not None and not is_within_time_window(
        now, mandate.auto_pay_window_start, mandate.auto_pay_window_end
    ):
        reasons.append(
            GateReasonItem(
                code=GateReasonCode.OUTSIDE_TIME_WINDOW,
                layer=GateReasonLayer.mandate,
                detail=(
                    f"Ngoài khung giờ tự chi ({mandate.auto_pay_window_start}"
                    f"–{mandate.auto_pay_window_end} giờ VN)."
                ),
            )
        )

    return reasons


def evaluate_invoice(
    *,
    invoice: InvoiceSnapshot,
    vendor: VendorSnapshot | None,
    vendor_accounts: Sequence[VendorAccountSnapshot],
    mandate: MandateSnapshot | None,
    policy: PolicyState,
    risk_signals: RiskSignals,
    indicators: Sequence[IndicatorRef],
    daily_budget: DailyBudgetSnapshot,
    vendor_suspended: bool,
    has_settled_ledger: bool,
    held_po_escrow: EscrowRecord | None,
    now: datetime,
) -> EvaluationResult:
    """Dry-run evaluation for POST /gate/evaluate (invoice mode). Zero side effects."""
    channel = select_channel(invoice=invoice, mandate=mandate, held_po_escrow=held_po_escrow)
    payee = resolve_payee_account(
        vendor=vendor,
        seller_tax_id=invoice.seller_tax_id,
        accounts=vendor_accounts,
        channel=channel,
        held_po_escrow=held_po_escrow,
    )
    amount_vnd = (
        invoice.total_vnd
        if (invoice.total_vnd is not None and 0 <= invoice.total_vnd <= MAX_SAFE_MONEY_VND)
        else 0
    )
    payee_account_id = payee.vendor_account_id if payee is not None else None
    intent_hash = compute_invoice_intent_hash(
        invoice_id=invoice.invoice_id,
        document_sha256=invoice.document_sha256,
        payee_account_id=payee_account_id,
        amount_vnd=amount_vnd,
        channel=channel.value,
    )

    verification_required = bool(risk_signals.cross_alert_hits) or (
        "CROSS_ALERT_HIT" in invoice.reason_codes
    )

    deny_reasons: list[GateReasonItem] = []
    kill_switch_blocked = False
    policy_unavailable = False

    # Layer 1: Policy availability (fail-closed)
    if not policy.available or policy.platform_limits is None:
        policy_unavailable = True
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.POLICY_UNAVAILABLE,
                layer=GateReasonLayer.platform_policy,
                detail="Không đọc được cấu hình policy/kill switch; Payment Gate từ chối theo nguyên tắc fail-closed.",
            )
        )

    # Layer 1b: Kill switches
    hard_ks, auto_pay_ks = _match_kill_switches(
        kill_switches=policy.kill_switches,
        tenant_id=invoice.tenant_id,
        indicators=indicators,
        matched_indicator_ids=risk_signals.matched_indicator_ids,
    )
    if hard_ks:
        kill_switch_blocked = True
        deny_reasons.extend(hard_ks)

    # Layer 2: Hard rules
    if has_settled_ledger or invoice.status == "paid":
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.ALREADY_PAID,
                layer=GateReasonLayer.hard_rule,
                detail="Hóa đơn đã được thanh toán trên sổ ledger.",
            )
        )

    if risk_signals.hard_block_hits:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.OFFICIAL_FRAUD_LIST,
                layer=GateReasonLayer.hard_rule,
                detail="Indicator của hóa đơn/người bán khớp danh sách chặn cứng (risk.hard_blocks).",
            )
        )

    # Red / blocked invoice is NEVER allowed (exception only for escrow release preview when status == escrow_held).
    is_escrow_release_path = channel == Channel.escrow and held_po_escrow is not None
    if (
        invoice.status in ("blocked", "rejected")
        or (invoice.severity == "red" and not is_escrow_release_path)
    ):
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.BLOCKED_INVOICE,
                layer=GateReasonLayer.hard_rule,
                detail="Hóa đơn đang ở trạng thái blocked (mức đỏ) nên không bao giờ được chi trực tiếp.",
            )
        )

    if invoice.total_vnd is None or invoice.total_vnd <= 0 or invoice.total_vnd > MAX_SAFE_MONEY_VND:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.BLOCKED_INVOICE,
                layer=GateReasonLayer.hard_rule,
                detail="Hóa đơn chưa có số tiền hợp lệ trong khoảng an toàn (0 < amount <= 2^53-1).",
            )
        )

    if payee is None:
        # Check if vendor has only an escrow_only account while channel != escrow
        has_escrow_only = any(
            acc.status == "escrow_only" and (vendor is not None and acc.vendor_id == vendor.vendor_id)
            for acc in vendor_accounts
        )
        if has_escrow_only and channel != Channel.escrow:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.PAYEE_NOT_VERIFIED,
                    layer=GateReasonLayer.hard_rule,
                    detail="Tài khoản NCC đang ở trạng thái escrow_only nên không được nhận chuyển khoản thường.",
                )
            )
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.CHANNEL_NOT_ALLOWED,
                    layer=GateReasonLayer.hard_rule,
                    detail="Tài khoản escrow_only chỉ cho phép thanh toán qua kênh escrow.",
                )
            )
        else:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.PAYEE_NOT_VERIFIED,
                    layer=GateReasonLayer.hard_rule,
                    detail=f"Người bán (MST {invoice.seller_tax_id}) chưa có tài khoản đã xác minh phù hợp kênh {channel.value} trong vendor registry.",
                )
            )

    if mandate is None or mandate.mode == "review_only":
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.MANDATE_NOT_AUTO_PAY,
                layer=GateReasonLayer.mandate,
                detail="Tenant đang ở chế độ review_only (hoặc chưa ký mandate), không phát lệnh chi.",
            )
        )

    if deny_reasons:
        return EvaluationResult(
            decision=GateDecision.DENY,
            allowed_methods=(),
            verification_required=verification_required,
            intent_hash=intent_hash,
            payee_account_id=payee_account_id,
            amount_vnd=amount_vnd,
            channel=channel,
            reasons=_dedup_reasons(deny_reasons),
            evaluated_at=now,
            kill_switch_blocked=kill_switch_blocked,
            policy_unavailable=policy_unavailable,
        )

    # Escrow release channel always requires explicit owner single approval (never auto-pay, never bulk).
    if is_escrow_release_path:
        req_reasons: list[GateReasonItem] = [
            GateReasonItem(
                code=GateReasonCode.APPROVAL_MISSING,
                layer=GateReasonLayer.hard_rule,
                detail="Hóa đơn gắn PO có cọc tạm giữ (escrow) cần Chủ chuỗi duyệt giải ngân.",
            )
        ]
        if verification_required:
            req_reasons.insert(
                0,
                GateReasonItem(
                    code=GateReasonCode.CROSS_ALERT_UNVERIFIED,
                    layer=GateReasonLayer.hard_rule,
                    detail="Hóa đơn khớp cảnh báo chéo và bắt buộc xác minh gọi lại SĐT lưu sẵn.",
                ),
            )
        return EvaluationResult(
            decision=GateDecision.REQUIRE_APPROVAL,
            allowed_methods=(AllowedMethod.single,),
            verification_required=verification_required,
            intent_hash=intent_hash,
            payee_account_id=payee_account_id,
            amount_vnd=amount_vnd,
            channel=channel,
            reasons=_dedup_reasons(req_reasons),
            evaluated_at=now,
        )

    # Layer 3: Check auto-pay eligibility vs REQUIRE_APPROVAL
    req_reasons = []
    if verification_required:
        req_reasons.append(
            GateReasonItem(
                code=GateReasonCode.CROSS_ALERT_UNVERIFIED,
                layer=GateReasonLayer.hard_rule,
                detail="Hóa đơn khớp cảnh báo chéo nên không được tự chi và bắt buộc xác minh gọi lại.",
            )
        )

    req_reasons.extend(
        _check_auto_pay_conditions(
            invoice=invoice,
            amount_vnd=amount_vnd,
            mandate=mandate,
            policy=policy,
            daily_budget=daily_budget,
            vendor_suspended=vendor_suspended,
            auto_pay_ks_reasons=auto_pay_ks,
            now=now,
            already_reserved_for_intent=False,
        )
    )

    bulk_ok = is_invoice_bulk_approvable(
        invoice=invoice,
        amount_vnd=amount_vnd,
        mandate=mandate,
        verification_required=verification_required,
    )
    allowed_methods = (
        (AllowedMethod.single, AllowedMethod.bulk) if bulk_ok else (AllowedMethod.single,)
    )

    if req_reasons:
        return EvaluationResult(
            decision=GateDecision.REQUIRE_APPROVAL,
            allowed_methods=allowed_methods,
            verification_required=verification_required,
            intent_hash=intent_hash,
            payee_account_id=payee_account_id,
            amount_vnd=amount_vnd,
            channel=channel,
            reasons=_dedup_reasons(req_reasons),
            evaluated_at=now,
        )

    return EvaluationResult(
        decision=GateDecision.ALLOW,
        allowed_methods=allowed_methods,
        verification_required=False,
        intent_hash=intent_hash,
        payee_account_id=payee_account_id,
        amount_vnd=amount_vnd,
        channel=channel,
        reasons=(),
        evaluated_at=now,
    )


def validate_intent_authorization(
    *,
    invoice: InvoiceSnapshot,
    approval: ApprovalSnapshot | None,
    latest_completed_job_id: str | None,
    vendor: VendorSnapshot | None,
    vendor_accounts: Sequence[VendorAccountSnapshot],
    mandate: MandateSnapshot | None,
    policy: PolicyState,
    risk_signals: RiskSignals,
    indicators: Sequence[IndicatorRef],
    daily_budget: DailyBudgetSnapshot,
    vendor_suspended: bool,
    has_settled_ledger: bool,
    held_po_escrow: EscrowRecord | None,
    now: datetime,
    already_reserved_for_intent: bool = False,
) -> EvaluationResult:
    """Strict authorization check for POST /gate/intents and re-evaluation at :execute.

    Returns EvaluationResult with decision=ALLOW if every rule and approval check passes,
    otherwise decision=DENY with all GateReasons.
    """
    channel = select_channel(invoice=invoice, mandate=mandate, held_po_escrow=held_po_escrow)
    preferred_payee_id = approval.payee_account_id if approval is not None else None
    payee = resolve_payee_account(
        vendor=vendor,
        seller_tax_id=invoice.seller_tax_id,
        accounts=vendor_accounts,
        channel=channel,
        held_po_escrow=held_po_escrow,
        preferred_account_id=preferred_payee_id,
    )
    # If preferred account from approval wasn't eligible, still resolve default verified payee for reporting.
    if payee is None and preferred_payee_id is not None:
        fallback_payee = resolve_payee_account(
            vendor=vendor,
            seller_tax_id=invoice.seller_tax_id,
            accounts=vendor_accounts,
            channel=channel,
            held_po_escrow=held_po_escrow,
            preferred_account_id=None,
        )
    else:
        fallback_payee = payee

    amount_vnd = (
        invoice.total_vnd
        if (invoice.total_vnd is not None and 0 <= invoice.total_vnd <= MAX_SAFE_MONEY_VND)
        else 0
    )
    resolved_payee_id = payee.vendor_account_id if payee is not None else (
        fallback_payee.vendor_account_id if fallback_payee is not None else None
    )
    expected_intent_hash = compute_invoice_intent_hash(
        invoice_id=invoice.invoice_id,
        document_sha256=invoice.document_sha256,
        payee_account_id=resolved_payee_id,
        amount_vnd=amount_vnd,
        channel=channel.value,
    )

    verification_required = bool(risk_signals.cross_alert_hits) or (
        "CROSS_ALERT_HIT" in invoice.reason_codes
    )

    deny_reasons: list[GateReasonItem] = []
    kill_switch_blocked = False
    policy_unavailable = False

    # 1. Policy availability (fail-closed)
    if not policy.available or policy.platform_limits is None:
        policy_unavailable = True
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.POLICY_UNAVAILABLE,
                layer=GateReasonLayer.platform_policy,
                detail="Không đọc được cấu hình policy/kill switch; Payment Gate từ chối theo nguyên tắc fail-closed.",
            )
        )

    # 2. Kill switches
    hard_ks, auto_pay_ks = _match_kill_switches(
        kill_switches=policy.kill_switches,
        tenant_id=invoice.tenant_id,
        indicators=indicators,
        matched_indicator_ids=risk_signals.matched_indicator_ids,
    )
    if hard_ks:
        kill_switch_blocked = True
        deny_reasons.extend(hard_ks)

    # 3. Hard rules on invoice / ledger / risk / channel
    if has_settled_ledger or invoice.status == "paid":
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.ALREADY_PAID,
                layer=GateReasonLayer.hard_rule,
                detail="Hóa đơn đã được thanh toán trên sổ ledger.",
            )
        )

    if risk_signals.hard_block_hits:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.OFFICIAL_FRAUD_LIST,
                layer=GateReasonLayer.hard_rule,
                detail="Indicator khớp danh sách chặn cứng (risk.hard_blocks).",
            )
        )

    if invoice.status in ("blocked", "rejected") or invoice.severity == "red":
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.BLOCKED_INVOICE,
                layer=GateReasonLayer.hard_rule,
                detail="Hóa đơn đang ở trạng thái blocked (mức đỏ) không bao giờ được phép chi.",
            )
        )

    if invoice.total_vnd is None or invoice.total_vnd <= 0 or invoice.total_vnd > MAX_SAFE_MONEY_VND:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.BLOCKED_INVOICE,
                layer=GateReasonLayer.hard_rule,
                detail="Hóa đơn chưa có số tiền hợp lệ trong khoảng an toàn (0 < amount <= 2^53-1).",
            )
        )

    # Hard rule: invoices on a PO with a held escrow MUST be paid via /escrows/{id}:release, never /intents.
    if channel == Channel.escrow or (approval is not None and approval.channel == Channel.escrow.value):
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.CHANNEL_NOT_ALLOWED,
                layer=GateReasonLayer.hard_rule,
                detail="Hóa đơn gắn PO đang có cọc tạm giữ (escrow) chỉ được chi qua giải ngân escrow.",
            )
        )

    # Payee check (strictly registry-only; escrow_only account forbidden for normal transfer/card)
    if payee is None:
        if preferred_payee_id is not None:
            matched_raw = next(
                (a for a in vendor_accounts if a.vendor_account_id == preferred_payee_id), None
            )
            if matched_raw is not None and matched_raw.status == "escrow_only":
                deny_reasons.append(
                    GateReasonItem(
                        code=GateReasonCode.PAYEE_NOT_VERIFIED,
                        layer=GateReasonLayer.hard_rule,
                        detail="Tài khoản escrow_only không được phép nhận chuyển khoản thường hoặc thẻ ảo.",
                    )
                )
                deny_reasons.append(
                    GateReasonItem(
                        code=GateReasonCode.CHANNEL_NOT_ALLOWED,
                        layer=GateReasonLayer.hard_rule,
                        detail="Tài khoản escrow_only chỉ dùng cho kênh escrow.",
                    )
                )
            else:
                deny_reasons.append(
                    GateReasonItem(
                        code=GateReasonCode.PAYEE_NOT_VERIFIED,
                        layer=GateReasonLayer.hard_rule,
                        detail="Tài khoản nhận tiền không thuộc danh bạ đã xác minh của NCC khớp MST.",
                    )
                )
        else:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.PAYEE_NOT_VERIFIED,
                    layer=GateReasonLayer.hard_rule,
                    detail="Người bán chưa có tài khoản đã xác minh trong vendor registry.",
                )
            )

    if mandate is None or mandate.mode == "review_only":
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.MANDATE_NOT_AUTO_PAY,
                layer=GateReasonLayer.mandate,
                detail="Tenant đang ở chế độ review_only (hoặc chưa ký mandate), không được chi.",
            )
        )

    # 4. Approval validation
    if approval is None:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.APPROVAL_MISSING,
                layer=GateReasonLayer.hard_rule,
                detail="Thiếu bản ghi approval cho hóa đơn.",
            )
        )
    else:
        if approval.status != "active":
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.APPROVAL_STALE,
                    layer=GateReasonLayer.hard_rule,
                    detail=f"Approval đang ở trạng thái '{approval.status}', không còn active.",
                )
            )
        if approval.invoice_id != invoice.invoice_id or approval.tenant_id != invoice.tenant_id:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.APPROVAL_STALE,
                    layer=GateReasonLayer.hard_rule,
                    detail="Approval không thuộc hóa đơn này.",
                )
            )
        if latest_completed_job_id is None or approval.job_id != latest_completed_job_id:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.APPROVAL_STALE,
                    layer=GateReasonLayer.hard_rule,
                    detail="Approval không thuộc lần điều tra (job hoàn tất) mới nhất của hóa đơn.",
                )
            )
        if (
            approval.intent_hash != expected_intent_hash
            or approval.amount_vnd != amount_vnd
            or approval.channel != channel.value
            or (payee is not None and approval.payee_account_id != payee.vendor_account_id)
        ):
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.APPROVAL_STALE,
                    layer=GateReasonLayer.hard_rule,
                    detail="Hóa đơn, tài khoản nhận, số tiền hoặc kênh chi đã thay đổi (intent_hash không khớp).",
                )
            )

        # Cross-alert verification requirement (D8)
        if verification_required:
            if approval.verification is None or not approval.verification.is_confirmed():
                deny_reasons.append(
                    GateReasonItem(
                        code=GateReasonCode.CROSS_ALERT_UNVERIFIED,
                        layer=GateReasonLayer.hard_rule,
                        detail="Hóa đơn khớp cảnh báo chéo nhưng approval chưa có xác minh gọi lại SĐT lưu sẵn.",
                    )
                )

        # Method-specific re-verification
        if approval.method == "mandate":
            if auto_pay_ks:
                kill_switch_blocked = True
            if policy.available and policy.platform_limits is not None:
                deny_reasons.extend(
                    _check_auto_pay_conditions(
                        invoice=invoice,
                        amount_vnd=amount_vnd,
                        mandate=mandate,
                        policy=policy,
                        daily_budget=daily_budget,
                        vendor_suspended=vendor_suspended,
                        auto_pay_ks_reasons=auto_pay_ks,
                        now=now,
                        already_reserved_for_intent=already_reserved_for_intent,
                    )
                )
        elif approval.method == "bulk":
            if not is_invoice_bulk_approvable(
                invoice=invoice,
                amount_vnd=amount_vnd,
                mandate=mandate,
                verification_required=verification_required,
            ):
                deny_reasons.append(
                    GateReasonItem(
                        code=GateReasonCode.APPROVAL_STALE,
                        layer=GateReasonLayer.mandate,
                        detail="Hóa đơn không còn đáp ứng điều kiện duyệt hàng loạt theo mandate hiện hành.",
                    )
                )
        elif approval.method != "single":
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.APPROVAL_STALE,
                    layer=GateReasonLayer.hard_rule,
                    detail=f"Phương thức duyệt không hợp lệ: '{approval.method}'.",
                )
            )

    if deny_reasons:
        return EvaluationResult(
            decision=GateDecision.DENY,
            allowed_methods=(),
            verification_required=verification_required,
            intent_hash=expected_intent_hash,
            payee_account_id=resolved_payee_id,
            amount_vnd=amount_vnd,
            channel=channel,
            reasons=_dedup_reasons(deny_reasons),
            evaluated_at=now,
            kill_switch_blocked=kill_switch_blocked,
            policy_unavailable=policy_unavailable,
        )

    return EvaluationResult(
        decision=GateDecision.ALLOW,
        allowed_methods=(AllowedMethod.single,),
        verification_required=verification_required,
        intent_hash=expected_intent_hash,
        payee_account_id=resolved_payee_id,
        amount_vnd=amount_vnd,
        channel=channel,
        reasons=(),
        evaluated_at=now,
    )


def evaluate_escrow_hold(
    *,
    po: PurchaseOrderSnapshot,
    vendor: VendorSnapshot | None,
    vendor_account: VendorAccountSnapshot | None,
    amount_vnd: int,
    has_open_escrow: bool,
    mandate: MandateSnapshot | None,
    policy: PolicyState,
    risk_signals: RiskSignals,
    indicators: Sequence[IndicatorRef],
    now: datetime,
) -> EvaluationResult:
    """Dry-run evaluation for POST /gate/evaluate (escrow preview mode)."""
    payee_id = vendor_account.vendor_account_id if vendor_account is not None else None
    intent_hash = (
        compute_escrow_intent_hash(
            purchase_order_id=po.purchase_order_id,
            payee_account_id=payee_id,
            amount_vnd=amount_vnd,
        )
        if payee_id is not None
        else compute_invoice_intent_hash(
            invoice_id=po.purchase_order_id,
            document_sha256="0" * 64,
            payee_account_id=None,
            amount_vnd=max(amount_vnd, 0),
            channel=Channel.escrow.value,
        )
    )
    verification_required = bool(risk_signals.cross_alert_hits)

    deny_reasons: list[GateReasonItem] = []
    kill_switch_blocked = False
    policy_unavailable = False

    if not policy.available or policy.platform_limits is None:
        policy_unavailable = True
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.POLICY_UNAVAILABLE,
                layer=GateReasonLayer.platform_policy,
                detail="Không đọc được cấu hình policy/kill switch; Payment Gate từ chối theo nguyên tắc fail-closed.",
            )
        )

    hard_ks, _ = _match_kill_switches(
        kill_switches=policy.kill_switches,
        tenant_id=po.tenant_id,
        indicators=indicators,
        matched_indicator_ids=risk_signals.matched_indicator_ids,
    )
    if hard_ks:
        kill_switch_blocked = True
        deny_reasons.extend(hard_ks)

    if risk_signals.hard_block_hits:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.OFFICIAL_FRAUD_LIST,
                layer=GateReasonLayer.hard_rule,
                detail="Indicator của NCC/tài khoản khớp danh sách chặn cứng.",
            )
        )

    if po.status in ("closed", "cancelled"):
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.BLOCKED_INVOICE,
                layer=GateReasonLayer.hard_rule,
                detail=f"Đơn đặt hàng (PO) đang ở trạng thái '{po.status}', không thể tạo cọc.",
            )
        )

    if has_open_escrow:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.ALREADY_PAID,
                layer=GateReasonLayer.hard_rule,
                detail="Đơn đặt hàng (PO) đã có khoản cọc tạm giữ đang mở.",
            )
        )

    if amount_vnd <= 0 or amount_vnd > MAX_SAFE_MONEY_VND or amount_vnd > po.total_vnd:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.ABOVE_PER_INVOICE_LIMIT,
                layer=GateReasonLayer.hard_rule,
                detail=f"Số tiền cọc ({amount_vnd:,}đ) phải trong khoảng hợp lệ và không vượt giá trị PO ({po.total_vnd:,}đ).",
            )
        )

    if (
        vendor is None
        or vendor.status != "active"
        or vendor_account is None
        or not is_account_valid_for_channel(vendor_account, vendor=vendor, channel=Channel.escrow)
    ):
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.PAYEE_NOT_VERIFIED,
                layer=GateReasonLayer.hard_rule,
                detail="Tài khoản nhận cọc phải ở trạng thái verified hoặc escrow_only và thuộc NCC của PO.",
            )
        )

    if mandate is None or mandate.mode == "review_only":
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.MANDATE_NOT_AUTO_PAY,
                layer=GateReasonLayer.mandate,
                detail="Tenant đang ở chế độ review_only (hoặc chưa ký mandate).",
            )
        )

    if deny_reasons:
        return EvaluationResult(
            decision=GateDecision.DENY,
            allowed_methods=(),
            verification_required=verification_required,
            intent_hash=intent_hash,
            payee_account_id=payee_id,
            amount_vnd=max(amount_vnd, 0),
            channel=Channel.escrow,
            reasons=_dedup_reasons(deny_reasons),
            evaluated_at=now,
            kill_switch_blocked=kill_switch_blocked,
            policy_unavailable=policy_unavailable,
        )

    req_reasons = [
        GateReasonItem(
            code=GateReasonCode.APPROVAL_MISSING,
            layer=GateReasonLayer.hard_rule,
            detail="Tạo cọc tạm giữ (escrow) luôn cần Chủ chuỗi duyệt đơn lẻ xác thực mạnh.",
        )
    ]
    if verification_required:
        req_reasons.insert(
            0,
            GateReasonItem(
                code=GateReasonCode.CROSS_ALERT_UNVERIFIED,
                layer=GateReasonLayer.hard_rule,
                detail="Tài khoản/NCC khớp cảnh báo chéo và cần xác minh gọi lại.",
            ),
        )

    return EvaluationResult(
        decision=GateDecision.REQUIRE_APPROVAL,
        allowed_methods=(AllowedMethod.single,),
        verification_required=verification_required,
        intent_hash=intent_hash,
        payee_account_id=payee_id,
        amount_vnd=amount_vnd,
        channel=Channel.escrow,
        reasons=_dedup_reasons(req_reasons),
        evaluated_at=now,
    )


def validate_escrow_create(
    *,
    approval: ApprovalSnapshot | None,
    po: PurchaseOrderSnapshot | None,
    vendor: VendorSnapshot | None,
    vendor_account: VendorAccountSnapshot | None,
    has_open_escrow: bool,
    mandate: MandateSnapshot | None,
    policy: PolicyState,
    risk_signals: RiskSignals,
    indicators: Sequence[IndicatorRef],
    now: datetime,
) -> EvaluationResult:
    """Validate POST /gate/escrows strictly from Approval + DB records."""
    deny_reasons: list[GateReasonItem] = []
    kill_switch_blocked = False
    policy_unavailable = False
    verification_required = bool(risk_signals.cross_alert_hits)

    if not policy.available or policy.platform_limits is None:
        policy_unavailable = True
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.POLICY_UNAVAILABLE,
                layer=GateReasonLayer.platform_policy,
                detail="Không đọc được cấu hình policy/kill switch (fail-closed).",
            )
        )

    tenant_id = po.tenant_id if po is not None else (approval.tenant_id if approval else "")
    hard_ks, _ = _match_kill_switches(
        kill_switches=policy.kill_switches,
        tenant_id=tenant_id,
        indicators=indicators,
        matched_indicator_ids=risk_signals.matched_indicator_ids,
    )
    if hard_ks:
        kill_switch_blocked = True
        deny_reasons.extend(hard_ks)

    if risk_signals.hard_block_hits:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.OFFICIAL_FRAUD_LIST,
                layer=GateReasonLayer.hard_rule,
                detail="Indicator khớp danh sách chặn cứng (risk.hard_blocks).",
            )
        )

    if approval is None:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.APPROVAL_MISSING,
                layer=GateReasonLayer.hard_rule,
                detail="Thiếu bản ghi approval tạo cọc.",
            )
        )
    else:
        if approval.status != "active":
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.APPROVAL_STALE,
                    layer=GateReasonLayer.hard_rule,
                    detail=f"Approval tạo cọc đang ở trạng thái '{approval.status}', không còn active.",
                )
            )
        if approval.channel != Channel.escrow.value:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.CHANNEL_NOT_ALLOWED,
                    layer=GateReasonLayer.hard_rule,
                    detail="Approval tạo cọc phải có channel = escrow.",
                )
            )
        if verification_required and (
            approval.verification is None or not approval.verification.is_confirmed()
        ):
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.CROSS_ALERT_UNVERIFIED,
                    layer=GateReasonLayer.hard_rule,
                    detail="NCC/tài khoản khớp cảnh báo chéo nhưng approval chưa xác minh gọi lại.",
                )
            )

    if po is None or po.status in ("closed", "cancelled"):
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.BLOCKED_INVOICE,
                layer=GateReasonLayer.hard_rule,
                detail="Đơn đặt hàng (PO) không tồn tại hoặc đã đóng/hủy.",
            )
        )
    elif approval is not None and (
        approval.amount_vnd <= 0
        or approval.amount_vnd > MAX_SAFE_MONEY_VND
        or approval.amount_vnd > po.total_vnd
    ):
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.ABOVE_PER_INVOICE_LIMIT,
                layer=GateReasonLayer.hard_rule,
                detail=f"Số tiền cọc ({approval.amount_vnd:,}đ) không hợp lệ hoặc vượt giá trị PO ({po.total_vnd:,}đ).",
            )
        )

    if has_open_escrow:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.ALREADY_PAID,
                layer=GateReasonLayer.hard_rule,
                detail="Mỗi đơn đặt hàng (PO) chỉ được có tối đa một escrow đang mở.",
            )
        )

    if (
        vendor is None
        or vendor.status != "active"
        or vendor_account is None
        or not is_account_valid_for_channel(vendor_account, vendor=vendor, channel=Channel.escrow)
    ):
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.PAYEE_NOT_VERIFIED,
                layer=GateReasonLayer.hard_rule,
                detail="Tài khoản nhận cọc không hợp lệ (cần verified hoặc escrow_only thuộc NCC của PO).",
            )
        )

    if mandate is None or mandate.mode == "review_only":
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.MANDATE_NOT_AUTO_PAY,
                layer=GateReasonLayer.mandate,
                detail="Tenant đang ở chế độ review_only (hoặc chưa ký mandate).",
            )
        )

    amount_vnd = approval.amount_vnd if approval is not None else 0
    payee_id = vendor_account.vendor_account_id if vendor_account is not None else None
    if po is not None and payee_id is not None and approval is not None:
        expected_hash = compute_escrow_intent_hash(
            purchase_order_id=po.purchase_order_id,
            payee_account_id=payee_id,
            amount_vnd=amount_vnd,
        )
        if approval.intent_hash != expected_hash:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.APPROVAL_STALE,
                    layer=GateReasonLayer.hard_rule,
                    detail="intent_hash của approval tạo cọc không khớp dữ liệu PO/tài khoản/số tiền.",
                )
            )
    else:
        expected_hash = "0" * 64

    if deny_reasons:
        return EvaluationResult(
            decision=GateDecision.DENY,
            allowed_methods=(),
            verification_required=verification_required,
            intent_hash=expected_hash,
            payee_account_id=payee_id,
            amount_vnd=max(amount_vnd, 0),
            channel=Channel.escrow,
            reasons=_dedup_reasons(deny_reasons),
            evaluated_at=now,
            kill_switch_blocked=kill_switch_blocked,
            policy_unavailable=policy_unavailable,
        )

    return EvaluationResult(
        decision=GateDecision.ALLOW,
        allowed_methods=(AllowedMethod.single,),
        verification_required=verification_required,
        intent_hash=expected_hash,
        payee_account_id=payee_id,
        amount_vnd=amount_vnd,
        channel=Channel.escrow,
        reasons=(),
        evaluated_at=now,
    )


def validate_escrow_release(
    *,
    escrow: EscrowRecord,
    release_approval: ApprovalSnapshot | None,
    release_invoice: InvoiceSnapshot | None,
    goods_receipt: GoodsReceiptSnapshot | None,
    po: PurchaseOrderSnapshot | None,
    vendor: VendorSnapshot | None,
    vendor_account: VendorAccountSnapshot | None,
    latest_completed_job_id: str | None,
    has_settled_ledger: bool,
    policy: PolicyState,
    risk_signals: RiskSignals,
    indicators: Sequence[IndicatorRef],
    now: datetime,
) -> EvaluationResult:
    """Validate POST /gate/escrows/{id}:release (F7): requires GRN + matching approved invoice."""
    deny_reasons: list[GateReasonItem] = []
    kill_switch_blocked = False
    policy_unavailable = False
    verification_required = bool(risk_signals.cross_alert_hits) or (
        release_invoice is not None and "CROSS_ALERT_HIT" in release_invoice.reason_codes
    )

    if not policy.available or policy.platform_limits is None:
        policy_unavailable = True
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.POLICY_UNAVAILABLE,
                layer=GateReasonLayer.platform_policy,
                detail="Không đọc được cấu hình policy/kill switch (fail-closed).",
            )
        )

    hard_ks, _ = _match_kill_switches(
        kill_switches=policy.kill_switches,
        tenant_id=escrow.tenant_id,
        indicators=indicators,
        matched_indicator_ids=risk_signals.matched_indicator_ids,
    )
    if hard_ks:
        kill_switch_blocked = True
        deny_reasons.extend(hard_ks)

    if risk_signals.hard_block_hits:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.OFFICIAL_FRAUD_LIST,
                layer=GateReasonLayer.hard_rule,
                detail="Indicator khớp danh sách chặn cứng (risk.hard_blocks).",
            )
        )

    # Hard rule (B1): MUST have a valid GoodsReceipt belonging to the escrow's PO!
    if goods_receipt is None:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.ESCROW_MISMATCH,
                layer=GateReasonLayer.hard_rule,
                detail="Không thể giải ngân escrow khi chưa có phiếu nhập hàng (goods_receipt).",
            )
        )
    elif (
        goods_receipt.purchase_order_id != escrow.purchase_order_id
        or goods_receipt.tenant_id != escrow.tenant_id
    ):
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.ESCROW_MISMATCH,
                layer=GateReasonLayer.hard_rule,
                detail="Phiếu nhập hàng (goods_receipt) không thuộc đơn đặt hàng (PO) của khoản cọc.",
            )
        )

    if has_settled_ledger or (release_invoice is not None and release_invoice.status == "paid"):
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.ALREADY_PAID,
                layer=GateReasonLayer.hard_rule,
                detail="Hóa đơn giải ngân đã được thanh toán.",
            )
        )

    if release_approval is None:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.APPROVAL_MISSING,
                layer=GateReasonLayer.hard_rule,
                detail="Thiếu approval giải ngân hóa đơn.",
            )
        )
    else:
        if release_approval.status != "active":
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.APPROVAL_STALE,
                    layer=GateReasonLayer.hard_rule,
                    detail=f"Approval giải ngân đang ở trạng thái '{release_approval.status}', không còn active.",
                )
            )
        if release_approval.channel != Channel.escrow.value:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.CHANNEL_NOT_ALLOWED,
                    layer=GateReasonLayer.hard_rule,
                    detail="Approval giải ngân phải có channel = escrow.",
                )
            )
        if latest_completed_job_id is None or release_approval.job_id != latest_completed_job_id:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.APPROVAL_STALE,
                    layer=GateReasonLayer.hard_rule,
                    detail="Approval giải ngân không thuộc job hoàn tất mới nhất của hóa đơn.",
                )
            )
        # B1: approved amount MUST EQUAL held amount AND approved payee MUST EQUAL held account!
        if release_approval.amount_vnd != escrow.amount_vnd:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.ESCROW_MISMATCH,
                    layer=GateReasonLayer.hard_rule,
                    detail=(
                        f"Số tiền duyệt giải ngân ({release_approval.amount_vnd:,}đ) "
                        f"không khớp số tiền cọc đang giữ ({escrow.amount_vnd:,}đ)."
                    ),
                )
            )
        if release_approval.payee_account_id != escrow.vendor_account_id:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.ESCROW_MISMATCH,
                    layer=GateReasonLayer.hard_rule,
                    detail="Tài khoản nhận trong approval giải ngân không khớp tài khoản đã khóa của cọc.",
                )
            )
        if verification_required and (
            release_approval.verification is None or not release_approval.verification.is_confirmed()
        ):
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.CROSS_ALERT_UNVERIFIED,
                    layer=GateReasonLayer.hard_rule,
                    detail="Hóa đơn giải ngân khớp cảnh báo chéo nhưng approval chưa có xác minh gọi lại.",
                )
            )

    if release_invoice is None:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.ESCROW_MISMATCH,
                layer=GateReasonLayer.hard_rule,
                detail="Không tìm thấy hóa đơn giải ngân gắn với approval.",
            )
        )
    else:
        if release_invoice.status in ("blocked", "rejected"):
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.BLOCKED_INVOICE,
                    layer=GateReasonLayer.hard_rule,
                    detail="Hóa đơn giải ngân đang bị blocked hoặc rejected.",
                )
            )
        if po is None or release_invoice.vendor_id != po.vendor_id:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.ESCROW_MISMATCH,
                    layer=GateReasonLayer.hard_rule,
                    detail="Hóa đơn giải ngân không thuộc cùng nhà cung cấp với PO của cọc.",
                )
            )
        if release_invoice.purchase_order_id != escrow.purchase_order_id:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.ESCROW_MISMATCH,
                    layer=GateReasonLayer.hard_rule,
                    detail="Hóa đơn giải ngân không gắn đúng PO của khoản cọc.",
                )
            )
        if (
            release_invoice.total_vnd is None
            or release_invoice.total_vnd <= 0
            or release_invoice.total_vnd > MAX_SAFE_MONEY_VND
        ):
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.BLOCKED_INVOICE,
                    layer=GateReasonLayer.hard_rule,
                    detail="Hóa đơn giải ngân chưa có số tiền hợp lệ.",
                )
            )
        elif release_invoice.total_vnd != escrow.amount_vnd:
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.ESCROW_MISMATCH,
                    layer=GateReasonLayer.hard_rule,
                    detail=(
                        f"Tổng hóa đơn giải ngân ({release_invoice.total_vnd:,}đ) "
                        f"phải bằng đúng số tiền cọc đang giữ ({escrow.amount_vnd:,}đ)."
                    ),
                )
            )

    if (
        vendor is None
        or vendor.status != "active"
        or vendor_account is None
        or vendor_account.vendor_account_id != escrow.vendor_account_id
        or not is_account_valid_for_channel(vendor_account, vendor=vendor, channel=Channel.escrow)
    ):
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.PAYEE_NOT_VERIFIED,
                layer=GateReasonLayer.hard_rule,
                detail="Tài khoản nhận giải ngân không còn hợp lệ trong vendor registry.",
            )
        )

    expected_hash = "0" * 64
    amount_vnd = 0
    if release_invoice is not None and release_invoice.total_vnd is not None and release_invoice.total_vnd >= 0:
        amount_vnd = release_invoice.total_vnd
        expected_hash = compute_invoice_intent_hash(
            invoice_id=release_invoice.invoice_id,
            document_sha256=release_invoice.document_sha256,
            payee_account_id=escrow.vendor_account_id,
            amount_vnd=amount_vnd,
            channel=Channel.escrow.value,
        )
        if release_approval is not None and (
            release_approval.intent_hash != expected_hash
            or release_approval.payee_account_id != escrow.vendor_account_id
            or release_approval.amount_vnd != amount_vnd
        ):
            deny_reasons.append(
                GateReasonItem(
                    code=GateReasonCode.APPROVAL_STALE,
                    layer=GateReasonLayer.hard_rule,
                    detail="intent_hash của approval giải ngân không khớp hóa đơn/tài khoản/số tiền.",
                )
            )

    if escrow.status != EscrowStatus.held:
        deny_reasons.append(
            GateReasonItem(
                code=GateReasonCode.APPROVAL_STALE,
                layer=GateReasonLayer.hard_rule,
                detail=f"Escrow đang ở trạng thái '{escrow.status.value}', không thể giải ngân.",
            )
        )

    if deny_reasons:
        return EvaluationResult(
            decision=GateDecision.DENY,
            allowed_methods=(),
            verification_required=verification_required,
            intent_hash=expected_hash,
            payee_account_id=escrow.vendor_account_id,
            amount_vnd=amount_vnd,
            channel=Channel.escrow,
            reasons=_dedup_reasons(deny_reasons),
            evaluated_at=now,
            kill_switch_blocked=kill_switch_blocked,
            policy_unavailable=policy_unavailable,
        )

    return EvaluationResult(
        decision=GateDecision.ALLOW,
        allowed_methods=(AllowedMethod.single,),
        verification_required=verification_required,
        intent_hash=expected_hash,
        payee_account_id=escrow.vendor_account_id,
        amount_vnd=amount_vnd,
        channel=Channel.escrow,
        reasons=(),
        evaluated_at=now,
    )

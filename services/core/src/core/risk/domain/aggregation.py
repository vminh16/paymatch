"""Pure Python severity aggregation, reason-code floors/ceilings, tool-output floors, system checks, and post-investigation status rules.

NO I/O, NO DB, NO network.
Spec references:
- docs/03-agents/agent-runtime.md §5a (reason code table)
- docs/05-api/internal-api.md §3 (tool output floors) & §4 (system checks at :complete)
- docs/05-api/merchant-api.md §2 (post-investigation status table)
- docs/02-architecture/flows.md (F2 QT-03 auto-pay suspensions)
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

Severity = Literal["green", "yellow", "red"]

SEVERITY_RANK: dict[Severity, int] = {"green": 0, "yellow": 1, "red": 2}
RANK_TO_SEVERITY: dict[int, Severity] = {0: "green", 1: "yellow", 2: "red"}


@dataclass(frozen=True)
class ReasonCodeRule:
    code: str
    floor: Severity
    ceiling: Severity | None
    qt03: bool
    label_vi: str


# Exact source of truth from docs/03-agents/agent-runtime.md §5a (all 27 codes)
REASON_CODE_RULES: dict[str, ReasonCodeRule] = {
    "OK": ReasonCodeRule("OK", "green", None, False, "Hợp lệ"),
    "PRICE_ABOVE_CONTRACT": ReasonCodeRule(
        "PRICE_ABOVE_CONTRACT", "yellow", None, True, "Đơn giá vượt hợp đồng"
    ),
    "PACK_SIZE_CHANGED": ReasonCodeRule(
        "PACK_SIZE_CHANGED", "yellow", None, True, "Thay đổi quy cách đóng gói (shrinkflation)"
    ),
    "QUANTITY_ABOVE_NORM": ReasonCodeRule(
        "QUANTITY_ABOVE_NORM", "yellow", None, True, "Số lượng vượt định mức / phiếu nhập"
    ),
    "NO_GOODS_RECEIPT": ReasonCodeRule(
        "NO_GOODS_RECEIPT", "yellow", None, False, "Chưa có phiếu nhập kho"
    ),
    "DUPLICATE_INVOICE": ReasonCodeRule(
        "DUPLICATE_INVOICE", "red", None, True, "Hóa đơn trùng lặp"
    ),
    "PAYEE_CHANGE_REQUEST": ReasonCodeRule(
        "PAYEE_CHANGE_REQUEST", "red", None, True, "Yêu cầu đổi tài khoản thụ hưởng"
    ),
    "PERSONAL_ACCOUNT": ReasonCodeRule(
        "PERSONAL_ACCOUNT", "red", None, False, "Tài khoản nhận tiền là tài khoản cá nhân"
    ),
    "HIDDEN_INSTRUCTION": ReasonCodeRule(
        "HIDDEN_INSTRUCTION", "red", None, True, "Câu lệnh giấu trong dữ liệu hóa đơn"
    ),
    "URGENCY_PRESSURE": ReasonCodeRule(
        "URGENCY_PRESSURE", "yellow", None, False, "Dấu hiệu hối thúc thanh toán gấp"
    ),
    "CROSS_ALERT_HIT": ReasonCodeRule(
        "CROSS_ALERT_HIT", "yellow", "yellow", True, "Trùng cảnh báo chéo trên mạng lưới MoMo"
    ),
    "OFFICIAL_FRAUD_LIST": ReasonCodeRule(
        "OFFICIAL_FRAUD_LIST", "red", None, True, "Nằm trong danh sách gian lận chính thức (SIMO)"
    ),
    "TAX_RISK_LIST": ReasonCodeRule(
        "TAX_RISK_LIST", "red", None, True, "Doanh nghiệp thuộc danh sách rủi ro cao về thuế"
    ),
    "MST_INACTIVE": ReasonCodeRule(
        "MST_INACTIVE", "red", None, False, "Mã số thuế ngừng hoạt động / bỏ địa chỉ"
    ),
    "INVOICE_NOT_FOUND_ON_PORTAL": ReasonCodeRule(
        "INVOICE_NOT_FOUND_ON_PORTAL", "red", None, False, "Hóa đơn không hợp lệ hoặc không có trên cổng HĐĐT"
    ),
    "VAT_DEDUCTION_RISK": ReasonCodeRule(
        "VAT_DEDUCTION_RISK", "yellow", None, False, "Rủi ro khấu trừ thuế GTGT"
    ),
    "UTILITY_OUT_OF_RANGE": ReasonCodeRule(
        "UTILITY_OUT_OF_RANGE", "yellow", None, True, "Chỉ số điện/nước bất thường"
    ),
    "OVER_LIMIT": ReasonCodeRule(
        "OVER_LIMIT", "yellow", None, False, "Vượt hạn mức tự chi"
    ),
    "LOW_BALANCE": ReasonCodeRule(
        "LOW_BALANCE", "yellow", None, False, "Số dư ví thấp"
    ),
    "NON_XML_SOURCE": ReasonCodeRule(
        "NON_XML_SOURCE", "yellow", None, False, "Hóa đơn PDF/ảnh không có XML gốc"
    ),
    "AMOUNT_MISMATCH": ReasonCodeRule(
        "AMOUNT_MISMATCH", "yellow", None, False, "Sai lệch số học trên hóa đơn"
    ),
    "UNKNOWN_VENDOR": ReasonCodeRule(
        "UNKNOWN_VENDOR", "yellow", None, False, "Nhà cung cấp chưa có trong danh bạ"
    ),
    "BOT_TIMEOUT": ReasonCodeRule(
        "BOT_TIMEOUT", "yellow", None, False, "Bot kiểm tra quá thời gian"
    ),
    "BOT_INVALID_OUTPUT": ReasonCodeRule(
        "BOT_INVALID_OUTPUT", "yellow", None, False, "Kết quả bot không đúng định dạng"
    ),
    "BOT_NOT_RUN": ReasonCodeRule(
        "BOT_NOT_RUN", "yellow", None, False, "Thiếu kết quả từ bot bắt buộc"
    ),
    "BOT_DISABLED": ReasonCodeRule(
        "BOT_DISABLED", "yellow", None, False, "Bot bắt buộc đang tạm tắt"
    ),
    "CUSTOM": ReasonCodeRule(
        "CUSTOM", "yellow", None, False, "Cảnh báo từ bot tùy chỉnh"
    ),
}

QT03_REASON_CODES: frozenset[str] = frozenset(
    code for code, rule in REASON_CODE_RULES.items() if rule.qt03
)

FRAUD_INDICATOR_REASON_CODES: frozenset[str] = frozenset(
    {
        "PERSONAL_ACCOUNT",
        "HIDDEN_INSTRUCTION",
        "PAYEE_CHANGE_REQUEST",
        "OFFICIAL_FRAUD_LIST",
        "TAX_RISK_LIST",
    }
)


def max_severity(a: Severity, b: Severity) -> Severity:
    return a if SEVERITY_RANK[a] >= SEVERITY_RANK[b] else b


def min_severity(a: Severity, b: Severity) -> Severity:
    return a if SEVERITY_RANK[a] <= SEVERITY_RANK[b] else b


def normalize_reason_codes(codes: Iterable[str]) -> list[str]:
    """Deduplicate reason codes preserving order; drop 'OK' when any non-OK code is present."""
    seen: set[str] = set()
    ordered: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    non_ok = [c for c in ordered if c != "OK"]
    if non_ok:
        return non_ok
    return ["OK"]


def compute_finding_severity(
    severity_reported: Severity,
    reason_codes: Collection[str],
) -> Severity:
    """Compute final finding severity applying reason-code floors and CROSS_ALERT_HIT ceiling.

    Rules (agent-runtime.md §5a):
    - Every reason code applies its floor severity (e.g. HIDDEN_INSTRUCTION -> red even if bot said green).
    - If the finding's non-OK reason codes are exclusively CROSS_ALERT_HIT, cap severity at yellow (D6).
    - Unknown reason codes default to yellow floor (fail-safe).
    """
    codes = normalize_reason_codes(reason_codes)
    non_ok = [c for c in codes if c != "OK"]

    floor: Severity = "green"
    for code in non_ok:
        rule = REASON_CODE_RULES.get(code)
        code_floor: Severity = rule.floor if rule is not None else "yellow"
        floor = max_severity(floor, code_floor)

    effective = max_severity(severity_reported, floor)

    # CROSS_ALERT_HIT alone is capped at yellow (D6)
    if non_ok and all(
        (REASON_CODE_RULES.get(c) is not None and REASON_CODE_RULES[c].ceiling == "yellow")
        for c in non_ok
    ):
        effective = min_severity(effective, "yellow")

    return effective


def _to_decimal(val: Any) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def extract_tool_floor_reason_codes(tool_calls: Iterable[Mapping[str, Any]]) -> list[str]:
    """Derive mandatory reason codes from trusted tool call outputs (internal-api.md §3).

    B1: Confirmed positive SIMO hits (`official_fraud_list` with `listed=True`) are preserved even when
    a later indicator in the same multi-indicator call errored and populated `error`.
    """
    added: list[str] = []
    for tc in tool_calls:
        tool_id = tc.get("tool_id")
        output = tc.get("output") or {}
        if not isinstance(output, Mapping):
            continue
        if tc.get("error"):
            # B1: Preserve confirmed positive hits from partially completed official_fraud_list calls
            if tool_id == "official_fraud_list" and output.get("listed") is True:
                added.append("OFFICIAL_FRAUD_LIST")
            continue

        if tool_id == "price_check":
            for item in output.get("items", []):
                if not isinstance(item, Mapping):
                    continue
                delta = _to_decimal(item.get("delta_pct"))
                if delta is not None and delta > 0:
                    added.append("PRICE_ABOVE_CONTRACT")
                pack_contract = _to_decimal(item.get("pack_qty_contract"))
                pack_parsed = _to_decimal(item.get("pack_qty_parsed"))
                if pack_parsed is None or (
                    pack_contract is not None and pack_parsed != pack_contract
                ):
                    added.append("PACK_SIZE_CHANGED")

        elif tool_id == "three_way_match":
            if output.get("quantity_above_norm") is True:
                added.append("QUANTITY_ABOVE_NORM")
            if output.get("missing_goods_receipt") is True:
                added.append("NO_GOODS_RECEIPT")

        elif tool_id == "utility_baseline":
            if output.get("out_of_range") is True:
                added.append("UTILITY_OUT_OF_RANGE")

        elif tool_id == "tax_id_lookup":
            status_code = output.get("status_code")
            if status_code in {"01", "03", "05", "06", "07"}:
                added.append("MST_INACTIVE")

        elif tool_id == "tax_risk_list":
            if output.get("listed") is True:
                added.append("TAX_RISK_LIST")

        elif tool_id == "einvoice_portal":
            if output.get("illegal_flag") is True:
                added.append("TAX_RISK_LIST")
            if (
                output.get("found") is False
                or output.get("processing_status_code") in {2, 4}
                or output.get("invoice_status_code") in {4, 6}
            ):
                added.append("INVOICE_NOT_FOUND_ON_PORTAL")

        elif tool_id == "official_fraud_list":
            if output.get("listed") is True:
                added.append("OFFICIAL_FRAUD_LIST")

        elif tool_id == "cross_alerts":
            if output.get("matched") is True:
                added.append("CROSS_ALERT_HIT")

    # Deduplicate preserving order
    return list(dict.fromkeys(added))


VALID_TAX_STATUS_CODES: frozenset[str] = frozenset(
    {"00", "01", "02", "03", "04", "05", "06", "07", "09", "10"}
)


def is_tool_call_successful(
    tool_call: Mapping[str, Any],
    *,
    expected_tax_id: str | None = None,
    expected_invoice_id: str | None = None,
) -> bool:
    """Evaluate tool-specific success semantics for mandatory prefetch coverage (B1, N4).

    Never treats a generic truthy wrapper (e.g. `{"invoices": []}` or invalid `status_code`) as successful.
    """
    if tool_call.get("error") is not None:
        return False
    output = tool_call.get("output")
    if not isinstance(output, Mapping) or not output:
        return False

    tool_id = str(tool_call.get("tool_id") or "")
    exp_tax = expected_tax_id.strip() if isinstance(expected_tax_id, str) and expected_tax_id.strip() else None

    if tool_id == "tax_id_lookup":
        status_code = output.get("status_code")
        if not isinstance(status_code, str) or status_code not in VALID_TAX_STATUS_CODES:
            return False
        if exp_tax is not None:
            actual_tax = output.get("tax_id")
            if not isinstance(actual_tax, str) or actual_tax.strip() != exp_tax:
                return False
        return True

    if tool_id == "tax_risk_list":
        if not isinstance(output.get("listed"), bool):
            return False
        if exp_tax is not None:
            actual_tax = str(output.get("tax_id") or "").strip()
            if actual_tax != exp_tax:
                return False
        return True

    if tool_id == "einvoice_portal":
        found = output.get("found")
        if not isinstance(found, bool):
            return False
        if found is True:
            return (
                output.get("invoice_status_code") is not None
                or output.get("processing_status_code") is not None
            )
        return True

    if tool_id == "invoices":
        invs = output.get("invoices")
        if not isinstance(invs, list) or len(invs) == 0:
            return False
        if expected_invoice_id is not None:
            return any(
                isinstance(item, Mapping) and item.get("invoice_id") == expected_invoice_id
                for item in invs
            )
        return True

    if tool_id == "vendor_contracts":
        return isinstance(output.get("contracts"), list)

    if tool_id == "three_way_match":
        return isinstance(output.get("missing_goods_receipt"), bool) and isinstance(
            output.get("quantity_above_norm"), bool
        )

    if tool_id == "vendor_registry":
        return (
            "vendor" in output
            and isinstance(output.get("accounts"), list)
            and isinstance(output.get("approved_verifications"), list)
        )

    if tool_id == "cross_alerts":
        return isinstance(output.get("matched"), bool) and isinstance(output.get("hits"), list)

    if tool_id == "official_fraud_list":
        return isinstance(output.get("listed"), bool) and isinstance(output.get("matches"), list)

    if tool_id == "utility_bills":
        return isinstance(output.get("readings"), list)

    if tool_id == "utility_baseline":
        return isinstance(output.get("out_of_range"), bool)

    if tool_id == "account_balance":
        bal = output.get("balance_vnd")
        return isinstance(bal, int) and not isinstance(bal, bool)

    if tool_id == "spending_limits":
        return isinstance(output.get("platform_limits"), Mapping) and isinstance(
            output.get("daily_budget"), Mapping
        )

    if tool_id == "payment_policy_preview":
        dec = output.get("decision")
        return isinstance(dec, str) and bool(dec.strip())

    return bool(output)


@dataclass(frozen=True)
class SystemFindingSpec:
    bot_id: str
    severity: Severity
    reason_codes: tuple[str, ...]
    reason_text: str
    evidence: tuple[dict[str, str], ...] = ()


def evaluate_tool_call_floors(
    tool_calls: Iterable[Mapping[str, Any]],
    *,
    existing_reason_codes: Collection[str] = (),
) -> list[SystemFindingSpec]:
    """Derive system findings for any tool-output floor triggered during a job attempt
    that is not already covered by existing non-superseded findings.

    Ensures a bot that times out or fails after a positive trusted tool call
    (e.g. official_fraud_list, cross_alerts, tax_risk_list, tax_id_lookup, einvoice_portal)
    cannot leave an invoice at yellow/green.
    """
    covered = set(existing_reason_codes)
    evidence_by_code: dict[str, list[dict[str, str]]] = {}

    for tc in tool_calls:
        codes = extract_tool_floor_reason_codes([tc])
        if not codes:
            continue
        tc_id = tc.get("tool_call_id")
        ev_item = (
            {"kind": "tool_call", "ref_id": str(tc_id), "tool_call_id": str(tc_id)}
            if tc_id
            else None
        )
        for code in codes:
            if code in covered:
                continue
            bucket = evidence_by_code.setdefault(code, [])
            if ev_item is not None and ev_item not in bucket:
                bucket.append(ev_item)

    findings: list[SystemFindingSpec] = []
    for code, ev_list in evidence_by_code.items():
        rule = REASON_CODE_RULES.get(code)
        sev = compute_finding_severity("green", (code,))
        label = rule.label_vi if rule is not None else code
        findings.append(
            SystemFindingSpec(
                bot_id="system",
                severity=sev,
                reason_codes=(code,),
                reason_text=f"Sàn kết quả công cụ xác nhận: {label}.",
                evidence=tuple(ev_list),
            )
        )
    return findings


def evaluate_mandatory_prefetch_coverage(
    *,
    required_prefetch_by_bot: Mapping[str, Collection[str]],
    attempt_tool_calls: Iterable[Mapping[str, Any]],
    skipped_bot_ids: Collection[str] = (),
    expected_tax_id: str | None = None,
    expected_invoice_id: str | None = None,
) -> list[SystemFindingSpec]:
    """Ensure every mandatory prefetch tool of every non-skipped required bot succeeded with tool-specific semantics (B1, B3).

    An errored, timed-out, revoked, wrong-target, or empty mandatory prefetch counts as not run (yellow floor).
    """
    skipped = set(skipped_bot_ids)
    tcs_by_bot_tool: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for tc in attempt_tool_calls:
        key = (str(tc.get("bot_id") or ""), str(tc.get("tool_id") or ""))
        tcs_by_bot_tool.setdefault(key, []).append(tc)

    findings: list[SystemFindingSpec] = []
    for bot_id, prefetch_tools in required_prefetch_by_bot.items():
        if bot_id in skipped:
            continue
        failed_timeout: list[str] = []
        failed_other: list[str] = []
        for tool_id in prefetch_tools:
            calls = tcs_by_bot_tool.get((bot_id, tool_id), [])
            succeeded = any(
                is_tool_call_successful(
                    c,
                    expected_tax_id=expected_tax_id,
                    expected_invoice_id=expected_invoice_id,
                )
                for c in calls
            )
            if succeeded:
                continue
            had_timeout = any(
                isinstance(c.get("error"), Mapping) and c["error"].get("code") == "UPSTREAM_TIMEOUT"
                for c in calls
            )
            if had_timeout:
                failed_timeout.append(tool_id)
            else:
                failed_other.append(tool_id)

        if failed_timeout:
            findings.append(
                SystemFindingSpec(
                    bot_id="system",
                    severity="yellow",
                    reason_codes=("BOT_TIMEOUT",),
                    reason_text=(
                        f"Công cụ prefetch bắt buộc của bot '{bot_id}' bị quá thời gian: "
                        f"{', '.join(failed_timeout)}."
                    ),
                )
            )
        if failed_other:
            findings.append(
                SystemFindingSpec(
                    bot_id="system",
                    severity="yellow",
                    reason_codes=("BOT_NOT_RUN",),
                    reason_text=(
                        f"Công cụ prefetch bắt buộc của bot '{bot_id}' chưa hoàn tất thành công: "
                        f"{', '.join(failed_other)}."
                    ),
                )
            )
    return findings


def carry_forward_prior_red_evidence(
    *,
    prior_findings: Iterable[Mapping[str, Any]],
    prior_tool_calls: Iterable[Mapping[str, Any]],
    current_reason_codes: Collection[str] = (),
) -> list[SystemFindingSpec]:
    """Carry forward confirmed red risk evidence from earlier attempts of the same job (B3).

    Previous attempts' OK findings do NOT count toward coverage, but confirmed red evidence
    (red findings or red tool-output floors) is never erased by a retry.
    """
    covered = set(current_reason_codes)
    red_codes: list[str] = []
    evidence_by_code: dict[str, list[dict[str, str]]] = {}

    for f in prior_findings:
        f_codes = list(f.get("reason_codes") or [])
        f_sev = f.get("severity") or compute_finding_severity(f.get("severity_reported") or "green", f_codes)
        if f_sev != "red":
            continue
        for c in f_codes:
            rule = REASON_CODE_RULES.get(c)
            if rule is not None and rule.floor == "red" and c not in covered:
                if c not in red_codes:
                    red_codes.append(c)

    for tc in prior_tool_calls:
        codes = extract_tool_floor_reason_codes([tc])
        tc_id = tc.get("tool_call_id")
        ev_item = (
            {"kind": "tool_call", "ref_id": str(tc_id), "tool_call_id": str(tc_id)}
            if tc_id
            else None
        )
        for c in codes:
            rule = REASON_CODE_RULES.get(c)
            if rule is not None and rule.floor == "red" and c not in covered:
                if c not in red_codes:
                    red_codes.append(c)
                if ev_item is not None:
                    bucket = evidence_by_code.setdefault(c, [])
                    if ev_item not in bucket:
                        bucket.append(ev_item)

    specs: list[SystemFindingSpec] = []
    for code in red_codes:
        rule = REASON_CODE_RULES.get(code)
        label = rule.label_vi if rule is not None else code
        specs.append(
            SystemFindingSpec(
                bot_id="system",
                severity="red",
                reason_codes=(code,),
                reason_text=f"Kế thừa bằng chứng rủi ro đỏ đã xác nhận từ lượt chạy trước: {label}.",
                evidence=tuple(evidence_by_code.get(code, ())),
            )
        )
    return specs


def evaluate_system_checks(
    *,
    invoice_bank_account_numbers: Collection[str],
    verified_account_numbers: Collection[str],
    approved_verification_account_numbers: Collection[str],
    has_published_cross_alert: bool,
    has_hard_block: bool,
) -> list[SystemFindingSpec]:
    """Deterministic system checks at :complete using DB data only (internal-api.md §4)."""
    findings: list[SystemFindingSpec] = []

    if has_published_cross_alert:
        findings.append(
            SystemFindingSpec(
                bot_id="system",
                severity="yellow",
                reason_codes=("CROSS_ALERT_HIT",),
                reason_text="Chỉ báo trên hóa đơn khớp cảnh báo chéo đang hiệu lực trên mạng lưới MoMo.",
            )
        )

    if has_hard_block:
        findings.append(
            SystemFindingSpec(
                bot_id="system",
                severity="red",
                reason_codes=("OFFICIAL_FRAUD_LIST",),
                reason_text="Chỉ báo trên hóa đơn thuộc danh sách chặn cứng chính thức.",
            )
        )

    allowed_numbers = {
        n.strip() for n in verified_account_numbers if n and n.strip()
    } | {
        n.strip() for n in approved_verification_account_numbers if n and n.strip()
    }
    unmatched = [
        n.strip()
        for n in invoice_bank_account_numbers
        if n and n.strip() and n.strip() not in allowed_numbers
    ]
    if unmatched:
        findings.append(
            SystemFindingSpec(
                bot_id="system",
                severity="red",
                reason_codes=("PAYEE_CHANGE_REQUEST",),
                reason_text=(
                    "Số tài khoản trên hóa đơn không trùng tài khoản đã xác minh trong danh bạ NCC "
                    "và chưa có xác minh đổi tài khoản F12."
                ),
            )
        )

    return findings


def check_required_bots(
    *,
    required_bot_ids: Collection[str],
    submitted_bot_ids: Collection[str],
    skipped_bot_ids: Collection[str],
) -> list[SystemFindingSpec]:
    """Emit yellow BOT_DISABLED / BOT_NOT_RUN findings for missing required bots (internal-api.md §1)."""
    submitted = set(submitted_bot_ids)
    skipped = set(skipped_bot_ids)
    findings: list[SystemFindingSpec] = []
    for bot_id in required_bot_ids:
        if bot_id in submitted:
            continue
        if bot_id in skipped:
            findings.append(
                SystemFindingSpec(
                    bot_id=bot_id,
                    severity="yellow",
                    reason_codes=("BOT_DISABLED",),
                    reason_text=f"Bot bắt buộc '{bot_id}' đang bị tạm tắt hoặc chặn bởi kill switch.",
                )
            )
        else:
            findings.append(
                SystemFindingSpec(
                    bot_id=bot_id,
                    severity="yellow",
                    reason_codes=("BOT_NOT_RUN",),
                    reason_text=f"Bot bắt buộc '{bot_id}' chưa nộp kết quả kiểm tra.",
                )
            )
    return findings


@dataclass(frozen=True)
class FindingInput:
    severity_reported: Severity
    reason_codes: tuple[str, ...]
    severity_computed: Severity | None = None


@dataclass(frozen=True)
class AggregationResult:
    final_severity: Severity
    reason_codes: tuple[str, ...]
    verification_required: bool
    qt03_codes: tuple[str, ...]


def aggregate_findings(findings: Iterable[FindingInput]) -> AggregationResult:
    """Monotone max-severity aggregation across all findings (invariant #5).

    Adding ANY Finding to the input never lowers `final_severity`.
    """
    final: Severity = "green"
    all_codes: list[str] = []

    for f in findings:
        sev = (
            f.severity_computed
            if f.severity_computed is not None
            else compute_finding_severity(f.severity_reported, f.reason_codes)
        )
        # Re-enforce floor even if caller passed severity_computed
        sev = max_severity(
            sev,
            compute_finding_severity("green", f.reason_codes),
        )
        final = max_severity(final, sev)
        all_codes.extend(f.reason_codes)

    normalized = normalize_reason_codes(all_codes)
    # If there are any non-OK codes, ensure final_severity respects all reason floors
    for code in normalized:
        if code == "OK":
            continue
        rule = REASON_CODE_RULES.get(code)
        code_floor: Severity = rule.floor if rule is not None else "yellow"
        final = max_severity(final, code_floor)

    qt03 = tuple(c for c in normalized if c in QT03_REASON_CODES)
    return AggregationResult(
        final_severity=final,
        reason_codes=tuple(normalized),
        verification_required=("CROSS_ALERT_HIT" in normalized),
        qt03_codes=qt03,
    )


def _within_window(now_vn: datetime, start_hhmm: str, end_hhmm: str) -> bool:
    sh, sm = (int(p) for p in start_hhmm.split(":"))
    eh, em = (int(p) for p in end_hhmm.split(":"))
    cur = now_vn.hour * 60 + now_vn.minute
    start = sh * 60 + sm
    end = eh * 60 + em
    if start <= end:
        return start <= cur <= end
    return cur >= start or cur <= end


def determine_post_investigation_status(
    *,
    final_severity: Severity,
    vendor_id: str | None,
    total_vnd: int | None,
    mandate: Mapping[str, Any] | None,
    platform_per_invoice_vnd: int,
    is_vendor_suspended: bool,
    now_vn: datetime,
) -> Literal["auto_pay_eligible", "pending_approval", "blocked", "no_payment_due"]:
    """Compute invoice status after investigation per docs/05-api/merchant-api.md §2 table."""
    if final_severity == "red":
        return "blocked"
    if total_vnd is not None and total_vnd <= 0:
        return "no_payment_due"   # downward adjustment / discount / 0 đ: nothing to pay, keep out of the queue
    if final_severity == "yellow":
        return "pending_approval"

    # Green invoice: check auto_pay eligibility
    if mandate is None or mandate.get("mode") != "auto_pay":
        return "pending_approval"
    if not vendor_id or is_vendor_suspended:
        return "pending_approval"
    if vendor_id not in (mandate.get("auto_pay_vendor_ids") or []):
        return "pending_approval"
    if total_vnd is None or total_vnd <= 0:
        return "pending_approval"

    mandate_per_invoice = int((mandate.get("limits") or {}).get("per_invoice_vnd", 0))
    effective_ceiling = min(mandate_per_invoice, platform_per_invoice_vnd)
    if total_vnd > effective_ceiling:
        return "pending_approval"

    window = mandate.get("auto_pay_window") or {}
    start = window.get("start")
    end = window.get("end")
    if start and end and not _within_window(now_vn, start, end):
        return "pending_approval"

    return "auto_pay_eligible"

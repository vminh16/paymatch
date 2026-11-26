"""Pure domain unit tests & safety invariants (zero I/O)."""

from __future__ import annotations

import ast
import json
import pathlib
from dataclasses import replace
from datetime import date, datetime

import pytest
from paymatch_contracts.gate import (
    AllowedMethod,
    Channel,
    Code as GateReasonCode,
    EscrowStatus,
    GateDecision,
    Layer as GateReasonLayer,
    PaymentIntentStatus,
)

from gate.domain import (
    DailyBudgetSnapshot,
    EscrowRecord,
    GoodsReceiptSnapshot,
    IndicatorRef,
    InvalidStateTransitionError,
    InvoiceSnapshot,
    KillSwitchSnapshot,
    PlatformLimitsSnapshot,
    PolicyState,
    RiskSignals,
    VN_TZ,
    VerificationRecord,
    compute_escrow_intent_hash,
    compute_invoice_intent_hash,
    evaluate_escrow_hold,
    evaluate_invoice,
    extract_indicators,
    format_transfer_memo,
    hash_account_indicator,
    hash_tax_id_indicator,
    require_escrow_transition,
    require_intent_transition,
    select_channel,
    validate_escrow_create,
    validate_escrow_release,
    validate_intent_authorization,
)

from gate_fixtures import (
    ACC_COFFEE,
    ACC_POS_CARD,
    ACC_SYRUP_ESCROW,
    APV_01,
    DOC_SHA_CUPS,
    DOC_SHA_SYRUP,
    GRN_01,
    GRN_OTHER,
    INV_COFFEE,
    INV_CUPS,
    INV_POS,
    INV_SYRUP,
    JOB_01,
    JOB_02,
    NOW_VN,
    PO_01,
    ROOT,
    STORE_01,
    TENANT_A,
    VENDOR_COFFEE,
    VENDOR_POS,
    VENDOR_SYRUP,
    make_approval_for_invoice,
    make_coffee_invoice,
    make_coffee_vendor,
    make_default_mandate,
    make_escrow_create_approval,
    make_pos_vendor,
    make_syrup_escrow_vendor,
)


def _policy(
    *,
    per_invoice: int = 30_000_000,
    per_day: int = 50_000_000,
    kill_switches: tuple[KillSwitchSnapshot, ...] = (),
    available: bool = True,
) -> PolicyState:
    return PolicyState(
        available=available,
        platform_limits=(
            PlatformLimitsSnapshot(
                auto_pay_per_invoice_vnd=per_invoice,
                auto_pay_per_day_vnd=per_day,
            )
            if available
            else None
        ),
        kill_switches=kill_switches,
    )


def test_hexagonal_boundary_domain_has_no_adapter_or_io_imports():
    domain_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "gate" / "domain"
    forbidden = {"psycopg", "httpx", "fastapi", "uvicorn", "gate.adapters"}
    for py_file in domain_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden
                    assert not alias.name.startswith("gate.adapters")
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden
                assert not node.module.startswith("gate.adapters")


def test_intent_hash_matches_shared_test_vectors():
    vectors = json.loads((ROOT / "contracts" / "test-vectors" / "hashing.json").read_text())
    by_name = {v["name"]: v for v in vectors["domain_vectors"]}

    cups_vec = by_name["cups_invoice_intent_hash"]
    assert (
        compute_invoice_intent_hash(**cups_vec["args"]) == cups_vec["expected_hash"]
    )
    null_vec = by_name["unknown_vendor_null_payee_intent_hash"]
    assert (
        compute_invoice_intent_hash(**null_vec["args"]) == null_vec["expected_hash"]
    )
    esc_vec = by_name["escrow_intent_hash"]
    assert (
        compute_escrow_intent_hash(
            purchase_order_id=esc_vec["args"]["purchase_order_id"],
            payee_account_id=esc_vec["args"]["payee_account_id"],
            amount_vnd=esc_vec["args"]["amount_vnd"],
        )
        == esc_vec["expected_hash"]
    )


def test_evaluate_green_coffee_autopay_allows():
    vendor, acc = make_coffee_vendor()
    inv = make_coffee_invoice()
    res = evaluate_invoice(
        invoice=inv,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=extract_indicators(seller_tax_id=inv.seller_tax_id, vendor=vendor, payee_account=acc),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert res.decision == GateDecision.ALLOW
    assert res.payee_account_id == ACC_COFFEE
    assert res.channel == Channel.bank_transfer
    assert res.allowed_methods == (AllowedMethod.single, AllowedMethod.bulk)
    assert res.reasons == ()
    assert format_transfer_memo(inv) == "0999010001 · 1C26TTN · 00001425"


def test_invariant_platform_ceiling_overrides_higher_mandate_limit():
    """Mandate sets 40tr/invoice & 60tr/day -> still blocked at 30tr/50tr platform ceiling."""
    vendor, acc = make_coffee_vendor()
    inv = make_coffee_invoice(amount_vnd=35_000_000)
    mandate_40m = make_default_mandate(per_invoice_vnd=40_000_000, per_day_vnd=60_000_000)
    apv = make_approval_for_invoice(inv, method="mandate")

    eval_res = evaluate_invoice(
        invoice=inv,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=mandate_40m,
        policy=_policy(per_invoice=30_000_000, per_day=50_000_000),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert eval_res.decision == GateDecision.REQUIRE_APPROVAL
    assert any(
        r.code == GateReasonCode.ABOVE_PER_INVOICE_LIMIT
        and r.layer == GateReasonLayer.platform_policy
        for r in eval_res.reasons
    )

    auth_res = validate_intent_authorization(
        invoice=inv,
        approval=apv,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=mandate_40m,
        policy=_policy(per_invoice=30_000_000, per_day=50_000_000),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert auth_res.decision == GateDecision.DENY
    assert any(
        r.code == GateReasonCode.ABOVE_PER_INVOICE_LIMIT
        and r.layer == GateReasonLayer.platform_policy
        for r in auth_res.reasons
    )

    # Daily platform ceiling: 25tr already used + 26.5tr = 51.5tr > 50tr platform ceiling (even with 60tr mandate)
    inv_small = make_coffee_invoice(amount_vnd=26_500_000)
    apv_small = make_approval_for_invoice(inv_small, method="mandate")
    auth_daily = validate_intent_authorization(
        invoice=inv_small,
        approval=apv_small,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=mandate_40m,
        policy=_policy(per_invoice=30_000_000, per_day=50_000_000),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date(), auto_pay_used_vnd=25_000_000),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert auth_daily.decision == GateDecision.DENY
    assert any(
        r.code == GateReasonCode.ABOVE_DAILY_LIMIT and r.layer == GateReasonLayer.platform_policy
        for r in auth_daily.reasons
    )


def test_invariant_3_payee_only_from_verified_registry_matching_mst():
    """Invoice with unknown vendor or mismatched MST or unverified account -> DENY."""
    vendor, acc = make_coffee_vendor()
    inv_mismatch = replace(make_coffee_invoice(), seller_tax_id="0999999999")
    res = evaluate_invoice(
        invoice=inv_mismatch,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert res.decision == GateDecision.DENY
    assert res.payee_account_id is None
    assert any(r.code == GateReasonCode.PAYEE_NOT_VERIFIED for r in res.reasons)

    # Approval referencing rogue account ID not in registry -> DENY
    inv_ok = make_coffee_invoice()
    rogue_apv = make_approval_for_invoice(
        inv_ok,
        payee_account_id="vac_01M88R0GVE0000000000000001",
        method="single",
    )
    auth = validate_intent_authorization(
        invoice=inv_ok,
        approval=rogue_apv,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert auth.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.PAYEE_NOT_VERIFIED for r in auth.reasons)


def test_invariant_red_blocked_invoice_never_allow_even_with_active_approval():
    vendor, acc = make_coffee_vendor()
    blocked_inv = make_coffee_invoice(
        status="blocked",
        severity="red",
        reason_codes=("PAYEE_CHANGE_REQUEST",),
    )
    apv = make_approval_for_invoice(blocked_inv, method="single")

    auth = validate_intent_authorization(
        invoice=blocked_inv,
        approval=apv,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert auth.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.BLOCKED_INVOICE for r in auth.reasons)


def test_invariant_cross_alert_without_verification_denies_and_with_confirmed_allows():
    vendor, acc = make_coffee_vendor()
    inv = make_coffee_invoice(status="pending_approval", severity="yellow", reason_codes=("CROSS_ALERT_HIT",))
    tax_ind = IndicatorRef(kind="tax_id", value_hash=hash_tax_id_indicator(inv.seller_tax_id))
    signals = RiskSignals(cross_alert_hits=(tax_ind,))

    # Evaluate: REQUIRE_APPROVAL, single only (never bulk!), verification_required=True
    ev = evaluate_invoice(
        invoice=inv,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=signals,
        indicators=(tax_ind,),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert ev.decision == GateDecision.REQUIRE_APPROVAL
    assert ev.verification_required is True
    assert ev.allowed_methods == (AllowedMethod.single,)
    assert any(r.code == GateReasonCode.CROSS_ALERT_UNVERIFIED for r in ev.reasons)

    # Without verification -> DENY
    apv_no_ver = make_approval_for_invoice(inv, method="single", verification=None)
    auth_denied = validate_intent_authorization(
        invoice=inv,
        approval=apv_no_ver,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=signals,
        indicators=(tax_ind,),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert auth_denied.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.CROSS_ALERT_UNVERIFIED for r in auth_denied.reasons)

    # With confirmed callback verification -> ALLOW
    apv_verified = make_approval_for_invoice(
        inv,
        method="single",
        verification=VerificationRecord(
            called_phone_on_file=True,
            result="confirmed",
            note="Đã gọi xác nhận",
            at=NOW_VN.isoformat(),
        ),
    )
    auth_ok = validate_intent_authorization(
        invoice=inv,
        approval=apv_verified,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=signals,
        indicators=(tax_ind,),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert auth_ok.decision == GateDecision.ALLOW


def test_invariant_escrow_only_account_denied_for_normal_transfer_and_release_requires_grn():
    vendor, escrow_acc, po = make_syrup_escrow_vendor()
    inv = InvoiceSnapshot(
        invoice_id=INV_SYRUP,
        tenant_id=TENANT_A,
        vendor_id=VENDOR_SYRUP,
        purchase_order_id=PO_01,
        seller_tax_id=vendor.tax_id,
        symbol="1C26TSR",
        number="00000001",
        invoice_type="goods",
        total_vnd=8_800_000,
        status="pending_approval",
        severity="yellow",
        reason_codes=("OK",),
        document_sha256=DOC_SHA_SYRUP,
    )

    # 1. escrow_only account + normal bank_transfer -> DENY
    apv_normal = make_approval_for_invoice(
        inv, payee_account_id=ACC_SYRUP_ESCROW, channel="bank_transfer", method="single"
    )
    res_normal = validate_intent_authorization(
        invoice=inv,
        approval=apv_normal,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(escrow_acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert res_normal.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.PAYEE_NOT_VERIFIED for r in res_normal.reasons)
    assert any(r.code == GateReasonCode.CHANNEL_NOT_ALLOWED for r in res_normal.reasons)

    # 2. Escrow preview & create -> ALLOWED with escrow_only account
    esc_eval = evaluate_escrow_hold(
        po=po,
        vendor=vendor,
        vendor_account=escrow_acc,
        amount_vnd=8_800_000,
        has_open_escrow=False,
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        now=NOW_VN,
    )
    assert esc_eval.decision == GateDecision.REQUIRE_APPROVAL
    assert esc_eval.channel == Channel.escrow

    create_apv = make_escrow_create_approval(po)
    esc_create = validate_escrow_create(
        approval=create_apv,
        po=po,
        vendor=vendor,
        vendor_account=escrow_acc,
        has_open_escrow=False,
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        now=NOW_VN,
    )
    assert esc_create.decision == GateDecision.ALLOW

    # 3. Release without goods_receipt -> DENY
    held_escrow = EscrowRecord(
        escrow_id="esc_01M88A6SAP3R27VDQ55VAKCF0P",
        tenant_id=TENANT_A,
        purchase_order_id=PO_01,
        vendor_account_id=ACC_SYRUP_ESCROW,
        approval_id=create_apv.approval_id,
        amount_vnd=8_800_000,
        status=EscrowStatus.held,
        source_invoice_id=INV_SYRUP,
        release_invoice_id=None,
        goods_receipt_id=None,
        rail_escrow_id="resc_01M88A6SAP3R27VDQ55VAKCF0P",
        failure_code=None,
        expires_on=date(2026, 12, 10),
        created_at=NOW_VN,
        released_at=None,
        refunded_at=None,
    )
    rel_apv = make_approval_for_invoice(
        inv, payee_account_id=ACC_SYRUP_ESCROW, channel="escrow", method="single"
    )
    rel_no_grn = validate_escrow_release(
        escrow=held_escrow,
        release_approval=rel_apv,
        release_invoice=inv,
        goods_receipt=None,
        po=po,
        vendor=vendor,
        vendor_account=escrow_acc,
        latest_completed_job_id=JOB_01,
        has_settled_ledger=False,
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        now=NOW_VN,
    )
    assert rel_no_grn.decision == GateDecision.DENY

    # Wrong PO GRN -> DENY
    wrong_grn = GoodsReceiptSnapshot(
        goods_receipt_id=GRN_OTHER,
        tenant_id=TENANT_A,
        purchase_order_id="po_01M88OTHER0000000000000001",
        store_id=STORE_01,
    )
    rel_wrong_grn = validate_escrow_release(
        escrow=held_escrow,
        release_approval=rel_apv,
        release_invoice=inv,
        goods_receipt=wrong_grn,
        po=po,
        vendor=vendor,
        vendor_account=escrow_acc,
        latest_completed_job_id=JOB_01,
        has_settled_ledger=False,
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        now=NOW_VN,
    )
    assert rel_wrong_grn.decision == GateDecision.DENY

    # Matching GRN -> ALLOW
    good_grn = GoodsReceiptSnapshot(
        goods_receipt_id=GRN_01,
        tenant_id=TENANT_A,
        purchase_order_id=PO_01,
        store_id=STORE_01,
    )
    rel_ok = validate_escrow_release(
        escrow=held_escrow,
        release_approval=rel_apv,
        release_invoice=inv,
        goods_receipt=good_grn,
        po=po,
        vendor=vendor,
        vendor_account=escrow_acc,
        latest_completed_job_id=JOB_01,
        has_settled_ledger=False,
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        now=NOW_VN,
    )
    assert rel_ok.decision == GateDecision.ALLOW

    # review_only mandate denies escrow release!
    rel_review_only = validate_escrow_release(
        escrow=held_escrow,
        release_approval=rel_apv,
        release_invoice=inv,
        goods_receipt=good_grn,
        po=po,
        vendor=vendor,
        vendor_account=escrow_acc,
        latest_completed_job_id=JOB_01,
        has_settled_ledger=False,
        mandate=make_default_mandate(mode="review_only"),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        now=NOW_VN,
    )
    assert rel_review_only.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.MANDATE_NOT_AUTO_PAY for r in rel_review_only.reasons)

    # B1: ESCROW_MISMATCH when release approved amount < held amount (must be EXACT equality)
    smaller_inv = replace(inv, total_vnd=8_000_000)
    smaller_apv = make_approval_for_invoice(
        smaller_inv, payee_account_id=ACC_SYRUP_ESCROW, channel="escrow", method="single"
    )
    rel_amt_mismatch = validate_escrow_release(
        escrow=held_escrow,
        release_approval=smaller_apv,
        release_invoice=smaller_inv,
        goods_receipt=good_grn,
        po=po,
        vendor=vendor,
        vendor_account=escrow_acc,
        latest_completed_job_id=JOB_01,
        has_settled_ledger=False,
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        now=NOW_VN,
    )
    assert rel_amt_mismatch.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.ESCROW_MISMATCH for r in rel_amt_mismatch.reasons)

    # B1: ESCROW_MISMATCH when release approved payee != held account
    wrong_payee_apv = make_approval_for_invoice(
        inv, payee_account_id=ACC_COFFEE, channel="escrow", method="single"
    )
    rel_payee_mismatch = validate_escrow_release(
        escrow=held_escrow,
        release_approval=wrong_payee_apv,
        release_invoice=inv,
        goods_receipt=good_grn,
        po=po,
        vendor=vendor,
        vendor_account=escrow_acc,
        latest_completed_job_id=JOB_01,
        has_settled_ledger=False,
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        now=NOW_VN,
    )
    assert rel_payee_mismatch.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.ESCROW_MISMATCH for r in rel_payee_mismatch.reasons)

    # B1: missing / wrong GRN also yields ESCROW_MISMATCH
    assert any(r.code == GateReasonCode.ESCROW_MISMATCH for r in rel_no_grn.reasons)
    assert any(r.code == GateReasonCode.ESCROW_MISMATCH for r in rel_wrong_grn.reasons)


def test_invariant_i1_amount_outside_safe_integer_range_denied():
    vendor, acc = make_coffee_vendor()
    huge_inv = make_coffee_invoice(amount_vnd=9_007_199_254_740_992)  # 2^53 (unsafe JS int)
    res = evaluate_invoice(
        invoice=huge_inv,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert res.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.BLOCKED_INVOICE for r in res.reasons)


def test_invariant_10_fail_closed_policy_unavailable():
    vendor, acc = make_coffee_vendor()
    inv = make_coffee_invoice()
    res = evaluate_invoice(
        invoice=inv,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(available=False),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert res.decision == GateDecision.DENY
    assert res.policy_unavailable is True
    assert any(r.code == GateReasonCode.POLICY_UNAVAILABLE for r in res.reasons)


def test_invariant_kill_switches_auto_pay_global_vs_tenant_vs_indicator():
    vendor, acc = make_coffee_vendor()
    inv = make_coffee_invoice()
    inds = extract_indicators(seller_tax_id=inv.seller_tax_id, vendor=vendor, payee_account=acc)
    apv_mandate = make_approval_for_invoice(inv, method="mandate")
    apv_single = make_approval_for_invoice(inv, method="single")

    # 1. auto_pay_global: blocks auto-pay (REQUIRE_APPROVAL on evaluate; DENY+kill_switch on mandate), allows single!
    ks_global = KillSwitchSnapshot(kill_switch_id="ksw_01", scope="auto_pay_global", target_id=None)
    ev_global = evaluate_invoice(
        invoice=inv,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(kill_switches=(ks_global,)),
        risk_signals=RiskSignals(),
        indicators=inds,
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert ev_global.decision == GateDecision.REQUIRE_APPROVAL
    assert any(r.code == GateReasonCode.KILL_SWITCH for r in ev_global.reasons)

    auth_mandate = validate_intent_authorization(
        invoice=inv,
        approval=apv_mandate,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(kill_switches=(ks_global,)),
        risk_signals=RiskSignals(),
        indicators=inds,
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert auth_mandate.decision == GateDecision.DENY
    assert auth_mandate.kill_switch_blocked is True

    auth_single = validate_intent_authorization(
        invoice=inv,
        approval=apv_single,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(kill_switches=(ks_global,)),
        risk_signals=RiskSignals(),
        indicators=inds,
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert auth_single.decision == GateDecision.ALLOW

    # 2. tenant kill switch: blocks even manual single!
    ks_tenant = KillSwitchSnapshot(kill_switch_id="ksw_02", scope="tenant", target_id=TENANT_A)
    auth_tenant = validate_intent_authorization(
        invoice=inv,
        approval=apv_single,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(kill_switches=(ks_tenant,)),
        risk_signals=RiskSignals(),
        indicators=inds,
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert auth_tenant.decision == GateDecision.DENY
    assert auth_tenant.kill_switch_blocked is True

    # 3. indicator kill switch (matched by account_hash): blocks even manual single!
    acc_hash = hash_account_indicator(acc.bank_code or "", acc.account_number or "")
    ks_ind = KillSwitchSnapshot(
        kill_switch_id="ksw_03",
        scope="indicator",
        target_id=acc_hash,
        indicator_kind="account_hash",
        value_hash=acc_hash,
    )
    auth_ind = validate_intent_authorization(
        invoice=inv,
        approval=apv_single,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(kill_switches=(ks_ind,)),
        risk_signals=RiskSignals(),
        indicators=inds,
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert auth_ind.decision == GateDecision.DENY
    assert auth_ind.kill_switch_blocked is True


def test_invariant_stale_non_active_or_old_job_approval_denies():
    vendor, acc = make_coffee_vendor()
    inv = make_coffee_invoice()

    # Superseded approval -> DENY
    apv_sup = make_approval_for_invoice(inv, method="single", status="superseded")
    res_sup = validate_intent_authorization(
        invoice=inv,
        approval=apv_sup,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert res_sup.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.APPROVAL_STALE for r in res_sup.reasons)

    # Approval from old job (JOB_01) when latest completed job is JOB_02 -> DENY
    apv_old_job = make_approval_for_invoice(inv, method="single", job_id=JOB_01)
    res_old = validate_intent_authorization(
        invoice=inv,
        approval=apv_old_job,
        latest_completed_job_id=JOB_02,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert res_old.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.APPROVAL_STALE for r in res_old.reasons)

    # Tampered intent_hash (e.g. amount changed) -> DENY
    apv_bad_hash = make_approval_for_invoice(inv, method="single", intent_hash="f" * 64)
    res_hash = validate_intent_authorization(
        invoice=inv,
        approval=apv_bad_hash,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert res_hash.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.APPROVAL_STALE for r in res_hash.reasons)


def test_channel_selection_bulk_rules_time_window_and_state_machines():
    # Channel selection: software -> virtual_card, goods -> bank_transfer
    pos_vendor, pos_acc = make_pos_vendor()
    pos_inv = InvoiceSnapshot(
        invoice_id=INV_POS,
        tenant_id=TENANT_A,
        vendor_id=VENDOR_POS,
        purchase_order_id=None,
        seller_tax_id=pos_vendor.tax_id,
        symbol="1C26TSV",
        number="00000112",
        invoice_type="software",
        total_vnd=12_000_000,
        status="scheduled",
        severity="green",
        reason_codes=("OK",),
        document_sha256="b" * 64,
    )
    mandate = make_default_mandate()
    assert select_channel(invoice=pos_inv, mandate=mandate, held_po_escrow=None) == Channel.virtual_card

    # Outside time window (23:30 VN) -> REQUIRE_APPROVAL with OUTSIDE_TIME_WINDOW
    late_night = datetime(2026, 11, 26, 23, 30, 0, tzinfo=VN_TZ)
    ev_late = evaluate_invoice(
        invoice=pos_inv,
        vendor=pos_vendor,
        vendor_accounts=(pos_acc,),
        mandate=mandate,
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=late_night.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=late_night,
    )
    assert ev_late.decision == GateDecision.REQUIRE_APPROVAL
    assert ev_late.channel == Channel.virtual_card
    assert ev_late.payee_account_id == ACC_POS_CARD
    assert any(r.code == GateReasonCode.OUTSIDE_TIME_WINDOW for r in ev_late.reasons)

    # Yellow NON_XML_SOURCE under 2tr -> bulk allowed; over 2tr -> single only
    vendor, acc = make_coffee_vendor()
    inv_pdf_small = make_coffee_invoice(
        invoice_id=INV_CUPS,
        amount_vnd=1_450_000,
        status="pending_approval",
        severity="yellow",
        reason_codes=("NON_XML_SOURCE",),
    )
    ev_pdf_small = evaluate_invoice(
        invoice=inv_pdf_small,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=mandate,
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert ev_pdf_small.decision == GateDecision.REQUIRE_APPROVAL
    assert AllowedMethod.bulk in ev_pdf_small.allowed_methods

    inv_pdf_large = replace(inv_pdf_small, total_vnd=3_000_000)
    ev_pdf_large = evaluate_invoice(
        invoice=inv_pdf_large,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=mandate,
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
    )
    assert ev_pdf_large.allowed_methods == (AllowedMethod.single,)

    # State machine guards
    require_intent_transition(PaymentIntentStatus.authorized, PaymentIntentStatus.executing)
    require_intent_transition(PaymentIntentStatus.executing, PaymentIntentStatus.settled)
    with pytest.raises(InvalidStateTransitionError):
        require_intent_transition(PaymentIntentStatus.executing, PaymentIntentStatus.expired)
    with pytest.raises(InvalidStateTransitionError):
        require_intent_transition(PaymentIntentStatus.settled, PaymentIntentStatus.failed)

    require_escrow_transition(EscrowStatus.pending, EscrowStatus.held)
    require_escrow_transition(EscrowStatus.held, EscrowStatus.released)
    with pytest.raises(InvalidStateTransitionError):
        require_escrow_transition(EscrowStatus.released, EscrowStatus.refunded)


def test_b5_manual_owner_proof_and_tainted_approval_denied():
    vendor, acc = make_coffee_vendor()
    inv = make_coffee_invoice(status="pending_approval", severity="yellow")

    # Non-owner approver -> DENY
    apv_manual = make_approval_for_invoice(inv, method="single")
    res_non_owner = validate_intent_authorization(
        invoice=inv,
        approval=apv_manual,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
        approver_is_owner=False,
    )
    assert res_non_owner.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.APPROVAL_STALE for r in res_non_owner.reasons)

    # Missing approver_user_id on manual approval -> DENY
    apv_null_user = replace(apv_manual, approver_user_id=None)
    res_null = validate_intent_authorization(
        invoice=inv,
        approval=apv_null_user,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
        approver_is_owner=True,
    )
    assert res_null.decision == GateDecision.DENY

    # Tainted approval (previously failed/denied/settled) -> DENY
    res_tainted = validate_intent_authorization(
        invoice=inv,
        approval=apv_manual,
        latest_completed_job_id=JOB_01,
        vendor=vendor,
        vendor_accounts=(acc,),
        mandate=make_default_mandate(),
        policy=_policy(),
        risk_signals=RiskSignals(),
        indicators=(),
        daily_budget=DailyBudgetSnapshot(budget_date=NOW_VN.date()),
        vendor_suspended=False,
        has_settled_ledger=False,
        held_po_escrow=None,
        now=NOW_VN,
        approver_is_owner=True,
        approval_tainted=True,
    )
    assert res_tainted.decision == GateDecision.DENY
    assert any(r.code == GateReasonCode.APPROVAL_STALE for r in res_tainted.reasons)

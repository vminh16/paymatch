"""Unit and property tests for pure severity aggregation, reason floors/ceilings, tool floors, and system checks."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from core.risk.domain.aggregation import (
    REASON_CODE_RULES,
    SEVERITY_RANK,
    FindingInput,
    Severity,
    aggregate_findings,
    check_required_bots,
    compute_finding_severity,
    determine_post_investigation_status,
    evaluate_system_checks,
    extract_tool_floor_reason_codes,
)

VN_TZ = timezone(timedelta(hours=7))


def test_invariant_monotone_aggregation_property() -> None:
    """Invariant #5 (repo-and-testing.md §4): adding ANY Finding never lowers final severity."""
    rng = random.Random(20261126)
    all_codes = list(REASON_CODE_RULES.keys())
    severities: list[Severity] = ["green", "yellow", "red"]

    for _ in range(500):
        base_len = rng.randint(0, 6)
        base_findings = [
            FindingInput(
                severity_reported=rng.choice(severities),
                reason_codes=tuple(rng.sample(all_codes, k=rng.randint(1, 3))),
            )
            for _ in range(base_len)
        ]
        extra = FindingInput(
            severity_reported=rng.choice(severities),
            reason_codes=tuple(rng.sample(all_codes, k=rng.randint(1, 3))),
        )
        before = aggregate_findings(base_findings)
        after = aggregate_findings([*base_findings, extra])
        assert SEVERITY_RANK[after.final_severity] >= SEVERITY_RANK[before.final_severity]


def test_invariant_reason_code_floor_and_cross_alert_ceiling() -> None:
    """Invariant: HIDDEN_INSTRUCTION reported green -> red; solo CROSS_ALERT_HIT reported red -> yellow."""
    assert compute_finding_severity("green", ["HIDDEN_INSTRUCTION"]) == "red"
    assert compute_finding_severity("green", ["PAYEE_CHANGE_REQUEST"]) == "red"
    assert compute_finding_severity("green", ["PERSONAL_ACCOUNT"]) == "red"
    assert compute_finding_severity("green", ["OFFICIAL_FRAUD_LIST"]) == "red"
    assert compute_finding_severity("green", ["TAX_RISK_LIST"]) == "red"
    assert compute_finding_severity("green", ["PRICE_ABOVE_CONTRACT"]) == "yellow"
    assert compute_finding_severity("green", ["NON_XML_SOURCE"]) == "yellow"

    # CROSS_ALERT_HIT alone is capped at yellow even if bot claims red
    assert compute_finding_severity("red", ["CROSS_ALERT_HIT"]) == "yellow"
    assert compute_finding_severity("green", ["CROSS_ALERT_HIT"]) == "yellow"
    # Combined with a red reason, red wins
    assert compute_finding_severity("green", ["CROSS_ALERT_HIT", "PERSONAL_ACCOUNT"]) == "red"


def test_tool_output_floors_internal_api_sec3() -> None:
    tool_calls = [
        {
            "tool_id": "price_check",
            "error": None,
            "output": {
                "items": [
                    {
                        "delta_pct": "21.739130",
                        "pack_qty_contract": "1000.000000",
                        "pack_qty_parsed": "800.000000",
                    }
                ]
            },
        },
        {
            "tool_id": "three_way_match",
            "error": None,
            "output": {"quantity_above_norm": True, "missing_goods_receipt": True},
        },
        {
            "tool_id": "utility_baseline",
            "error": None,
            "output": {"out_of_range": True},
        },
        {"tool_id": "tax_id_lookup", "error": None, "output": {"status_code": "06"}},
        {"tool_id": "tax_risk_list", "error": None, "output": {"listed": True}},
        {
            "tool_id": "einvoice_portal",
            "error": None,
            "output": {"found": True, "invoice_status_code": 6, "illegal_flag": True},
        },
    ]
    codes = set(extract_tool_floor_reason_codes(tool_calls))
    assert codes == {
        "PRICE_ABOVE_CONTRACT",
        "PACK_SIZE_CHANGED",
        "QUANTITY_ABOVE_NORM",
        "NO_GOODS_RECEIPT",
        "UTILITY_OUT_OF_RANGE",
        "MST_INACTIVE",
        "TAX_RISK_LIST",
        "INVOICE_NOT_FOUND_ON_PORTAL",
    }


def test_system_checks_catch_all_ok_runtime() -> None:
    """System checks at :complete catch cross alerts, hard blocks, and unknown bank accounts."""
    sys_findings = evaluate_system_checks(
        invoice_bank_account_numbers=["998812345601"],
        verified_account_numbers=["990010000002"],
        approved_verification_account_numbers=[],
        has_published_cross_alert=True,
        has_hard_block=False,
    )
    all_findings = [
        FindingInput(severity_reported="green", reason_codes=("OK",)),
        *[FindingInput(severity_reported=f.severity, reason_codes=f.reason_codes) for f in sys_findings],
    ]
    agg = aggregate_findings(all_findings)
    assert agg.final_severity == "red"
    assert "PAYEE_CHANGE_REQUEST" in agg.reason_codes
    assert "CROSS_ALERT_HIT" in agg.reason_codes
    assert agg.verification_required is True


def test_required_bots_missing_and_disabled() -> None:
    res = check_required_bots(
        required_bot_ids=["procurement", "accounts-payable", "tax"],
        submitted_bot_ids=["procurement"],
        skipped_bot_ids=["tax"],
    )
    by_bot = {f.bot_id: f for f in res}
    assert by_bot["accounts-payable"].reason_codes == ("BOT_NOT_RUN",)
    assert by_bot["accounts-payable"].severity == "yellow"
    assert by_bot["tax"].reason_codes == ("BOT_DISABLED",)
    assert by_bot["tax"].severity == "yellow"


@pytest.mark.parametrize(
    ("severity", "total_vnd", "mode", "suspended", "hour", "expected"),
    [
        ("red", 10_000_000, "auto_pay", False, 10, "blocked"),
        ("yellow", 10_000_000, "auto_pay", False, 10, "pending_approval"),
        ("green", 26_500_000, "auto_pay", False, 10, "auto_pay_eligible"),
        ("green", 31_000_000, "auto_pay", False, 10, "pending_approval"),  # above 30M ceiling
        ("green", 26_500_000, "auto_pay", True, 10, "pending_approval"),   # QT-03 suspended
        ("green", 26_500_000, "auto_pay", False, 23, "pending_approval"),  # outside 07:00-22:00
        ("green", 26_500_000, "ask_first", False, 10, "pending_approval"),
        ("green", 26_500_000, "review_only", False, 10, "pending_approval"),
    ],
)
def test_post_investigation_status_table(
    severity: Severity,
    total_vnd: int,
    mode: str,
    suspended: bool,
    hour: int,
    expected: str,
) -> None:
    mandate = {
        "mode": mode,
        "limits": {"per_invoice_vnd": 30_000_000, "per_day_vnd": 50_000_000},
        "auto_pay_vendor_ids": ["ven_1"],
        "auto_pay_window": {"start": "07:00", "end": "22:00"},
    }
    status = determine_post_investigation_status(
        final_severity=severity,
        vendor_id="ven_1",
        total_vnd=total_vnd,
        mandate=mandate,
        platform_per_invoice_vnd=30_000_000,
        is_vendor_suspended=suspended,
        now_vn=datetime(2026, 11, 26, hour, 30, tzinfo=VN_TZ),
    )
    assert status == expected

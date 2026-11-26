"""Replay cassette tests for all 6 BRD §14 scenarios from services/sim-world/data/demo/scenarios.json.

Every test runs the full LangGraph supervisor + specialist bots graph using ReplayLLM
in strict `replay` mode against hand-written JSON cassette fixtures (zero live LLM calls)
and asserts the outgoing FindingSubmission and :complete HTTP bodies directly (I6).
"""

from __future__ import annotations

import asyncio

import pytest
from paymatch_contracts.internal import ReasonCode, Severity

from agent_runtime.adapters.internal_api_http import HttpInternalApiClient
from agent_runtime.domain.budgets import RuntimeConfig
from agent_runtime.domain.safety import BOT_OWNED_REASON_CODES, RED_REASON_CODES
from agent_runtime.llm import ReplayLLM
from agent_runtime.session.worker import AgentWorker

from brd14_scenarios import (
    BRD_14_TEMPLATE_IDS,
    CASSETTES_DIR,
    build_brd14_fixture,
    load_brd14_expectations,
)
from fake_internal_api import FakeInternalApiServer

_EXPECTATIONS = load_brd14_expectations()

_EXPECTED_BOT_SUBMISSIONS: dict[str, dict[str, tuple[str, set[str]]]] = {
    "BRD_01_COFFEE_26M5": {
        "procurement": ("green", {"OK"}),
        "accounts-payable": ("green", {"OK"}),
        "fraud-control": ("green", {"OK"}),
        "tax": ("green", {"OK"}),
        "treasury": ("green", {"OK"}),
    },
    "BRD_02_MILK_31M_ZALO_PAYEE": {
        "procurement": ("green", {"OK"}),
        "accounts-payable": ("green", {"OK"}),
        "fraud-control": ("red", {"PAYEE_CHANGE_REQUEST", "PERSONAL_ACCOUNT", "URGENCY_PRESSURE"}),
        "tax": ("green", {"OK"}),
        "treasury": ("yellow", {"OVER_LIMIT"}),
    },
    "BRD_03_CUPS_SHRINKFLATION": {
        "procurement": ("yellow", {"PACK_SIZE_CHANGED", "PRICE_ABOVE_CONTRACT"}),
        "accounts-payable": ("green", {"OK"}),
        "fraud-control": ("green", {"OK"}),
        "tax": ("green", {"OK"}),
        "treasury": ("green", {"OK"}),
    },
    "BRD_04_SYRUP_NEW_VENDOR_FRAUD": {
        "procurement": ("green", {"OK"}),
        "accounts-payable": ("green", {"OK"}),
        "fraud-control": ("red", {"PERSONAL_ACCOUNT", "HIDDEN_INSTRUCTION"}),
        "tax": ("red", {"TAX_RISK_LIST", "VAT_DEDUCTION_RISK"}),
        "treasury": ("green", {"OK"}),
    },
    "BRD_05_POS_SOFTWARE_12M": {
        "procurement": ("green", {"OK"}),
        "fraud-control": ("green", {"OK"}),
        "tax": ("green", {"OK"}),
        "treasury": ("green", {"OK"}),
    },
    "BRD_06_WATER_STORE3_4M2": {
        "branch-operations": ("yellow", {"UTILITY_OUT_OF_RANGE"}),
        "treasury": ("green", {"OK"}),
    },
}


@pytest.mark.parametrize("template_id", BRD_14_TEMPLATE_IDS)
def test_brd14_scenario_replay_matches_expected_severity_and_reason_codes(template_id: str):
    """Run full supervisor + specialist bots graph strictly from Replay cassette fixture."""
    cassette_path = CASSETTES_DIR / f"{template_id}.json"
    assert cassette_path.exists(), f"Missing Replay cassette fixture: {cassette_path}"

    expected = _EXPECTATIONS[template_id]
    expected_severity = Severity(expected["expected_severity"])
    expected_codes = {ReasonCode(c) for c in expected["expected_reason_codes"]}
    expected_bots = _EXPECTED_BOT_SUBMISSIONS[template_id]

    async def _run() -> None:
        server = FakeInternalApiServer()
        fix, _ = build_brd14_fixture(template_id)
        server.enqueue_job(fix)

        replay_llm = ReplayLLM.from_file(cassette_path)
        assert replay_llm.mode == "replay"

        async with server.make_httpx_client() as client:
            api = HttpInternalApiClient("http://internal-api.test", "test-service-key", client=client)
            worker = AgentWorker(api=api, llm=replay_llm, config=RuntimeConfig(worker_id="w-replay"))
            outcome = await worker.run_once()

        assert outcome is not None
        assert outcome.status == "completed"
        assert outcome.final_severity == expected_severity
        assert len(replay_llm.played_keys) >= 3

        # Directly assert outgoing FindingSubmission payloads sent by agent-runtime (I6)
        submissions = server.submitted_findings[fix.job_id]
        by_bot = {s.bot_id: s for s in submissions}
        assert set(by_bot.keys()) == set(expected_bots.keys())

        for bot_id, (exp_sev, exp_rcs) in expected_bots.items():
            sub = by_bot[bot_id]
            assert sub.severity_reported.value == exp_sev
            assert {c.value for c in sub.reason_codes} == exp_rcs
            assert sub.prompt_hash.startswith("sha256:")
            assert 1 <= len(sub.reason) <= 1000
            # Every emitted reason code must be owned by that bot
            owned = {c.value for c in BOT_OWNED_REASON_CODES[bot_id]}
            assert {c.value for c in sub.reason_codes} <= owned
            # Every red submission must carry valid evidence
            if any(ReasonCode(c.value) in RED_REASON_CODES for c in sub.reason_codes):
                assert len(sub.evidence) >= 1, f"{template_id}/{bot_id} red finding missing evidence"

        # Directly assert outgoing :complete HTTP body (I6)
        comp = server.completed_jobs[fix.job_id]
        raw_complete = comp["raw_body"]
        assert raw_complete["worker_id"] == "w-replay"
        assert raw_complete["attempt"] == 1
        raw_brief = raw_complete["result"]["brief"]
        assert 1 <= len(raw_brief["lines"]) <= 5
        assert all(isinstance(line, str) and 1 <= len(line) <= 200 for line in raw_brief["lines"])
        assert raw_brief["model"] == "demo-replay-v1"
        assert raw_brief["prompt_hash"].startswith("sha256:")
        assert len(raw_brief["cited_evidence"]) >= 1

        # Aggregated verdict matches scenarios.json
        actual_codes = set(comp["reason_codes"])
        assert actual_codes == expected_codes, (
            f"{template_id}: expected reason_codes={expected_codes}, got {actual_codes}"
        )

        # Treasury channel check for BRD_05 (virtual_card) and BRD_01 (bank_transfer)
        if template_id == "BRD_05_POS_SOFTWARE_12M":
            assert by_bot["treasury"].proposed_channel is not None
            assert by_bot["treasury"].proposed_channel.value == "virtual_card"
        elif template_id == "BRD_01_COFFEE_26M5":
            assert by_bot["treasury"].proposed_channel is not None
            assert by_bot["treasury"].proposed_channel.value == "bank_transfer"

    asyncio.run(_run())

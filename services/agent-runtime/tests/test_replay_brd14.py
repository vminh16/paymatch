"""Replay cassette tests for all 6 BRD §14 scenarios from services/sim-world/data/demo/scenarios.json.

Every test runs the full LangGraph supervisor + specialist bots graph using ReplayLLM
in strict `replay` mode against hand-written JSON cassette fixtures (zero live LLM calls).
"""

from __future__ import annotations

import asyncio

import pytest
from paymatch_contracts.internal import ReasonCode, Severity

from agent_runtime.adapters.internal_api_http import HttpInternalApiClient
from agent_runtime.domain.budgets import RuntimeConfig
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


@pytest.mark.parametrize("template_id", BRD_14_TEMPLATE_IDS)
def test_brd14_scenario_replay_matches_expected_severity_and_reason_codes(template_id: str):
    """Run full supervisor + specialist bots graph strictly from Replay cassette fixture."""
    cassette_path = CASSETTES_DIR / f"{template_id}.json"
    assert cassette_path.exists(), f"Missing Replay cassette fixture: {cassette_path}"

    expected = _EXPECTATIONS[template_id]
    expected_severity = Severity(expected["expected_severity"])
    expected_codes = {ReasonCode(c) for c in expected["expected_reason_codes"]}

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
        assert len(replay_llm.played_keys) >= 3  # supervisor + specialist bots played from cassette

        comp = server.completed_jobs[fix.job_id]
        actual_codes = set(comp["reason_codes"])
        assert actual_codes == expected_codes, (
            f"{template_id}: expected reason_codes={expected_codes}, got {actual_codes}"
        )
        # Brief must satisfy 1..5 lines × <= 200 chars
        brief = comp["request"].result.brief
        assert 1 <= len(brief.lines) <= 5
        assert all(len(line) <= 200 for line in brief.lines)

        # Treasury channel check for BRD_05 (virtual_card) and BRD_01 (bank_transfer)
        if template_id == "BRD_05_POS_SOFTWARE_12M":
            tr_sub = next(s for s in server.submitted_findings[fix.job_id] if s.bot_id == "treasury")
            assert tr_sub.proposed_channel is not None and tr_sub.proposed_channel.value == "virtual_card"
        elif template_id == "BRD_01_COFFEE_26M5":
            tr_sub = next(s for s in server.submitted_findings[fix.job_id] if s.bot_id == "treasury")
            assert tr_sub.proposed_channel is not None and tr_sub.proposed_channel.value == "bank_transfer"

    asyncio.run(_run())

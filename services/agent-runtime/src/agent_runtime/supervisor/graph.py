"""LangGraph supervisor graph for chief-accountant (docs/03-agents/agent-runtime.md §8)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent
from paymatch_contracts.internal import (
    BotSessionGrant,
    BriefSubmission,
    FindingForSupervisor,
    InvestigateSessionContext,
    JobProgressEventItem,
    JobSessionResponse,
    Type as ProgressEventType,
)
from pydantic import ValidationError

from agent_runtime.bots.runner import BotRunner
from agent_runtime.domain.budgets import BOT_MAX_STEPS, BOT_TIMEOUT_S
from agent_runtime.domain.models import BotQueryInput, RecordedToolCall
from agent_runtime.domain.safety import (
    build_fallback_brief,
    compute_prompt_hash,
    filter_supervisor_tools,
    parse_supervisor_brief_output,
    sanitize_finding_for_supervisor,
)
from agent_runtime.llm.langchain_adapter import PortChatModel
from agent_runtime.llm.port import LLM
from agent_runtime.session.port import InternalApiClient, LeaseLostError
from agent_runtime.session.token_store import TokenStore
from agent_runtime.tools.registry import build_internal_tools

ProgressCallback = Callable[[JobProgressEventItem], Awaitable[None]]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ask_tool_name(bot_id: str) -> str:
    """Tool identifier exposed to chief-accountant for a specialist bot (`ask_<bot_id>`)."""
    return f"ask_{bot_id}"


def _extract_last_ai_text(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


def _extract_last_ai_model(messages: list[Any], fallback: str) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            meta = getattr(msg, "response_metadata", None) or {}
            model = meta.get("model")
            if isinstance(model, str) and model and model != "unknown":
                return model
    return fallback


@dataclass(frozen=True)
class SupervisorRunResult:
    """Output of the supervisor LangGraph run for `investigate_invoice`."""

    brief: BriefSubmission
    findings: tuple[FindingForSupervisor, ...]
    steps_executed: int


class _SupervisorGraphState(TypedDict, total=False):
    session_ready: bool
    raw_brief_text: str
    brief_model: str
    steps_executed: int
    brief: BriefSubmission


class SupervisorRunner:
    """Runs the LangGraph supervisor graph: START -> open_session -> supervisor -> finish -> END."""

    def __init__(
        self,
        *,
        api: InternalApiClient,
        llm: LLM,
        safety_frame: str,
        chief_accountant_prompt: str,
        brief_model_name: str,
        bot_max_steps: int = BOT_MAX_STEPS,
        bot_timeout_s: float = BOT_TIMEOUT_S,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._api = api
        self._llm = llm
        self._safety_frame = safety_frame
        self._chief_prompt = chief_accountant_prompt
        self._brief_model_name = brief_model_name
        self._bot_max_steps = bot_max_steps
        self._bot_timeout_s = bot_timeout_s
        self._on_progress = on_progress

    async def _emit(self, event: JobProgressEventItem) -> None:
        if self._on_progress is not None:
            await self._on_progress(event)

    async def run_investigation(
        self,
        *,
        job_id: str,
        session: JobSessionResponse,
        token_store: TokenStore,
    ) -> SupervisorRunResult:
        """Execute an `investigate_invoice` session via LangGraph supervisor + bot subgraphs."""
        if not isinstance(session.context, InvestigateSessionContext):
            raise TypeError(
                f"Expected InvestigateSessionContext, got {type(session.context).__name__}"
            )
        ctx = session.context
        prompt_hash = compute_prompt_hash(self._chief_prompt)

        findings_by_bot: dict[str, FindingForSupervisor] = {}
        supervisor_tool_calls: list[RecordedToolCall] = []

        bot_runner = BotRunner(
            api=self._api,
            llm=self._llm,
            token_store=token_store,
            safety_frame=self._safety_frame,
            job_id=job_id,
            max_steps=self._bot_max_steps,
            timeout_s=self._bot_timeout_s,
            on_progress=self._on_progress,
        )

        # Build `ask_<bot_id>` tools (one per active bot in session, description from manifest)
        ask_tools: list[StructuredTool] = []
        for bot_grant in session.bots:
            ask_tools.append(
                self._make_ask_bot_tool(
                    bot_grant=bot_grant,
                    bot_runner=bot_runner,
                    findings_by_bot=findings_by_bot,
                    default_invoice_id=ctx.invoice_id,
                )
            )

        # Build trusted supervisor tools from session.supervisor.tools (strip any forbidden untrusted tool)
        safe_supervisor_defs = filter_supervisor_tools(session.supervisor.tools)
        trusted_tools = build_internal_tools(
            api=self._api,
            token_store=token_store,
            holder="supervisor",
            tool_definitions=safe_supervisor_defs,
            recorded_calls=supervisor_tool_calls,
        )

        all_supervisor_tools: list[StructuredTool] = [*ask_tools, *trusted_tools]

        step_counter = {"count": 0}

        async def _pre_model_hook(state: dict[str, Any]) -> dict[str, Any]:
            step_counter["count"] += 1
            await self._emit(
                JobProgressEventItem(
                    type=ProgressEventType.supervisor_step,
                    step=step_counter["count"],
                    at=_now_utc(),
                )
            )
            return {}

        react_agent = create_react_agent(
            model=PortChatModel(self._llm),
            tools=all_supervisor_tools,
            prompt=SystemMessage(content=self._chief_prompt),
            pre_model_hook=_pre_model_hook,
            name="chief-accountant",
        )

        async def _node_open_session(state: _SupervisorGraphState) -> _SupervisorGraphState:
            del state
            return {"session_ready": True}

        async def _node_supervisor(state: _SupervisorGraphState) -> _SupervisorGraphState:
            del state
            active_bot_ids = [b.bot_id for b in session.bots]
            skipped_ids = [s.bot_id for s in session.skipped]
            user_payload = {
                "task_type": "investigate_invoice",
                "invoice_id": ctx.invoice_id,
                "invoice_type": ctx.invoice_type.value,
                "required_bot_ids": list(session.required_bot_ids),
                "active_bots": active_bot_ids,
                "skipped_bots": skipped_ids,
            }
            user_prompt = (
                "Điều tra hóa đơn theo ngữ cảnh có cấu trúc sau (không có nội dung untrusted):\n"
                + json.dumps(user_payload, ensure_ascii=False, sort_keys=True)
            )
            recursion_limit = max(3, 2 * session.budget.max_steps + 1)
            try:
                result_state = await asyncio.wait_for(
                    react_agent.ainvoke(
                        {"messages": [HumanMessage(content=user_prompt)]},
                        config={"recursion_limit": recursion_limit},
                    ),
                    timeout=float(session.budget.seconds),
                )
                msgs = list(result_state.get("messages", []))
                return {
                    "raw_brief_text": _extract_last_ai_text(msgs),
                    "brief_model": _extract_last_ai_model(msgs, self._brief_model_name),
                    "steps_executed": step_counter["count"],
                }
            except LeaseLostError:
                raise
            except (TimeoutError, GraphRecursionError):
                return {
                    "raw_brief_text": "",
                    "brief_model": self._brief_model_name,
                    "steps_executed": step_counter["count"],
                }

        async def _node_finish(state: _SupervisorGraphState) -> _SupervisorGraphState:
            raw_text = state.get("raw_brief_text", "")
            model_name = state.get("brief_model", self._brief_model_name)
            try:
                parsed = parse_supervisor_brief_output(raw_text)
                brief = BriefSubmission(
                    lines=parsed.lines,
                    cited_evidence=parsed.cited_evidence,
                    model=model_name,
                    prompt_hash=prompt_hash,
                )
            except (ValueError, ValidationError):
                brief = build_fallback_brief(
                    invoice_id=ctx.invoice_id,
                    invoice_type=ctx.invoice_type.value,
                    findings=findings_by_bot.values(),
                    model=model_name,
                    prompt_hash=prompt_hash,
                )
            return {"brief": brief}

        graph = StateGraph(_SupervisorGraphState)
        graph.add_node("open_session", _node_open_session)
        graph.add_node("supervisor", _node_supervisor)
        graph.add_node("finish", _node_finish)
        graph.add_edge(START, "open_session")
        graph.add_edge("open_session", "supervisor")
        graph.add_edge("supervisor", "finish")
        graph.add_edge("finish", END)
        compiled = graph.compile()

        final_state = await compiled.ainvoke({})
        return SupervisorRunResult(
            brief=final_state["brief"],
            findings=tuple(findings_by_bot.values()),
            steps_executed=final_state.get("steps_executed", step_counter["count"]),
        )

    def _make_ask_bot_tool(
        self,
        *,
        bot_grant: BotSessionGrant,
        bot_runner: BotRunner,
        findings_by_bot: dict[str, FindingForSupervisor],
        default_invoice_id: str,
    ) -> StructuredTool:
        tool_name = ask_tool_name(bot_grant.bot_id)
        description = bot_grant.description or bot_grant.manifest.description

        async def _ask_bot(
            invoice_id: str | None = None,
            focus: list[str] | None = None,
            question_code: str | None = None,
            _grant: BotSessionGrant = bot_grant,
        ) -> str:
            query = BotQueryInput(
                invoice_id=invoice_id or default_invoice_id,
                focus=focus,
                question_code=question_code,
            )
            finding_for_sup = await bot_runner.run(_grant, query)
            findings_by_bot[_grant.bot_id] = finding_for_sup
            # Invariant #6: return ONLY FindingForSupervisor fields — strictly NO `reason`!
            clean_payload = sanitize_finding_for_supervisor(finding_for_sup)
            return json.dumps(clean_payload, ensure_ascii=False, sort_keys=True)

        return StructuredTool.from_function(
            coroutine=_ask_bot,
            name=tool_name,
            description=description,
            args_schema=BotQueryInput,
        )

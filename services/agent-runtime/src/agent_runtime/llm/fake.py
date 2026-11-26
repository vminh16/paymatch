"""Scripted FakeLLM adapter for deterministic agent logic and invariant tests."""

from __future__ import annotations

import asyncio
import inspect
import re
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from agent_runtime.domain.models import LLMMessage, LLMResponse, LLMToolSchema

from .port import LLMError

LLMResponder = Callable[
    [Sequence[LLMMessage], Sequence[LLMToolSchema] | None, dict[str, Any] | None],
    LLMResponse | Awaitable[LLMResponse],
]

_BOT_ROLE_RE = re.compile(r"# Vai trò:.*?\(`([a-z][a-z0-9-]*)`\)")
_SUPERVISOR_MARKER = "chief-accountant"


def infer_agent_id(messages: Sequence[LLMMessage]) -> str:
    """Identify which agent ('chief-accountant' or '<bot_id>') owns the system prompt."""
    for msg in messages:
        if msg.role == "system":
            if _SUPERVISOR_MARKER in msg.content:
                return "chief-accountant"
            match = _BOT_ROLE_RE.search(msg.content)
            if match:
                return match.group(1)
    return "default"


@dataclass
class RecordedLLMCall:
    """Recorded invocation for test assertions."""

    agent_id: str
    messages: list[LLMMessage]
    tools: list[LLMToolSchema] | None
    schema: dict[str, Any] | None


class FakeLLM:
    """Deterministic scripted LLM supporting global FIFO queues, per-agent scripts, or callables."""

    def __init__(
        self,
        responses: Sequence[LLMResponse | Exception | LLMResponder] | None = None,
        *,
        by_agent: dict[str, Sequence[LLMResponse | Exception | LLMResponder]] | None = None,
        responder: LLMResponder | None = None,
        delay_by_agent: dict[str, float] | None = None,
        model: str = "fake-llm-v1",
    ) -> None:
        self._queue: deque[LLMResponse | Exception | LLMResponder] = deque(responses or ())
        self._by_agent: dict[str, deque[LLMResponse | Exception | LLMResponder]] = {
            agent_id: deque(items) for agent_id, items in (by_agent or {}).items()
        }
        self._responder = responder
        self._delay_by_agent = dict(delay_by_agent or {})
        self.model = model
        self.calls: list[RecordedLLMCall] = []

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSchema] | None = None,
        schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        agent_id = infer_agent_id(messages)
        self.calls.append(
            RecordedLLMCall(
                agent_id=agent_id,
                messages=list(messages),
                tools=list(tools) if tools is not None else None,
                schema=schema,
            )
        )

        delay = self._delay_by_agent.get(agent_id, 0.0)
        if delay > 0:
            await asyncio.sleep(delay)

        if self._responder is not None:
            result = self._responder(messages, tools, schema)
            if inspect.isawaitable(result):
                return await result
            return result

        queue = self._by_agent.get(agent_id)
        if queue is not None:
            if not queue:
                raise LLMError(f"FakeLLM script exhausted for agent={agent_id!r}")
            item = queue.popleft()
        elif self._queue:
            item = self._queue.popleft()
        else:
            raise LLMError(f"FakeLLM has no scripted response left for agent={agent_id!r}")

        if isinstance(item, Exception):
            raise item
        if callable(item):
            res = item(messages, tools, schema)
            if inspect.isawaitable(res):
                return await res
            return res
        if item.model == "unknown":
            return item.model_copy(update={"model": self.model})
        return item

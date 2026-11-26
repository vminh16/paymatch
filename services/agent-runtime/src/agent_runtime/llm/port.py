"""Provider-neutral LLM port (docs/03-agents/agent-runtime.md §7)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Protocol, runtime_checkable

from agent_runtime.domain.models import LLMMessage, LLMResponse, LLMToolSchema

LLMMode = Literal["live", "record", "replay"]


class LLMError(RuntimeError):
    """Base error raised by LLM adapters."""


class CassetteMissError(LLMError):
    """Raised in replay mode when no cassette entry matches the canonical input hash."""

    def __init__(self, key: str, detail: str = "") -> None:
        self.key = key
        msg = f"Replay cassette miss for key={key}"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)


@runtime_checkable
class LLM(Protocol):
    """Provider-neutral LLM completion port.

    Real provider adapters are intentionally omitted until the team selects a provider/model.
    """

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSchema] | None = None,
        schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Complete a conversation, optionally with callable tool schemas or JSON output schema."""
        ...

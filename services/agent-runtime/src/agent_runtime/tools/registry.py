"""Thin LangChain tool wrappers around POST /internal/tools/{id}:invoke."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain_core.tools import StructuredTool
from paymatch_contracts.internal import Provenance, ToolDefinition

from agent_runtime.domain.models import RecordedToolCall
from agent_runtime.domain.safety import format_tool_result_block
from agent_runtime.session.port import (
    InternalApiClient,
    InternalApiError,
    KillSwitchActiveError,
    LeaseLostError,
    ToolNotGrantedError,
)
from agent_runtime.session.token_store import TokenStore

ToolCalledCallback = Callable[[str], Awaitable[None]]


async def invoke_internal_tool_safe(
    *,
    api: InternalApiClient,
    token_store: TokenStore,
    holder: str,
    tool_id: str,
    tool_input: dict[str, Any],
    recorded_calls: list[RecordedToolCall],
    on_tool_called: ToolCalledCallback | None = None,
) -> str:
    """Invoke a single internal-api tool using holder's capability token.

    - Re-raises LeaseLostError immediately (worker must halt).
    - Surfaces 403 TOOL_NOT_GRANTED, 423 KILL_SWITCH_ACTIVE, and other tool errors as a
      provenance-labelled ToolResult error payload so the bot records yellow (never green).
    """
    token = token_store.get(holder)
    if on_tool_called is not None:
        await on_tool_called(tool_id)

    try:
        result = await api.invoke_tool(tool_id, token, tool_input)
    except LeaseLostError:
        raise
    except (ToolNotGrantedError, KillSwitchActiveError, InternalApiError) as exc:
        recorded_calls.append(
            RecordedToolCall(
                tool_call_id=None,
                tool_id=tool_id,
                provenance=Provenance.trusted,
                data={},
                error_code=exc.code,
                error_detail=exc.detail,
            )
        )
        return format_tool_result_block(
            tool_id=tool_id,
            provenance=Provenance.trusted,
            evidence_ref="error",
            payload={
                "data": {},
                "error": {"code": exc.code, "detail": exc.detail},
            },
        )

    prov = Provenance(result.provenance.value)
    err_code = result.error.code.value if result.error is not None else None
    err_detail = result.error.detail if result.error is not None else None
    recorded_calls.append(
        RecordedToolCall(
            tool_call_id=result.evidence_ref,
            tool_id=tool_id,
            provenance=prov,
            data=result.data,
            error_code=err_code,
            error_detail=err_detail,
        )
    )
    payload: dict[str, Any] = {
        "data": result.data,
        "evidence_ref": result.evidence_ref,
        "error": (
            {"code": err_code, "detail": err_detail}
            if result.error is not None
            else None
        ),
    }
    return format_tool_result_block(
        tool_id=tool_id,
        provenance=prov,
        evidence_ref=result.evidence_ref,
        payload=payload,
    )


def build_internal_tools(
    *,
    api: InternalApiClient,
    token_store: TokenStore,
    holder: str,
    tool_definitions: Sequence[ToolDefinition],
    recorded_calls: list[RecordedToolCall],
    on_tool_called: ToolCalledCallback | None = None,
) -> list[StructuredTool]:
    """Create thin LangChain StructuredTool wrappers for each granted ToolDefinition."""
    lc_tools: list[StructuredTool] = []

    for tool_def in tool_definitions:
        tid = tool_def.tool_id
        schema = tool_def.input_schema or {"type": "object", "properties": {}}
        if "type" not in schema:
            schema = {"type": "object", **schema}

        async def _call_tool(_tid: str = tid, **kwargs: Any) -> str:
            return await invoke_internal_tool_safe(
                api=api,
                token_store=token_store,
                holder=holder,
                tool_id=_tid,
                tool_input=dict(kwargs),
                recorded_calls=recorded_calls,
                on_tool_called=on_tool_called,
            )

        lc_tools.append(
            StructuredTool.from_function(
                coroutine=_call_tool,
                name=tid,
                description=tool_def.description,
                args_schema=schema,
            )
        )

    return lc_tools

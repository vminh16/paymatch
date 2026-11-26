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

_RESERVED_REDIRECT_ARGS: frozenset[str] = frozenset({"_tid", "tool_id"})


def _supervisor_redacted_block(tool_id: str, code: str, evidence_ref: str = "error") -> str:
    """Supervisor boundary: never forward untrusted data or error.detail; only code/severity/reason_codes."""
    return format_tool_result_block(
        tool_id=tool_id,
        provenance=Provenance.trusted,
        evidence_ref=evidence_ref,
        payload={
            "code": code,
            "severity": "yellow",
            "reason_codes": [],
        },
    )


async def invoke_internal_tool_safe(
    *,
    api: InternalApiClient,
    token_store: TokenStore,
    holder: str,
    tool_id: str,
    tool_input: dict[str, Any],
    recorded_calls: list[RecordedToolCall],
    on_tool_called: ToolCalledCallback | None = None,
    supervisor_boundary: bool = False,
) -> str:
    """Invoke a single internal-api tool using holder's capability token.

    - Re-raises LeaseLostError immediately (worker must halt).
    - Surfaces 403 TOOL_NOT_GRANTED, 423 KILL_SWITCH_ACTIVE, and other tool errors as a
      provenance-labelled ToolResult error payload so the bot records yellow (never green).
    - When `supervisor_boundary=True`, NEVER forwards data whose actual provenance is
      `untrusted` or any `error.detail` text; returns only `{code, severity, reason_codes}`.
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
        if supervisor_boundary:
            return _supervisor_redacted_block(tool_id, exc.code)
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

    if supervisor_boundary:
        if prov == Provenance.untrusted:
            return _supervisor_redacted_block(
                tool_id,
                "UNTRUSTED_DATA_BLOCKED",
                evidence_ref=result.evidence_ref,
            )
        if err_code is not None:
            return _supervisor_redacted_block(
                tool_id,
                err_code,
                evidence_ref=result.evidence_ref,
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


def _make_tool_coroutine(
    *,
    bound_tool_id: str,
    allowed_schema_keys: frozenset[str],
    api: InternalApiClient,
    token_store: TokenStore,
    holder: str,
    recorded_calls: list[RecordedToolCall],
    on_tool_called: ToolCalledCallback | None,
    supervisor_boundary: bool,
) -> Callable[..., Awaitable[str]]:
    """Bind `bound_tool_id` strictly in a closure (never in tool kwargs) and reject redirect args."""
    forbidden_keys = _RESERVED_REDIRECT_ARGS - allowed_schema_keys

    async def _call_tool(**kwargs: Any) -> str:
        bad_keys = sorted(forbidden_keys & set(kwargs.keys()))
        if bad_keys:
            detail = f"Rejected forbidden argument(s): {', '.join(bad_keys)}"
            recorded_calls.append(
                RecordedToolCall(
                    tool_call_id=None,
                    tool_id=bound_tool_id,
                    provenance=Provenance.trusted,
                    data={},
                    error_code="INVALID_INPUT",
                    error_detail=detail,
                )
            )
            if supervisor_boundary:
                return _supervisor_redacted_block(bound_tool_id, "INVALID_INPUT")
            return format_tool_result_block(
                tool_id=bound_tool_id,
                provenance=Provenance.trusted,
                evidence_ref="error",
                payload={"data": {}, "error": {"code": "INVALID_INPUT", "detail": detail}},
            )
        return await invoke_internal_tool_safe(
            api=api,
            token_store=token_store,
            holder=holder,
            tool_id=bound_tool_id,
            tool_input=dict(kwargs),
            recorded_calls=recorded_calls,
            on_tool_called=on_tool_called,
            supervisor_boundary=supervisor_boundary,
        )

    return _call_tool


def build_internal_tools(
    *,
    api: InternalApiClient,
    token_store: TokenStore,
    holder: str,
    tool_definitions: Sequence[ToolDefinition],
    recorded_calls: list[RecordedToolCall],
    on_tool_called: ToolCalledCallback | None = None,
    supervisor_boundary: bool = False,
) -> list[StructuredTool]:
    """Create thin LangChain StructuredTool wrappers for each granted ToolDefinition."""
    lc_tools: list[StructuredTool] = []

    for tool_def in tool_definitions:
        tid = tool_def.tool_id
        schema = tool_def.input_schema or {"type": "object", "properties": {}}
        if "type" not in schema:
            schema = {"type": "object", **schema}
        props = schema.get("properties")
        allowed_keys = frozenset(props.keys()) if isinstance(props, dict) else frozenset()

        coro = _make_tool_coroutine(
            bound_tool_id=tid,
            allowed_schema_keys=allowed_keys,
            api=api,
            token_store=token_store,
            holder=holder,
            recorded_calls=recorded_calls,
            on_tool_called=on_tool_called,
            supervisor_boundary=supervisor_boundary,
        )
        lc_tools.append(
            StructuredTool.from_function(
                coroutine=coro,
                name=tid,
                description=tool_def.description,
                args_schema=schema,
            )
        )

    return lc_tools

"""Thin LangChain BaseChatModel adapter over the provider-neutral LLM port.

This allows LangGraph's prebuilt ReAct agent (`create_react_agent`) to execute
the real graph while every completion goes through `LLM.complete(messages, tools?, schema?)`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, PrivateAttr

from agent_runtime.domain.models import LLMMessage, LLMResponse, LLMToolCall, LLMToolSchema

from .port import LLM


def _stringify_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def lc_messages_to_domain(messages: Sequence[BaseMessage]) -> list[LLMMessage]:
    """Convert LangChain BaseMessage objects to provider-neutral LLMMessage list."""
    out: list[LLMMessage] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            out.append(LLMMessage(role="system", content=_stringify_content(msg.content)))
        elif isinstance(msg, HumanMessage):
            out.append(LLMMessage(role="user", content=_stringify_content(msg.content)))
        elif isinstance(msg, AIMessage):
            tcalls = [
                LLMToolCall(
                    id=str(tc.get("id", "")),
                    name=str(tc.get("name", "")),
                    arguments=dict(tc.get("args", {}) or {}),
                )
                for tc in (msg.tool_calls or [])
            ]
            out.append(
                LLMMessage(
                    role="assistant",
                    content=_stringify_content(msg.content),
                    tool_calls=tcalls,
                )
            )
        elif isinstance(msg, ToolMessage):
            out.append(
                LLMMessage(
                    role="tool",
                    content=_stringify_content(msg.content),
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                )
            )
        else:
            out.append(LLMMessage(role="user", content=_stringify_content(msg.content)))
    return out


def tool_to_schema(tool: BaseTool | dict[str, Any]) -> LLMToolSchema:
    """Convert a LangChain BaseTool or dict into a provider-neutral LLMToolSchema."""
    if isinstance(tool, dict):
        return LLMToolSchema(
            name=str(tool["name"]),
            description=str(tool.get("description", "")),
            parameters=dict(tool.get("parameters", {"type": "object", "properties": {}})),
        )
    params: dict[str, Any] = {"type": "object", "properties": {}}
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None:
        if isinstance(args_schema, dict):
            params = dict(args_schema)
        elif isinstance(args_schema, type) and issubclass(args_schema, BaseModel):
            params = args_schema.model_json_schema()
    return LLMToolSchema(
        name=tool.name,
        description=tool.description or "",
        parameters=params,
    )


def domain_response_to_chat_result(response: LLMResponse) -> ChatResult:
    """Convert domain LLMResponse into a LangChain ChatResult."""
    tool_calls = [
        {
            "id": tc.id,
            "name": tc.name,
            "args": tc.arguments,
            "type": "tool_call",
        }
        for tc in response.tool_calls
    ]
    ai_msg = AIMessage(
        content=response.content or "",
        tool_calls=tool_calls,
        response_metadata={"model": response.model},
    )
    return ChatResult(generations=[ChatGeneration(message=ai_msg)])


class PortChatModel(BaseChatModel):
    """LangChain BaseChatModel delegating all calls to an `LLM` port."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _port: LLM = PrivateAttr()
    _bound_tools: list[LLMToolSchema] | None = PrivateAttr(default=None)
    _output_schema: dict[str, Any] | None = PrivateAttr(default=None)

    def __init__(
        self,
        port: LLM,
        *,
        bound_tools: list[LLMToolSchema] | None = None,
        output_schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._port = port
        self._bound_tools = bound_tools
        self._output_schema = output_schema

    @property
    def _llm_type(self) -> str:
        return "paymatch-port-chat-model"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        del tool_choice, kwargs
        schemas = [tool_to_schema(t) for t in tools]
        return PortChatModel(
            self._port,
            bound_tools=schemas,
            output_schema=self._output_schema,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        domain_msgs = lc_messages_to_domain(messages)
        response = asyncio.run(
            self._port.complete(
                domain_msgs,
                tools=self._bound_tools,
                schema=self._output_schema,
            )
        )
        return domain_response_to_chat_result(response)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        domain_msgs = lc_messages_to_domain(messages)
        response = await self._port.complete(
            domain_msgs,
            tools=self._bound_tools,
            schema=self._output_schema,
        )
        return domain_response_to_chat_result(response)

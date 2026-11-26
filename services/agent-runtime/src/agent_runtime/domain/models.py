"""Pure domain models for provider-neutral LLM I/O, bot outputs, and job outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from paymatch_contracts.internal import (
    Channel1,
    EvidenceRef,
    FindingForSupervisor,
    InvoiceStatus,
    LocalDate,
    Provenance,
    ReasonCode,
    Severity,
)
from pydantic import BaseModel, ConfigDict, Field


class LLMToolCall(BaseModel):
    """Provider-neutral tool call issued by an LLM."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMMessage(BaseModel):
    """Provider-neutral chat message."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


class LLMToolSchema(BaseModel):
    """Provider-neutral JSON Schema definition for a callable tool."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})


class LLMResponse(BaseModel):
    """Provider-neutral completion response."""

    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    parsed: dict[str, Any] | None = None
    model: str = "unknown"


class BotQueryInput(BaseModel):
    """Structured query sent by chief-accountant when calling ask_<bot_id> (agent-runtime.md §3)."""

    model_config = ConfigDict(extra="forbid")

    invoice_id: str | None = Field(
        default=None,
        description="ID hóa đơn cần điều tra (ví dụ inv_...).",
    )
    focus: list[str] | None = Field(
        default=None,
        description="Danh sách mục trọng tâm có cấu trúc (enum ngắn, không chứa văn bản tự do).",
    )
    question_code: str | None = Field(
        default=None,
        description="Mã câu hỏi có cấu trúc tùy chọn.",
    )


class BotFindingOutput(BaseModel):
    """Strict JSON output expected from a specialist bot LLM before submission to core."""

    model_config = ConfigDict(extra="forbid")

    severity_reported: Severity
    reason_codes: Annotated[list[ReasonCode], Field(min_length=1)]
    reason: Annotated[str, Field(max_length=1000)]
    evidence: list[EvidenceRef] = Field(default_factory=list)
    provenance: Provenance
    proposed_channel: Channel1 | None = None
    proposed_pay_on: LocalDate | None = None


type BriefLine = Annotated[str, Field(min_length=1, max_length=200)]


class SupervisorBriefOutput(BaseModel):
    """Strict JSON brief output expected from chief-accountant (≤ 5 lines × 200 chars)."""

    model_config = ConfigDict(extra="forbid")

    lines: Annotated[list[BriefLine], Field(min_length=1, max_length=5)]
    cited_evidence: list[EvidenceRef] = Field(default_factory=list)


@dataclass(frozen=True)
class RecordedToolCall:
    """Audit record of a tool invocation made by a bot or supervisor."""

    tool_call_id: str | None
    tool_id: str
    provenance: Provenance
    data: dict[str, Any]
    error_code: str | None = None
    error_detail: str | None = None


@dataclass(frozen=True)
class JobRunOutcome:
    """Summary of one worker job execution."""

    job_id: str
    attempt: int
    status: Literal["completed", "failed", "lease_lost", "unsupported_completed"]
    final_severity: Severity | None = None
    invoice_status: InvoiceStatus | None = None
    findings: tuple[FindingForSupervisor, ...] = field(default_factory=tuple)
    will_retry: bool | None = None
    error_code: str | None = None

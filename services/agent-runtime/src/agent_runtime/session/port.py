"""Internal API client port and typed protocol errors (contracts/openapi/core-internal.yaml)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from paymatch_contracts.internal import (
    BotAnswerSubmission,
    ClaimedJobResponse,
    CompleteAnswerResult,
    CompleteInvestigateResult,
    CompleteJobResponse,
    FailJobResponse,
    FindingForSupervisor,
    JobHeartbeatResponse,
    JobProgressEventItem,
    JobSessionResponse,
    TaskType,
    ToolDefinition,
)
from paymatch_contracts.schemas.bot_answer_schema import BotAnswer
from paymatch_contracts.schemas.finding_submission_schema import FindingSubmission
from paymatch_contracts.schemas.model_config_schema import ModelConfig
from paymatch_contracts.schemas.tool_result_schema import ToolResult


class InternalApiError(RuntimeError):
    """Base error from core internal-api."""

    def __init__(self, status_code: int, code: str, detail: str = "") -> None:
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(f"internal-api {status_code} {code}: {detail}")


class LeaseLostError(InternalApiError):
    """Raised on 409 LEASE_LOST; worker must stop the job immediately."""


class KillSwitchActiveError(InternalApiError):
    """Raised on 423 KILL_SWITCH_ACTIVE."""


class ToolNotGrantedError(InternalApiError):
    """Raised on 403 TOOL_NOT_GRANTED (or 403 FORBIDDEN on tool invoke)."""


class TokenExpiredError(InternalApiError):
    """Raised on 401 TOKEN_EXPIRED / UNAUTHENTICATED."""


class InvalidStateError(InternalApiError):
    """Raised on 409 INVALID_STATE."""


@runtime_checkable
class InternalApiClient(Protocol):
    """Port for core internal-api (/internal/*)."""

    async def claim_job(
        self,
        worker_id: str,
        task_types: Sequence[TaskType] | None = None,
    ) -> ClaimedJobResponse | None:
        """POST /internal/jobs:claim -> ClaimedJobResponse or None on 204."""
        ...

    async def open_session(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
    ) -> JobSessionResponse:
        """POST /internal/jobs/{job_id}/session."""
        ...

    async def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
    ) -> JobHeartbeatResponse:
        """POST /internal/jobs/{job_id}/heartbeat."""
        ...

    async def report_progress(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
        events: Sequence[JobProgressEventItem],
    ) -> None:
        """POST /internal/jobs/{job_id}/progress."""
        ...

    async def submit_finding(
        self,
        job_id: str,
        capability_token: str,
        finding: FindingSubmission,
    ) -> FindingForSupervisor:
        """POST /internal/jobs/{job_id}/findings."""
        ...

    async def submit_bot_answer(
        self,
        job_id: str,
        capability_token: str,
        answer: BotAnswerSubmission,
    ) -> BotAnswer:
        """POST /internal/jobs/{job_id}/bot-answers."""
        ...

    async def complete_job(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
        result: CompleteInvestigateResult | CompleteAnswerResult,
    ) -> CompleteJobResponse:
        """POST /internal/jobs/{job_id}:complete."""
        ...

    async def fail_job(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
        error_code: str,
        detail: str,
    ) -> FailJobResponse:
        """POST /internal/jobs/{job_id}:fail."""
        ...

    async def list_model_configs(self) -> list[ModelConfig]:
        """GET /internal/model-configs."""
        ...

    async def list_tools(self, capability_token: str) -> list[ToolDefinition]:
        """GET /internal/tools."""
        ...

    async def invoke_tool(
        self,
        tool_id: str,
        capability_token: str,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """POST /internal/tools/{tool_id}:invoke."""
        ...

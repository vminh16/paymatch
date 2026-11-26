"""httpx client adapter for core internal-api (/internal/*)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx
from paymatch_contracts.internal import (
    BotAnswerSubmission,
    ClaimedJobResponse,
    ClaimJobRequest,
    CompleteAnswerResponse,
    CompleteAnswerResult,
    CompleteInvestigateResponse,
    CompleteInvestigateResult,
    CompleteJobRequest,
    CompleteJobResponse,
    FailJobRequest,
    FailJobResponse,
    FindingForSupervisor,
    JobHeartbeatRequest,
    JobHeartbeatResponse,
    JobProgressEventItem,
    JobProgressRequest,
    JobSessionResponse,
    OpenJobSessionRequest,
    TaskType,
    ToolDefinition,
    ToolInvokeRequest,
)
from paymatch_contracts.schemas.bot_answer_schema import BotAnswer
from paymatch_contracts.schemas.finding_submission_schema import FindingSubmission
from paymatch_contracts.schemas.model_config_schema import ModelConfig
from paymatch_contracts.schemas.tool_result_schema import ToolResult

from agent_runtime.domain.budgets import TOOL_INVOKE_MAX_RETRIES_5XX, TOOL_INVOKE_TIMEOUT_S
from agent_runtime.session.port import (
    InternalApiError,
    InvalidStateError,
    KillSwitchActiveError,
    LeaseLostError,
    TokenExpiredError,
    ToolNotGrantedError,
)


def _normalize_origin(base_url: str) -> str:
    """Accept either 'http://host:8003' or 'http://host:8003/internal' cleanly."""
    stripped = base_url.rstrip("/")
    if stripped.endswith("/internal"):
        return stripped[: -len("/internal")]
    return stripped


def _parse_error(response: httpx.Response) -> InternalApiError:
    status = response.status_code
    code = f"HTTP_{status}"
    detail = response.text[:500]
    try:
        payload = response.json()
        if isinstance(payload, dict):
            code = str(payload.get("code") or code)
            detail = str(payload.get("detail") or payload.get("title") or detail)
    except ValueError:
        pass

    if status == 409 and code == "LEASE_LOST":
        return LeaseLostError(status, code, detail)
    if status == 409 and code == "INVALID_STATE":
        return InvalidStateError(status, code, detail)
    if status == 423 or code == "KILL_SWITCH_ACTIVE":
        return KillSwitchActiveError(status, code, detail)
    if status == 403 and code in {"TOOL_NOT_GRANTED", "FORBIDDEN"}:
        return ToolNotGrantedError(status, code, detail)
    if status == 401:
        return TokenExpiredError(status, code, detail)
    return InternalApiError(status, code, detail)


class HttpInternalApiClient:
    """Async httpx client for core internal-api.

    Strictly separates ServiceKeyAuth (`X-Service-Key`) from CapabilityBearerAuth
    (`Authorization: Bearer <token>`): never mixes the two on any request.
    """

    def __init__(
        self,
        base_url: str,
        service_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 10.0,
        tool_timeout_s: float = TOOL_INVOKE_TIMEOUT_S,
        tool_retries_5xx: int = TOOL_INVOKE_MAX_RETRIES_5XX,
    ) -> None:
        self._origin = _normalize_origin(base_url)
        self._service_key = service_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=self._origin, timeout=timeout_s)
        self._tool_timeout_s = tool_timeout_s
        self._tool_retries_5xx = tool_retries_5xx

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> HttpInternalApiClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    def _service_headers(self) -> dict[str, str]:
        return {"X-Service-Key": self._service_key}

    def _capability_headers(self, capability_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {capability_token}"}

    def _url(self, path: str) -> str:
        if self._client.base_url and str(self._client.base_url).rstrip("/"):
            return path
        return f"{self._origin}{path}"

    async def claim_job(
        self,
        worker_id: str,
        task_types: Sequence[TaskType] | None = None,
    ) -> ClaimedJobResponse | None:
        req = ClaimJobRequest(
            worker_id=worker_id,
            task_types=list(task_types) if task_types is not None else None,
        )
        resp = await self._client.post(
            self._url("/internal/jobs:claim"),
            headers=self._service_headers(),
            json=req.model_dump(mode="json", exclude_none=True),
        )
        if resp.status_code == 204:
            return None
        if resp.status_code != 200:
            raise _parse_error(resp)
        return ClaimedJobResponse.model_validate(resp.json())

    async def open_session(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
    ) -> JobSessionResponse:
        req = OpenJobSessionRequest(worker_id=worker_id, attempt=attempt)
        resp = await self._client.post(
            self._url(f"/internal/jobs/{job_id}/session"),
            headers=self._service_headers(),
            json=req.model_dump(mode="json"),
        )
        if resp.status_code != 200:
            raise _parse_error(resp)
        return JobSessionResponse.model_validate(resp.json())

    async def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
    ) -> JobHeartbeatResponse:
        req = JobHeartbeatRequest(worker_id=worker_id, attempt=attempt)
        resp = await self._client.post(
            self._url(f"/internal/jobs/{job_id}/heartbeat"),
            headers=self._service_headers(),
            json=req.model_dump(mode="json"),
        )
        if resp.status_code != 200:
            raise _parse_error(resp)
        return JobHeartbeatResponse.model_validate(resp.json())

    async def report_progress(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
        events: Sequence[JobProgressEventItem],
    ) -> None:
        if not events:
            return
        req = JobProgressRequest(worker_id=worker_id, attempt=attempt, events=list(events))
        resp = await self._client.post(
            self._url(f"/internal/jobs/{job_id}/progress"),
            headers=self._service_headers(),
            json=req.model_dump(mode="json", exclude_none=True),
        )
        if resp.status_code != 204:
            raise _parse_error(resp)

    async def submit_finding(
        self,
        job_id: str,
        capability_token: str,
        finding: FindingSubmission,
    ) -> FindingForSupervisor:
        resp = await self._client.post(
            self._url(f"/internal/jobs/{job_id}/findings"),
            headers=self._capability_headers(capability_token),
            json=finding.model_dump(mode="json"),
        )
        if resp.status_code != 201:
            raise _parse_error(resp)
        return FindingForSupervisor.model_validate(resp.json())

    async def submit_bot_answer(
        self,
        job_id: str,
        capability_token: str,
        answer: BotAnswerSubmission,
    ) -> BotAnswer:
        resp = await self._client.post(
            self._url(f"/internal/jobs/{job_id}/bot-answers"),
            headers=self._capability_headers(capability_token),
            json=answer.model_dump(mode="json"),
        )
        if resp.status_code != 201:
            raise _parse_error(resp)
        return BotAnswer.model_validate(resp.json())

    async def complete_job(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
        result: CompleteInvestigateResult | CompleteAnswerResult,
    ) -> CompleteJobResponse:
        req = CompleteJobRequest(worker_id=worker_id, attempt=attempt, result=result)
        resp = await self._client.post(
            self._url(f"/internal/jobs/{job_id}:complete"),
            headers=self._service_headers(),
            json=req.model_dump(mode="json", by_alias=True),
        )
        if resp.status_code != 200:
            raise _parse_error(resp)
        data = resp.json()
        if "final_severity" in data:
            return CompleteInvestigateResponse.model_validate(data)
        return CompleteAnswerResponse.model_validate(data)

    async def fail_job(
        self,
        job_id: str,
        worker_id: str,
        attempt: int,
        error_code: str,
        detail: str,
    ) -> FailJobResponse:
        req = FailJobRequest(
            worker_id=worker_id,
            attempt=attempt,
            error_code=error_code,
            detail=detail,
        )
        resp = await self._client.post(
            self._url(f"/internal/jobs/{job_id}:fail"),
            headers=self._service_headers(),
            json=req.model_dump(mode="json"),
        )
        if resp.status_code != 200:
            raise _parse_error(resp)
        return FailJobResponse.model_validate(resp.json())

    async def list_model_configs(self) -> list[ModelConfig]:
        resp = await self._client.get(
            self._url("/internal/model-configs"),
            headers=self._service_headers(),
        )
        if resp.status_code != 200:
            raise _parse_error(resp)
        return [ModelConfig.model_validate(item) for item in resp.json()]

    async def list_tools(self, capability_token: str) -> list[ToolDefinition]:
        resp = await self._client.get(
            self._url("/internal/tools"),
            headers=self._capability_headers(capability_token),
        )
        if resp.status_code != 200:
            raise _parse_error(resp)
        return [ToolDefinition.model_validate(item) for item in resp.json()]

    async def invoke_tool(
        self,
        tool_id: str,
        capability_token: str,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        req = ToolInvokeRequest(input=tool_input)
        attempts = 1 + max(0, self._tool_retries_5xx)
        last_error: Exception | None = None
        for idx in range(attempts):
            try:
                resp = await self._client.post(
                    self._url(f"/internal/tools/{tool_id}:invoke"),
                    headers=self._capability_headers(capability_token),
                    json=req.model_dump(mode="json"),
                    timeout=self._tool_timeout_s,
                )
            except httpx.TimeoutException as exc:
                last_error = exc
                if idx + 1 < attempts:
                    continue
                raise InternalApiError(504, "UPSTREAM_TIMEOUT", str(exc)) from exc
            if resp.status_code == 200:
                return ToolResult.model_validate(resp.json())
            if 500 <= resp.status_code <= 599 and idx + 1 < attempts:
                last_error = _parse_error(resp)
                continue
            raise _parse_error(resp)
        assert last_error is not None
        raise last_error

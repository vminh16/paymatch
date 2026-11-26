"""Agent worker loop: claim job -> session -> supervisor ReAct -> complete / fail."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

import httpx
from paymatch_contracts.internal import (
    AnswerSubmission,
    ClaimedJobResponse,
    CompleteAnswerResult,
    CompleteInvestigateResponse,
    CompleteInvestigateResult,
    JobProgressEventItem,
    TaskType,
)
from paymatch_contracts.schemas.model_config_schema import ModelConfig, Purpose

from agent_runtime.domain.budgets import RuntimeConfig
from agent_runtime.domain.models import JobRunOutcome
from agent_runtime.llm.port import LLM, LLMError
from agent_runtime.plugins.loader import RuntimePrompts, load_runtime_prompts
from agent_runtime.session.heartbeat import HeartbeatManager
from agent_runtime.session.port import InternalApiClient, InternalApiError, LeaseLostError
from agent_runtime.session.token_store import TokenStore
from agent_runtime.supervisor.graph import SupervisorRunner

logger = logging.getLogger(__name__)

_UNSUPPORTED_TASK_MESSAGE = (
    "Loại tác vụ hỏi đáp/báo cáo chưa được hỗ trợ trong phiên bản agent-runtime hiện tại."
)


class AgentWorker:
    """Stateless worker polling internal-api for jobs and executing them within lease bounds."""

    def __init__(
        self,
        *,
        api: InternalApiClient,
        llm: LLM,
        config: RuntimeConfig,
        prompts: RuntimePrompts | None = None,
        task_types: Sequence[TaskType] | None = None,
    ) -> None:
        self._api = api
        self._llm = llm
        self._config = config
        self._prompts = prompts or load_runtime_prompts()
        self._task_types = list(task_types) if task_types is not None else [
            TaskType.question,
            TaskType.investigate_invoice,
            TaskType.report,
        ]
        self._model_configs: dict[Purpose, ModelConfig] = {}

    async def refresh_model_configs(self) -> dict[Purpose, ModelConfig]:
        """Fetch ModelConfig entries from GET /internal/model-configs (no hard-coded model names)."""
        try:
            configs = await self._api.list_model_configs()
            self._model_configs = {cfg.purpose: cfg for cfg in configs}
        except (InternalApiError, httpx.HTTPError):
            logger.debug("Model configs unavailable from internal-api; using RuntimeConfig defaults")
        return dict(self._model_configs)

    def _brief_model_name(self) -> str:
        cfg = self._model_configs.get(Purpose.brief)
        if cfg is not None:
            return cfg.primary_model
        return self._config.default_brief_model

    async def run_once(self) -> JobRunOutcome | None:
        """Claim and process at most one job. Returns None if queue is empty (204)."""
        claimed = await self._api.claim_job(
            worker_id=self._config.worker_id,
            task_types=self._task_types,
        )
        if claimed is None:
            return None
        return await self.process_claimed_job(claimed)

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        """Poll internal-api until `stop_event` is set, surviving transient API errors."""
        while stop_event is None or not stop_event.is_set():
            try:
                outcome = await self.run_once()
            except (InternalApiError, httpx.HTTPError) as exc:
                logger.warning("Transient error during poll loop; retrying: %s", exc)
                await asyncio.sleep(self._config.poll_interval_s)
                continue
            if outcome is None:
                await asyncio.sleep(self._config.poll_interval_s)

    async def process_claimed_job(self, claimed: ClaimedJobResponse) -> JobRunOutcome:
        """Execute a claimed job through its full lifecycle."""
        if claimed.task_type in (TaskType.question, TaskType.report):
            return await self._handle_unsupported_stub(claimed)

        if not self._model_configs:
            await self.refresh_model_configs()

        try:
            session = await self._api.open_session(
                job_id=claimed.job_id,
                worker_id=self._config.worker_id,
                attempt=claimed.attempt,
            )
        except LeaseLostError:
            return JobRunOutcome(
                job_id=claimed.job_id,
                attempt=claimed.attempt,
                status="lease_lost",
                error_code="LEASE_LOST",
            )
        except InternalApiError as exc:
            return await self._fail_safely(claimed, error_code=exc.code, detail=exc.detail)
        except httpx.HTTPError as exc:
            return await self._fail_safely(
                claimed, error_code="UPSTREAM_UNAVAILABLE", detail=str(exc)
            )

        token_store = TokenStore(session)
        heartbeat = HeartbeatManager(
            api=self._api,
            token_store=token_store,
            job_id=claimed.job_id,
            worker_id=self._config.worker_id,
            attempt=claimed.attempt,
            interval_s=self._config.heartbeat_interval_s,
            max_consecutive_errors=self._config.heartbeat_max_consecutive_errors,
        )

        async def _send_progress(event: JobProgressEventItem) -> None:
            try:
                await self._api.report_progress(
                    job_id=claimed.job_id,
                    worker_id=self._config.worker_id,
                    attempt=claimed.attempt,
                    events=[event],
                )
            except LeaseLostError:
                raise
            except (InternalApiError, httpx.HTTPError) as exc:
                logger.warning("Progress event delivery failed for job %s: %s", claimed.job_id, exc)

        supervisor = SupervisorRunner(
            api=self._api,
            llm=self._llm,
            safety_frame=self._prompts.safety_frame,
            chief_accountant_prompt=self._prompts.chief_accountant,
            brief_model_name=self._brief_model_name(),
            bot_max_steps=self._config.bot_max_steps,
            bot_timeout_s=self._config.bot_timeout_s,
            on_progress=_send_progress,
        )

        run_task = asyncio.create_task(
            supervisor.run_investigation(
                job_id=claimed.job_id,
                session=session,
                token_store=token_store,
            ),
            name=f"job-{claimed.job_id}",
        )
        heartbeat.attach_target_task(run_task)
        heartbeat.start()

        try:
            run_result = await run_task
        except asyncio.CancelledError:
            if heartbeat.lease_lost is not None:
                return JobRunOutcome(
                    job_id=claimed.job_id,
                    attempt=claimed.attempt,
                    status="lease_lost",
                    error_code="LEASE_LOST",
                )
            if heartbeat.fatal_error is not None:
                err = heartbeat.fatal_error
                err_code = err.code if isinstance(err, InternalApiError) else "HEARTBEAT_FAILED"
                return await self._fail_safely(claimed, error_code=err_code, detail=str(err))
            raise
        except LeaseLostError:
            return JobRunOutcome(
                job_id=claimed.job_id,
                attempt=claimed.attempt,
                status="lease_lost",
                error_code="LEASE_LOST",
            )
        except (LLMError, Exception) as exc:  # noqa: BLE001
            error_code = (
                exc.code
                if isinstance(exc, InternalApiError)
                else ("LLM_ERROR" if isinstance(exc, LLMError) else "RUNTIME_ERROR")
            )
            return await self._fail_safely(claimed, error_code=error_code, detail=str(exc))
        finally:
            await heartbeat.stop()

        try:
            complete_resp = await self._api.complete_job(
                job_id=claimed.job_id,
                worker_id=self._config.worker_id,
                attempt=claimed.attempt,
                result=CompleteInvestigateResult(brief=run_result.brief),
            )
        except LeaseLostError:
            return JobRunOutcome(
                job_id=claimed.job_id,
                attempt=claimed.attempt,
                status="lease_lost",
                error_code="LEASE_LOST",
            )
        except InternalApiError as exc:
            return await self._fail_safely(claimed, error_code=exc.code, detail=exc.detail)
        except httpx.HTTPError as exc:
            return await self._fail_safely(
                claimed, error_code="UPSTREAM_UNAVAILABLE", detail=str(exc)
            )

        if isinstance(complete_resp, CompleteInvestigateResponse):
            return JobRunOutcome(
                job_id=claimed.job_id,
                attempt=claimed.attempt,
                status="completed",
                final_severity=complete_resp.final_severity,
                invoice_status=complete_resp.invoice_status,
                findings=run_result.findings,
            )
        return JobRunOutcome(
            job_id=claimed.job_id,
            attempt=claimed.attempt,
            status="completed",
            findings=run_result.findings,
        )

    async def _handle_unsupported_stub(self, claimed: ClaimedJobResponse) -> JobRunOutcome:
        """Clean stub for question/report jobs (out of scope for phase-1)."""
        try:
            await self._api.complete_job(
                job_id=claimed.job_id,
                worker_id=self._config.worker_id,
                attempt=claimed.attempt,
                result=CompleteAnswerResult(
                    answer=AnswerSubmission(
                        text=_UNSUPPORTED_TASK_MESSAGE,
                        citations=[],
                        proposed_actions=[],
                    )
                ),
            )
        except LeaseLostError:
            return JobRunOutcome(
                job_id=claimed.job_id,
                attempt=claimed.attempt,
                status="lease_lost",
                error_code="LEASE_LOST",
            )
        except (InternalApiError, httpx.HTTPError) as exc:
            detail = exc.detail if isinstance(exc, InternalApiError) else str(exc)
            return await self._fail_safely(
                claimed,
                error_code="UNSUPPORTED_TASK_TYPE",
                detail=f"{claimed.task_type.value}: {detail}",
            )
        return JobRunOutcome(
            job_id=claimed.job_id,
            attempt=claimed.attempt,
            status="unsupported_completed",
            error_code="UNSUPPORTED_TASK_TYPE",
        )

    async def _fail_safely(
        self,
        claimed: ClaimedJobResponse,
        *,
        error_code: str,
        detail: str,
    ) -> JobRunOutcome:
        try:
            fail_resp = await self._api.fail_job(
                job_id=claimed.job_id,
                worker_id=self._config.worker_id,
                attempt=claimed.attempt,
                error_code=error_code,
                detail=detail[:1000],
            )
            return JobRunOutcome(
                job_id=claimed.job_id,
                attempt=claimed.attempt,
                status="failed",
                will_retry=fail_resp.will_retry,
                error_code=error_code,
            )
        except LeaseLostError:
            return JobRunOutcome(
                job_id=claimed.job_id,
                attempt=claimed.attempt,
                status="lease_lost",
                error_code="LEASE_LOST",
            )
        except (InternalApiError, httpx.HTTPError) as exc:
            logger.warning("fail_job call failed for job %s: %s", claimed.job_id, exc)
            return JobRunOutcome(
                job_id=claimed.job_id,
                attempt=claimed.attempt,
                status="failed",
                will_retry=None,
                error_code=error_code,
            )

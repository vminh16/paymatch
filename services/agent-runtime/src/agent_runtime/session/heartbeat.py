"""Background lease heartbeat and capability token renewal task (internal-api.md §1)."""

from __future__ import annotations

import asyncio
import contextlib
import logging

import httpx

from agent_runtime.domain.budgets import HEARTBEAT_INTERVAL_S
from agent_runtime.session.port import InternalApiClient, InternalApiError, LeaseLostError
from agent_runtime.session.token_store import TokenStore

logger = logging.getLogger(__name__)


class HeartbeatManager:
    """Periodically renews job lease and capability tokens every `interval_s` seconds (default 30s).

    - Immediately cancels target task on `409 LEASE_LOST`.
    - Retries transient errors (e.g. 503) without crashing the background task; after
      `max_consecutive_errors` consecutive failures, records `fatal_error` and cancels the
      target task so `AgentWorker` routes the failure through `:fail`.
    """

    def __init__(
        self,
        *,
        api: InternalApiClient,
        token_store: TokenStore,
        job_id: str,
        worker_id: str,
        attempt: int,
        interval_s: float = HEARTBEAT_INTERVAL_S,
        max_consecutive_errors: int = 3,
        on_lease_lost: asyncio.Task[object] | None = None,
    ) -> None:
        self._api = api
        self._token_store = token_store
        self._job_id = job_id
        self._worker_id = worker_id
        self._attempt = attempt
        self._interval_s = interval_s
        self._max_consecutive_errors = max(1, max_consecutive_errors)
        self._target_task = on_lease_lost
        self._task: asyncio.Task[None] | None = None
        self.beat_count: int = 0
        self.consecutive_errors: int = 0
        self.lease_lost: LeaseLostError | None = None
        self.fatal_error: Exception | None = None

    def attach_target_task(self, task: asyncio.Task[object]) -> None:
        self._target_task = task

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"heartbeat-{self._job_id}")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_s)
            try:
                resp = await self._api.heartbeat(
                    job_id=self._job_id,
                    worker_id=self._worker_id,
                    attempt=self._attempt,
                )
                self._token_store.update(resp.tokens)
                self.beat_count += 1
                self.consecutive_errors = 0
            except LeaseLostError as exc:
                self.lease_lost = exc
                if self._target_task is not None and not self._target_task.done():
                    self._target_task.cancel()
                return
            except (InternalApiError, httpx.HTTPError) as exc:
                self.consecutive_errors += 1
                logger.warning(
                    "Heartbeat failed for job %s (%d/%d): %s",
                    self._job_id,
                    self.consecutive_errors,
                    self._max_consecutive_errors,
                    exc,
                )
                if self.consecutive_errors >= self._max_consecutive_errors:
                    self.fatal_error = exc
                    if self._target_task is not None and not self._target_task.done():
                        self._target_task.cancel()
                    return

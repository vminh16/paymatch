"""Webhook dispatcher from sim-world to core internal-api (/webhooks/rails)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class WebhookRecord:
    event_id: str
    type: str
    occurred_at: str
    data: dict[str, Any]
    delivered: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "occurred_at": self.occurred_at,
            "data": self.data,
            "delivered": self.delivered,
            "error": self.error,
        }


class WebhookDispatcher:
    """Delivers rail events to CORE_INTERNAL_URL + /webhooks/rails (3s timeout, 3 tries)."""

    def __init__(
        self,
        core_internal_url: str | None,
        service_key: str | None = None,
        *,
        timeout_s: float = 3.0,
        max_attempts: int = 3,
        backoff_s: tuple[float, ...] = (0.2, 0.5),
        client_factory: Callable[[], httpx.Client] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = core_internal_url.rstrip("/") if core_internal_url else None
        self._service_key = service_key
        self._timeout_s = timeout_s
        self._max_attempts = max_attempts
        self._backoff_s = backoff_s
        self._client_factory = client_factory
        self._sleep_fn = sleep_fn

    def dispatch(
        self,
        *,
        event_id: str,
        event_type: str,
        occurred_at: str,
        data: dict[str, Any],
    ) -> WebhookRecord:
        payload = {
            "event_id": event_id,
            "type": event_type,
            "occurred_at": occurred_at,
            "data": data,
        }
        if not self._base_url:
            return WebhookRecord(
                event_id=event_id,
                type=event_type,
                occurred_at=occurred_at,
                data=data,
                delivered=False,
                error=None,
            )

        url = f"{self._base_url}/webhooks/rails"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._service_key:
            headers["X-Service-Key"] = self._service_key

        last_error: str | None = None
        client = (
            self._client_factory()
            if self._client_factory is not None
            else httpx.Client(timeout=self._timeout_s)
        )
        try:
            for attempt in range(self._max_attempts):
                try:
                    resp = client.post(url, json=payload, headers=headers, timeout=self._timeout_s)
                    if 200 <= resp.status_code < 300:
                        return WebhookRecord(
                            event_id=event_id,
                            type=event_type,
                            occurred_at=occurred_at,
                            data=data,
                            delivered=True,
                            error=None,
                        )
                    last_error = f"HTTP {resp.status_code}"
                except httpx.HTTPError as exc:
                    last_error = str(exc)

                if attempt < self._max_attempts - 1:
                    delay = self._backoff_s[min(attempt, len(self._backoff_s) - 1)]
                    self._sleep_fn(delay)
        finally:
            if self._client_factory is None:
                client.close()

        return WebhookRecord(
            event_id=event_id,
            type=event_type,
            occurred_at=occurred_at,
            data=data,
            delivered=False,
            error=last_error,
        )

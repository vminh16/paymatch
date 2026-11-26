"""Per-caller X-Service-Key authentication & authorization matrix for Payment Gate.

Matrix from docs/05-api/gate-api.md & contracts/openapi/gate.yaml:
  - merchant-api : POST /gate/evaluate, GET /gate/intents, GET /gate/intents/{id},
                   POST /gate/escrows, GET /gate/escrows/{id}
  - core-worker  : POST /gate/evaluate, GET /gate/budgets/{t}/{d},
                   POST /gate/intents, :execute, :cancel, GET /gate/intents, GET /gate/intents/{id},
                   POST /gate/escrows/{id}:release, :refund, GET /gate/escrows/{id}
  - internal-api : POST /gate/evaluate, GET /gate/budgets/{t}/{d}
  - console-api  : GET /gate/intents/{id} ONLY (requires X-Ticket-Id header -> else 403 TICKET_REQUIRED)
  - agent-worker : NEVER has a Gate key
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Literal

from fastapi import Header, Request

from gate.adapters.http.errors import HttpProblemError
from gate.config import Settings

Caller = Literal["merchant-api", "core-worker", "internal-api", "console-api"]


def identify_caller(settings: Settings, service_key: str) -> Caller | None:
    candidates: tuple[tuple[Caller, str], ...] = (
        ("merchant-api", settings.merchant_api_service_key),
        ("core-worker", settings.core_worker_service_key),
        ("internal-api", settings.internal_api_service_key),
        ("console-api", settings.console_api_service_key),
    )
    for caller_name, expected_key in candidates:
        if expected_key and hmac.compare_digest(service_key, expected_key):
            return caller_name
    return None


def require_caller(*allowed: Caller) -> Callable[..., Caller]:
    """Return a FastAPI dependency enforcing X-Service-Key and caller matrix."""

    def dependency(
        request: Request,
        x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    ) -> Caller:
        if not x_service_key:
            raise HttpProblemError(
                status=401,
                code="UNAUTHENTICATED",
                title="Authentication required",
                detail="Thiếu hoặc không hợp lệ X-Service-Key.",
            )

        settings: Settings = request.app.state.settings
        caller = identify_caller(settings, x_service_key)
        if caller is None:
            raise HttpProblemError(
                status=401,
                code="UNAUTHENTICATED",
                title="Authentication required",
                detail="Thiếu hoặc không hợp lệ X-Service-Key.",
            )

        if allowed and caller not in allowed:
            raise HttpProblemError(
                status=403,
                code="FORBIDDEN",
                title="Caller not permitted for endpoint",
                detail="Khóa dịch vụ hiện tại không có quyền gọi endpoint này trên Payment Gate.",
            )

        return caller

    return dependency

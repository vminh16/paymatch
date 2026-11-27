"""X-Service-Key authentication with per-caller authorization and DEMO_MODE exemptions."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Literal

from fastapi import Header, Request

from sim_world.config import Settings
from sim_world.errors import ProblemError

Caller = Literal["core", "gate"]


def _identify_caller(settings: Settings, key: str) -> Caller | None:
    if settings.core_service_key and hmac.compare_digest(key, settings.core_service_key):
        return "core"
    if settings.gate_service_key and hmac.compare_digest(key, settings.gate_service_key):
        return "gate"
    return None


def require_caller(
    *allowed: Caller,
    allow_demo_mode: bool = False,
) -> Callable[..., str]:
    """Return a FastAPI dependency enforcing X-Service-Key and caller role."""

    def dependency(
        request: Request,
        x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    ) -> str:
        settings: Settings = request.app.state.settings
        if allow_demo_mode and settings.demo_mode and x_service_key is None:
            return "demo"

        if not x_service_key:
            raise ProblemError(
                status=401,
                code="UNAUTHENTICATED",
                title="Missing service key",
                detail="X-Service-Key header is required.",
            )

        caller = _identify_caller(settings, x_service_key)
        if caller is None:
            raise ProblemError(
                status=401,
                code="UNAUTHENTICATED",
                title="Invalid service key",
                detail="The provided X-Service-Key is not recognized.",
            )

        if allowed and caller not in allowed:
            raise ProblemError(
                status=403,
                code="FORBIDDEN",
                title="Service caller not allowed",
                detail=f"Caller '{caller}' is not permitted to access this endpoint.",
            )

        return caller

    return dependency

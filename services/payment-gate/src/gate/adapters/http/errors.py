"""RFC 9457 Problem Details helpers for Payment Gate HTTP responses."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class HttpProblemError(Exception):
    def __init__(
        self,
        *,
        status: int,
        code: str,
        title: str,
        detail: str,
        errors: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.errors = errors
        self.extra = extra or {}


def build_problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    slug = code.lower().replace("_", "-")
    payload: dict[str, Any] = {
        "type": f"https://paymatch.dev/problems/{slug}",
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "instance": str(request.url.path),
    }
    if errors is not None:
        payload["errors"] = errors
    if extra:
        payload.update(extra)
    return JSONResponse(
        status_code=status,
        content=payload,
        media_type="application/problem+json",
    )

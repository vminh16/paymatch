"""RFC 9457 Problem Details error helpers for sim-world."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.errors = errors


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
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
    return JSONResponse(
        status_code=status,
        content=payload,
        media_type="application/problem+json",
    )

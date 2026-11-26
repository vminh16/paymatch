"""RFC 9457 Problem Details error model and FastAPI handlers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.shared.ids import new_id


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str,
        *,
        errors: list[dict[str, Any]] | None = None,
        current_status: str | None = None,
        existing_invoice_id: str | None = None,
        gate_reasons: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.errors = errors
        self.current_status = current_status
        self.existing_invoice_id = existing_invoice_id
        self.gate_reasons = gate_reasons


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
    current_status: str | None = None,
    existing_invoice_id: str | None = None,
    gate_reasons: list[dict[str, Any]] | None = None,
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
    if current_status is not None:
        payload["current_status"] = current_status
    if existing_invoice_id is not None:
        payload["existing_invoice_id"] = existing_invoice_id
    if gate_reasons is not None:
        payload["gate_reasons"] = gate_reasons
    req_id = getattr(request.state, "request_id", None) or new_id("req")
    return JSONResponse(
        status_code=status,
        content=payload,
        media_type="application/problem+json",
        headers={"X-Request-Id": req_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        req_id = new_id("req")
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers.setdefault("X-Request-Id", req_id)
        return response

    @app.exception_handler(ProblemError)
    async def _handle_problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(
            request,
            status=exc.status,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            errors=exc.errors,
            current_status=exc.current_status,
            existing_invoice_id=exc.existing_invoice_id,
            gate_reasons=exc.gate_reasons,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errs = []
        for item in exc.errors():
            loc = ".".join(str(p) for p in item.get("loc", []) if p not in {"body", "query", "path", "header"})
            errs.append(
                {
                    "field": loc or "request",
                    "code": item.get("type", "invalid"),
                    "detail": item.get("msg", "Validation error"),
                }
            )
        return problem_response(
            request,
            status=400,
            code="VALIDATION_FAILED",
            title="Validation failed",
            detail="Dữ liệu đầu vào không hợp lệ.",
            errors=errs,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "VALIDATION_FAILED",
            409: "INVALID_STATE",
        }
        code = code_map.get(exc.status_code, "VALIDATION_FAILED")
        return problem_response(
            request,
            status=exc.status_code,
            code=code,
            title=str(exc.detail or "HTTP error"),
            detail=str(exc.detail or "HTTP error"),
        )

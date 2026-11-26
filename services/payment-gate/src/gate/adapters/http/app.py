"""FastAPI app factory, exception handlers, middleware, and background poller lifespan."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from gate.adapters.http.errors import HttpProblemError, build_problem_response
from gate.adapters.http.routes import router
from gate.adapters.http.serializers import to_gate_reason, to_payment_intent
from gate.adapters.postgres.ledger_store import PostgresLedgerStore
from gate.adapters.postgres.read_store import PostgresCoreReadStore
from gate.adapters.sim_world.clock import SimWorldClock, SystemClock
from gate.adapters.sim_world.rail import SimWorldPaymentRail
from gate.application.poller import GateBackgroundPoller
from gate.application.service import PaymentGateService, UpstreamTimeoutError
from gate.config import Settings
from gate.domain.models import (
    GateDeniedError,
    InvalidStateTransitionError,
    PolicyUnavailableError,
    ResourceNotFoundError,
    TenantMismatchError,
)
from gate.ids import new_id
from gate.ports.clock import Clock
from gate.ports.ledger_store import LedgerStore
from gate.ports.rail import PaymentRail
from gate.ports.read_store import CoreReadStore

logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    read_store: CoreReadStore | None = None,
    ledger_store: LedgerStore | None = None,
    rail: PaymentRail | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    cfg = settings or Settings.from_env()
    r_store = read_store or PostgresCoreReadStore(cfg.database_url)
    l_store = ledger_store or PostgresLedgerStore(cfg.database_url)
    p_rail = rail or SimWorldPaymentRail(
        sim_url=cfg.sim_url,
        service_key=cfg.sim_gate_service_key,
        timeout_seconds=cfg.rail_timeout_seconds,
    )
    clk = clock or (
        SimWorldClock(sim_url=cfg.sim_url, service_key=cfg.sim_gate_service_key)
        if cfg.demo_mode
        else SystemClock()
    )

    service = PaymentGateService(
        read_store=r_store,
        ledger_store=l_store,
        rail=p_rail,
        clock=clk,
        authorization_ttl_seconds=cfg.authorization_ttl_seconds,
    )
    poller = GateBackgroundPoller(
        ledger_store=l_store,
        rail=p_rail,
        clock=clk,
        stuck_threshold_seconds=cfg.stuck_threshold_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        stop_event = asyncio.Event()
        task: asyncio.Task[None] | None = None

        async def _poll_loop() -> None:
            while not stop_event.is_set():
                try:
                    await asyncio.to_thread(poller.run_once)
                except Exception:
                    logger.exception("Payment Gate background poller tick failed")
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=cfg.poll_interval_seconds)
                except TimeoutError:
                    pass

        if cfg.enable_background_poller:
            task = asyncio.create_task(_poll_loop())
        try:
            yield
        finally:
            stop_event.set()
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(
        title="PayMatch Payment Gate API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = cfg
    app.state.service = service
    app.state.poller = poller

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-Id") or new_id("req")
        response = await call_next(request)
        response.headers["X-Request-Id"] = req_id
        return response

    @app.exception_handler(HttpProblemError)
    async def handle_http_problem(request: Request, exc: HttpProblemError) -> JSONResponse:
        return build_problem_response(
            request,
            status=exc.status,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            errors=exc.errors,
            extra=exc.extra,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        items = [
            {
                "field": ".".join(str(loc) for loc in err.get("loc", ())),
                "code": str(err.get("type", "invalid")),
                "detail": str(err.get("msg", "Invalid input")),
            }
            for err in exc.errors()
        ]
        return build_problem_response(
            request,
            status=400,
            code="VALIDATION_FAILED",
            title="Validation failed",
            detail="Dữ liệu đầu vào không hợp lệ.",
            errors=items,
        )

    @app.exception_handler(TenantMismatchError)
    async def handle_tenant_mismatch(request: Request, exc: TenantMismatchError) -> JSONResponse:
        return build_problem_response(
            request,
            status=403,
            code="TENANT_MISMATCH",
            title="Tenant mismatch",
            detail=str(exc),
        )

    @app.exception_handler(ResourceNotFoundError)
    async def handle_not_found(request: Request, exc: ResourceNotFoundError) -> JSONResponse:
        return build_problem_response(
            request,
            status=404,
            code="NOT_FOUND",
            title="Resource not found",
            detail=str(exc),
        )

    @app.exception_handler(InvalidStateTransitionError)
    async def handle_invalid_state(
        request: Request, exc: InvalidStateTransitionError
    ) -> JSONResponse:
        extra: dict[str, Any] = {}
        if exc.current_status is not None:
            extra["current_status"] = exc.current_status
        return build_problem_response(
            request,
            status=409,
            code="INVALID_STATE",
            title="Invalid state",
            detail=str(exc),
            extra=extra,
        )

    @app.exception_handler(PolicyUnavailableError)
    async def handle_policy_unavailable(
        request: Request, exc: PolicyUnavailableError
    ) -> JSONResponse:
        return build_problem_response(
            request,
            status=503,
            code="UPSTREAM_UNAVAILABLE",
            title="Policy store unavailable",
            detail=str(exc),
            extra={
                "gate_reasons": [
                    {
                        "code": "POLICY_UNAVAILABLE",
                        "layer": "platform_policy",
                        "detail": str(exc),
                    }
                ]
            },
        )

    @app.exception_handler(UpstreamTimeoutError)
    async def handle_upstream_timeout(request: Request, exc: UpstreamTimeoutError) -> JSONResponse:
        return build_problem_response(
            request,
            status=504,
            code="UPSTREAM_TIMEOUT",
            title="Upstream rail timeout",
            detail=str(exc),
        )

    @app.exception_handler(GateDeniedError)
    async def handle_gate_denied(request: Request, exc: GateDeniedError) -> JSONResponse:
        serialized_reasons = [to_gate_reason(r).model_dump(mode="json") for r in exc.reasons]
        if exc.policy_unavailable:
            return build_problem_response(
                request,
                status=503,
                code="UPSTREAM_UNAVAILABLE",
                title="Policy store unavailable",
                detail=exc.detail,
                extra={"gate_reasons": serialized_reasons},
            )
        if exc.kill_switch_blocked:
            extra: dict[str, Any] = {"gate_reasons": serialized_reasons}
            if exc.payment_intent is not None:
                extra["payment_intent"] = to_payment_intent(exc.payment_intent).model_dump(
                    mode="json"
                )
            return build_problem_response(
                request,
                status=423,
                code="KILL_SWITCH_ACTIVE",
                title="Kill switch active",
                detail="Thao tác chi bị khóa do kill switch đang bật.",
                extra=extra,
            )

        extra = {
            "gate_reasons": serialized_reasons,
            "payment_intent": (
                to_payment_intent(exc.payment_intent).model_dump(mode="json")
                if exc.payment_intent is not None
                else None
            ),
        }
        return build_problem_response(
            request,
            status=422,
            code="GATE_DENIED",
            title="Payment Gate denied request",
            detail=exc.detail,
            extra=extra,
        )

    app.include_router(router)
    return app


app = create_app()

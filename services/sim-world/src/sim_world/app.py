"""FastAPI application factory for sim-world (/sim/*, port 8200)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from sim_world.config import Settings
from sim_world.errors import ProblemError, problem_response
from sim_world.ids import new_id
from sim_world.jwt_keys import IdentityKeyStore
from sim_world.routes import chat, identity, lookups, rails, scenario, sources
from sim_world.schemas import HealthResponse, ReadyResponse
from sim_world.store import SimWorldStore
from sim_world.webhooks import WebhookDispatcher


def create_app(
    settings: Settings | None = None,
    *,
    webhook_dispatcher: WebhookDispatcher | None = None,
) -> FastAPI:
    cfg = settings or Settings.from_env()
    keys = IdentityKeyStore()
    dispatcher = webhook_dispatcher or WebhookDispatcher(
        core_internal_url=cfg.core_internal_url,
        service_key=cfg.webhook_service_key,
    )
    store = SimWorldStore(
        data_dir=cfg.data_dir,
        keys=keys,
        webhooks=dispatcher,
        demo_mode=cfg.demo_mode,
    )
    store.reset(dataset=cfg.default_dataset, seed=cfg.default_seed)

    app = FastAPI(
        title="PayMatch sim-world API",
        version="0.2.0",
        docs_url="/sim/docs",
        openapi_url="/sim/openapi.json",
    )
    app.state.settings = cfg
    app.state.keys = keys
    app.state.store = store

    if cfg.demo_mode:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or new_id("req")
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(ProblemError)
    async def handle_problem_error(request: Request, exc: ProblemError):
        return problem_response(
            request,
            status=exc.status,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            errors=exc.errors,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        formatted = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", []) if part != "body")
            formatted.append(
                {
                    "field": loc or "request",
                    "code": str(err.get("type", "invalid")),
                    "detail": str(err.get("msg", "Invalid input")),
                }
            )
        return problem_response(
            request,
            status=400,
            code="VALIDATION_FAILED",
            title="Request validation failed",
            detail="One or more request fields failed schema validation.",
            errors=formatted,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException):
        code_map = {
            400: "VALIDATION_FAILED",
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "INVALID_STATE",
        }
        return problem_response(
            request,
            status=exc.status_code,
            code=code_map.get(exc.status_code, "HTTP_ERROR"),
            title=str(exc.detail),
            detail=str(exc.detail),
        )

    @app.get("/sim/healthz", response_model=HealthResponse, tags=["system"])
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/sim/readyz", response_model=ReadyResponse, tags=["system"])
    def readyz(request: Request) -> dict:
        s: SimWorldStore = request.app.state.store
        if not s.ready:
            raise ProblemError(
                status=503,
                code="UPSTREAM_UNAVAILABLE",
                title="Service not ready",
                detail="Dataset has not been loaded.",
            )
        return {"status": "ready", "dataset": s.dataset, "loaded_at": s.loaded_at}

    app.include_router(identity.router)
    app.include_router(rails.router)
    app.include_router(sources.router)
    app.include_router(chat.router)
    app.include_router(lookups.router)
    app.include_router(scenario.router)

    return app


app = create_app()

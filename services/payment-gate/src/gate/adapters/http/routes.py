"""FastAPI routes for Payment Gate (`/gate/*`, port 8100) per contracts/openapi/gate.yaml."""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response
from paymatch_contracts import Escrow as EscrowContract
from paymatch_contracts.gate import (
    CancelPaymentIntentRequest,
    CreateEscrowRequest,
    CreatePaymentIntentRequest,
    DailyBudgetResponse,
    EvaluateEscrowRequest,
    EvaluateInvoiceRequest,
    EvaluateResponse,
    ExecutePaymentIntentRequest,
    HealthResponse,
    PaymentIntent,
    PaymentIntentPage,
    PaymentIntentStatus,
    ReadyResponse,
    RefundEscrowRequest,
    ReleaseEscrowRequest,
)

from gate.adapters.http.auth import Caller, require_caller
from gate.adapters.http.errors import HttpProblemError
from gate.adapters.http.serializers import (
    to_escrow,
    to_evaluate_response,
    to_payment_intent,
    to_payment_intent_page,
)
from gate.application.service import PaymentGateService

router = APIRouter(prefix="/gate")

_TENANT_PATTERN = r"^ten_[0-9A-HJKMNP-TV-Z]{26}$"
_INVOICE_PATTERN = r"^inv_[0-9A-HJKMNP-TV-Z]{26}$"
_PI_PATTERN = r"^pi_[0-9A-HJKMNP-TV-Z]{26}$"
_ESC_PATTERN = r"^esc_[0-9A-HJKMNP-TV-Z]{26}$"


def _get_service(request: Request) -> PaymentGateService:
    return request.app.state.service


def _extract_trace_id(traceparent: str | None) -> str | None:
    if not traceparent:
        return None
    parts = traceparent.strip().split("-")
    if len(parts) == 4 and len(parts[1]) == 32:
        return parts[1]
    return None


# --- System probes (unauthenticated) ---


@router.get("/healthz", response_model=HealthResponse, tags=["System"])
def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse, tags=["System"])
def readyz(service: PaymentGateService = Depends(_get_service)) -> ReadyResponse:
    if not service.is_ready():
        raise HttpProblemError(
            status=503,
            code="UPSTREAM_UNAVAILABLE",
            title="Gate not ready",
            detail="Payment Gate chưa sẵn sàng (DB ledger/core/control/risk không khả dụng).",
        )
    return ReadyResponse(status="ready")


# --- Evaluate ---


@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    tags=["Evaluate"],
    dependencies=[Depends(require_caller("merchant-api", "core-worker", "internal-api"))],
)
def evaluate_payment_policy(
    body: EvaluateInvoiceRequest | EvaluateEscrowRequest,
    service: PaymentGateService = Depends(_get_service),
) -> EvaluateResponse:
    if isinstance(body, EvaluateInvoiceRequest):
        res = service.evaluate_invoice_policy(
            invoice_id=body.invoice_id,
            tenant_id=body.tenant_id,
        )
    else:
        res = service.evaluate_escrow_policy(
            purchase_order_id=body.purchase_order_id,
            vendor_account_id=body.vendor_account_id,
            amount_vnd=body.amount_vnd,
            tenant_id=body.tenant_id,
        )
    return to_evaluate_response(res)


# --- Budgets ---


@router.get(
    "/budgets/{tenant_id}/{date}",
    response_model=DailyBudgetResponse,
    tags=["Budgets"],
    dependencies=[Depends(require_caller("core-worker", "internal-api"))],
)
def get_daily_budget(
    tenant_id: Annotated[str, Path(pattern=_TENANT_PATTERN)],
    date: date_type,
    service: PaymentGateService = Depends(_get_service),
) -> DailyBudgetResponse:
    summary = service.get_daily_budget_summary(tenant_id=tenant_id, budget_date=date)
    return DailyBudgetResponse(**summary)


# --- Payment Intents ---


@router.post(
    "/intents",
    response_model=PaymentIntent,
    status_code=201,
    tags=["Intents"],
    dependencies=[Depends(require_caller("core-worker"))],
)
def create_payment_intent(
    body: CreatePaymentIntentRequest,
    response: Response,
    traceparent: str | None = Header(default=None),
    service: PaymentGateService = Depends(_get_service),
) -> PaymentIntent:
    outcome = service.create_intent(
        invoice_id=body.invoice_id,
        approval_id=body.approval_id,
        tenant_id=body.tenant_id,
        trace_id=_extract_trace_id(traceparent),
    )
    response.status_code = 201 if outcome.created else 200
    return to_payment_intent(outcome.intent)


@router.get(
    "/intents",
    response_model=PaymentIntentPage,
    tags=["Intents"],
    dependencies=[Depends(require_caller("merchant-api", "core-worker"))],
)
def list_payment_intents(
    tenant_id: Annotated[str, Query(pattern=_TENANT_PATTERN)],
    invoice_id: Annotated[str | None, Query(pattern=_INVOICE_PATTERN)] = None,
    status: list[PaymentIntentStatus] | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = Query(default=None),
    service: PaymentGateService = Depends(_get_service),
) -> PaymentIntentPage:
    statuses = tuple(s.value for s in status) if status else None
    items, next_cursor = service.list_intents(
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        statuses=statuses,
        limit=limit,
        cursor=cursor,
    )
    return to_payment_intent_page(items, next_cursor)


@router.get(
    "/intents/{payment_intent_id}",
    response_model=PaymentIntent,
    tags=["Intents"],
)
def get_payment_intent(
    payment_intent_id: Annotated[str, Path(pattern=_PI_PATTERN)],
    caller: Caller = Depends(require_caller("merchant-api", "core-worker", "console-api")),
    x_ticket_id: str | None = Header(default=None, alias="X-Ticket-Id"),
    service: PaymentGateService = Depends(_get_service),
) -> PaymentIntent:
    if caller == "console-api" and (not x_ticket_id or not x_ticket_id.strip()):
        raise HttpProblemError(
            status=403,
            code="TICKET_REQUIRED",
            title="Support ticket required",
            detail="console-api bắt buộc truyền header X-Ticket-Id khi tra PaymentIntent.",
        )
    intent = service.get_intent(payment_intent_id)
    return to_payment_intent(intent)


@router.post(
    "/intents/{payment_intent_id}:execute",
    response_model=PaymentIntent,
    tags=["Intents"],
    dependencies=[Depends(require_caller("core-worker"))],
)
def execute_payment_intent(
    payment_intent_id: Annotated[str, Path(pattern=_PI_PATTERN)],
    body: ExecutePaymentIntentRequest,
    traceparent: str | None = Header(default=None),
    service: PaymentGateService = Depends(_get_service),
) -> PaymentIntent:
    intent = service.execute_intent(
        payment_intent_id=payment_intent_id,
        tenant_id=body.tenant_id,
        trace_id=_extract_trace_id(traceparent),
    )
    return to_payment_intent(intent)


@router.post(
    "/intents/{payment_intent_id}:cancel",
    response_model=PaymentIntent,
    tags=["Intents"],
    dependencies=[Depends(require_caller("core-worker"))],
)
def cancel_payment_intent(
    payment_intent_id: Annotated[str, Path(pattern=_PI_PATTERN)],
    body: CancelPaymentIntentRequest,
    traceparent: str | None = Header(default=None),
    service: PaymentGateService = Depends(_get_service),
) -> PaymentIntent:
    intent = service.cancel_intent(
        payment_intent_id=payment_intent_id,
        reason=body.reason.value,
        tenant_id=body.tenant_id,
        trace_id=_extract_trace_id(traceparent),
    )
    return to_payment_intent(intent)


# --- Escrows (F7) ---


@router.post(
    "/escrows",
    response_model=EscrowContract,
    status_code=201,
    tags=["Escrows"],
    dependencies=[Depends(require_caller("merchant-api"))],
)
def create_escrow(
    body: CreateEscrowRequest,
    response: Response,
    traceparent: str | None = Header(default=None),
    service: PaymentGateService = Depends(_get_service),
) -> EscrowContract:
    outcome = service.create_escrow(
        approval_id=body.approval_id,
        expires_on=body.expires_on,
        tenant_id=body.tenant_id,
        trace_id=_extract_trace_id(traceparent),
    )
    response.status_code = 201 if outcome.created else 200
    return to_escrow(outcome.escrow)


@router.get(
    "/escrows/{escrow_id}",
    response_model=EscrowContract,
    tags=["Escrows"],
    dependencies=[Depends(require_caller("merchant-api", "core-worker"))],
)
def get_escrow(
    escrow_id: Annotated[str, Path(pattern=_ESC_PATTERN)],
    service: PaymentGateService = Depends(_get_service),
) -> EscrowContract:
    escrow = service.get_escrow(escrow_id)
    return to_escrow(escrow)


@router.post(
    "/escrows/{escrow_id}:release",
    response_model=EscrowContract,
    tags=["Escrows"],
    dependencies=[Depends(require_caller("core-worker"))],
)
def release_escrow(
    escrow_id: Annotated[str, Path(pattern=_ESC_PATTERN)],
    body: ReleaseEscrowRequest,
    traceparent: str | None = Header(default=None),
    service: PaymentGateService = Depends(_get_service),
) -> EscrowContract:
    escrow = service.release_escrow(
        escrow_id=escrow_id,
        approval_id=body.approval_id,
        goods_receipt_id=body.goods_receipt_id,
        tenant_id=body.tenant_id,
        trace_id=_extract_trace_id(traceparent),
    )
    return to_escrow(escrow)


@router.post(
    "/escrows/{escrow_id}:refund",
    response_model=EscrowContract,
    tags=["Escrows"],
    dependencies=[Depends(require_caller("core-worker"))],
)
def refund_escrow(
    escrow_id: Annotated[str, Path(pattern=_ESC_PATTERN)],
    body: RefundEscrowRequest,
    traceparent: str | None = Header(default=None),
    service: PaymentGateService = Depends(_get_service),
) -> EscrowContract:
    escrow = service.refund_escrow(
        escrow_id=escrow_id,
        reason=body.reason.value,
        tenant_id=body.tenant_id,
        trace_id=_extract_trace_id(traceparent),
    )
    return to_escrow(escrow)

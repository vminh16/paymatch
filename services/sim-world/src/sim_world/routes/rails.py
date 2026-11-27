"""Payment rails routes: /sim/rails/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from sim_world.auth import require_caller
from sim_world.schemas import (
    CardDetailResponse,
    CreateCardRequest,
    CreateCardResponse,
    CreateEscrowRequest,
    CreateEscrowResponse,
    EscrowActionRequest,
    EscrowActionResponse,
    TransferRequest,
    TransferResponse,
    WalletResponse,
)
from sim_world.store import SimWorldStore

router = APIRouter(prefix="/sim/rails", tags=["rails"])
_gate_only = [Depends(require_caller("gate"))]
_core_or_gate = [Depends(require_caller("core", "gate"))]


@router.post("/transfers", response_model=TransferResponse, dependencies=_gate_only)
def create_transfer(body: TransferRequest, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.create_transfer(
        idempotency_key=body.idempotency_key,
        from_wallet_id=body.from_wallet_id,
        bank_code=body.to.bank_code,
        account_number=body.to.account_number,
        account_name=body.to.account_name,
        amount_vnd=body.amount_vnd,
        memo=body.memo,
    )


@router.get("/transfers/{idempotency_key}", response_model=TransferResponse, dependencies=_gate_only)
def get_transfer(idempotency_key: str, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.get_transfer(idempotency_key)


@router.post("/cards", response_model=CreateCardResponse, dependencies=_gate_only)
def create_card(body: CreateCardRequest, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.create_card(
        idempotency_key=body.idempotency_key,
        from_wallet_id=body.from_wallet_id,
        merchant_id=body.merchant_id,
        amount_vnd=body.amount_vnd,
        single_use=body.single_use,
    )


@router.get("/cards/{card_id}", response_model=CardDetailResponse, dependencies=_gate_only)
def get_card(card_id: str, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.get_card(card_id)


@router.post("/escrows", response_model=CreateEscrowResponse, dependencies=_gate_only)
def create_escrow(body: CreateEscrowRequest, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.create_escrow(
        idempotency_key=body.idempotency_key,
        from_wallet_id=body.from_wallet_id,
        to=body.to.model_dump(),
        amount_vnd=body.amount_vnd,
        expires_on=body.expires_on,
    )


@router.post(
    "/escrows/{rail_escrow_id}:release",
    response_model=EscrowActionResponse,
    dependencies=_gate_only,
)
def release_escrow(
    rail_escrow_id: str,
    body: EscrowActionRequest,
    request: Request,
) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.release_escrow(rail_escrow_id, body.idempotency_key)


@router.post(
    "/escrows/{rail_escrow_id}:refund",
    response_model=EscrowActionResponse,
    dependencies=_gate_only,
)
def refund_escrow(
    rail_escrow_id: str,
    body: EscrowActionRequest,
    request: Request,
) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.refund_escrow(rail_escrow_id, body.idempotency_key)


@router.get("/wallets/{wallet_id}", response_model=WalletResponse, dependencies=_core_or_gate)
def get_wallet(wallet_id: str, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.get_wallet(wallet_id)

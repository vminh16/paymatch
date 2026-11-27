"""Official lookup routes: /sim/einvoice, /sim/tax, /sim/simo, /sim/revenue."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from sim_world.auth import require_caller
from sim_world.schemas import (
    EinvoiceLookupResponse,
    RevenueResponse,
    SimoCheckResponse,
    TaxpayerResponse,
    TaxRiskListResponse,
)
from sim_world.store import SimWorldStore

router = APIRouter(
    prefix="/sim",
    tags=["lookups"],
    dependencies=[Depends(require_caller("core"))],
)


@router.get("/einvoice/invoices", response_model=EinvoiceLookupResponse)
def lookup_einvoice(
    request: Request,
    seller_tax_id: str = Query(..., min_length=1),
    symbol: str = Query(..., min_length=1),
    number: str = Query(..., min_length=1),
) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.lookup_einvoice(seller_tax_id=seller_tax_id, symbol=symbol, number=number)


@router.get("/tax/taxpayers/{tax_id}", response_model=TaxpayerResponse)
def get_taxpayer(tax_id: str, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.get_taxpayer(tax_id)


@router.get("/tax/risk-list/{tax_id}", response_model=TaxRiskListResponse)
def get_tax_risk_list(tax_id: str, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.get_tax_risk_list(tax_id)


@router.get("/simo/indicators:check", response_model=SimoCheckResponse)
def check_simo_indicator(
    request: Request,
    kind: Literal["account_hash", "phone", "tax_id"] = Query(...),
    value_hash: str = Query(..., min_length=1),
) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.check_simo(kind=kind, value_hash=value_hash)


@router.get("/revenue", response_model=RevenueResponse)
def get_revenue(
    request: Request,
    wallet_id: str = Query(..., min_length=1),
    store_ref: str = Query(..., min_length=1),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.get_revenue(wallet_id=wallet_id, store_ref=store_ref, month=month)

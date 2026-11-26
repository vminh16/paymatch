"""Scenario control routes: /sim/scenario*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from sim_world.auth import require_caller
from sim_world.schemas import (
    CardSwipeRequest,
    CardSwipeResponse,
    ClockAdvanceRequest,
    ClockResponse,
    ScenarioCatalogItem,
    ScenarioResetRequest,
    ScenarioResetResponse,
    ScenarioStateResponse,
    SendScenarioChatRequest,
    SendScenarioChatResponse,
    SendScenarioInvoiceRequest,
    SendScenarioInvoiceResponse,
)
from sim_world.store import SimWorldStore

router = APIRouter(
    prefix="/sim",
    tags=["scenario"],
    dependencies=[Depends(require_caller("core", "gate", allow_demo_mode=True))],
)


@router.post("/scenario:reset", response_model=ScenarioResetResponse)
def reset_scenario(body: ScenarioResetRequest, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.reset(dataset=body.dataset, seed=body.seed)


@router.get("/scenario/state", response_model=ScenarioStateResponse)
def get_scenario_state(request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.get_scenario_state()


@router.get("/scenario/catalog", response_model=list[ScenarioCatalogItem])
def get_scenario_catalog(request: Request) -> list[dict]:
    store: SimWorldStore = request.app.state.store
    return store.get_scenario_catalog()


@router.post(
    "/scenario/invoices:send",
    response_model=SendScenarioInvoiceResponse,
    response_model_exclude_none=True,
)
def send_scenario_invoice(body: SendScenarioInvoiceRequest, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.send_scenario_invoice(
        template_id=body.template_id,
        overrides=body.overrides,
    )


@router.post("/scenario/chat-messages", response_model=SendScenarioChatResponse)
def send_scenario_chat_message(body: SendScenarioChatRequest, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.inject_chat_message(thread_id=body.thread_id, text=body.text)


@router.post("/scenario/cards/{card_id}:swipe", response_model=CardSwipeResponse)
def swipe_scenario_card(
    card_id: str,
    body: CardSwipeRequest,
    request: Request,
) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.swipe_card(
        card_id,
        merchant_id=body.merchant_id,
        amount_vnd=body.amount_vnd,
    )


@router.get("/scenario/clock", response_model=ClockResponse)
def get_scenario_clock(request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return {"now": store.get_clock()}


@router.post("/scenario/clock:advance", response_model=ClockResponse)
def advance_scenario_clock(body: ClockAdvanceRequest, request: Request) -> dict:
    store: SimWorldStore = request.app.state.store
    return {"now": store.advance_clock(body.to)}

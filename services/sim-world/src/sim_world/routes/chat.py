"""Chat routes: /sim/chat/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from sim_world.auth import require_caller
from sim_world.schemas import ChatMessage, ChatThread
from sim_world.store import SimWorldStore

router = APIRouter(
    prefix="/sim/chat",
    tags=["chat"],
    dependencies=[Depends(require_caller("core"))],
)


@router.get("/threads", response_model=list[ChatThread])
def list_chat_threads(
    request: Request,
    tenant_ref: str = Query(..., min_length=1),
    counterparty_phone: str | None = Query(default=None),
) -> list[dict]:
    store: SimWorldStore = request.app.state.store
    return store.list_chat_threads(
        tenant_ref=tenant_ref,
        counterparty_phone=counterparty_phone,
    )


@router.get("/threads/{thread_id}/messages", response_model=list[ChatMessage])
def list_chat_messages(
    thread_id: str,
    request: Request,
    since: str | None = Query(default=None),
) -> list[dict]:
    store: SimWorldStore = request.app.state.store
    return store.list_chat_messages(thread_id, since=since)

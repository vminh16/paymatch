"""Invoice source routes: /sim/inbox/* and /sim/bills*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response

from sim_world.auth import require_caller
from sim_world.schemas import BillsPage, InboxMessagesPage
from sim_world.store import SimWorldStore

router = APIRouter(
    prefix="/sim",
    dependencies=[Depends(require_caller("core"))],
)


@router.get("/inbox/messages", response_model=InboxMessagesPage, tags=["inbox"])
def list_inbox_messages(
    request: Request,
    mailbox: str = Query(..., min_length=1),
    after: str | None = Query(default=None),
    from_addr: str | None = Query(default=None, alias="from"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.list_inbox_messages(
        mailbox=mailbox,
        after=after,
        from_addr=from_addr,
        limit=limit,
    )


@router.get(
    "/inbox/messages/{message_id}/attachments/{attachment_id}",
    tags=["inbox"],
)
def get_inbox_attachment(
    message_id: str,
    attachment_id: str,
    request: Request,
) -> Response:
    store: SimWorldStore = request.app.state.store
    content_type, raw = store.get_inbox_attachment(message_id, attachment_id)
    return Response(content=raw, media_type=content_type)


@router.get("/bills", response_model=BillsPage, tags=["bills"])
def list_bills(
    request: Request,
    wallet_id: str = Query(..., min_length=1),
    after: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    store: SimWorldStore = request.app.state.store
    return store.list_bills(wallet_id=wallet_id, after=after, limit=limit)


@router.get("/bills/{bill_id}/document", tags=["bills"])
def get_bill_document(bill_id: str, request: Request) -> Response:
    store: SimWorldStore = request.app.state.store
    raw = store.get_bill_document(bill_id)
    return Response(content=raw, media_type="application/xml")

"""Poller use case for ingesting invoices from inbox and utility bills behind InvoiceSourcePort."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

import psycopg
from psycopg.types.json import Jsonb

from core.ingest.application.ingest_invoice import IngestCommand, IngestResult, ingest_invoice
from core.shared.clock import Clock, SystemClock
from core.shared.errors import ProblemError
from core.shared.ids import new_id


@dataclass(frozen=True)
class InboxAttachment:
    attachment_id: str
    filename: str
    content_type: str
    raw_bytes: bytes


@dataclass(frozen=True)
class InboxMessage:
    message_id: str
    from_address: str
    subject: str
    body_text: str
    received_at: datetime
    attachments: tuple[InboxAttachment, ...]


@dataclass(frozen=True)
class UtilityBill:
    bill_id: str
    provider: str  # electricity | water
    customer_code: str
    store_ref: str
    period: str
    amount_vnd: int
    readings: dict[str, Any]
    xml_attachment_id: str | None
    due_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    total_usage: str | None = None
    usage_unit: str | None = None
    subtotal_vnd: int | None = None
    vat_total_vnd: int | None = None
    statement_no: str | None = None


class InvoiceSourcePort(Protocol):
    def list_inbox_messages(
        self, mailbox: str, after: str | None = None
    ) -> tuple[list[InboxMessage], str | None]: ...

    def list_bills(
        self, wallet_id: str, after: str | None = None
    ) -> tuple[list[UtilityBill], str | None]: ...

    def fetch_bill_document(self, bill_id: str) -> bytes | None: ...


def _get_cursor(conn: psycopg.Connection, tenant_id: str, source: str) -> str | None:
    row = conn.execute(
        "SELECT cursor FROM core.poll_cursors WHERE tenant_id = %s AND source = %s",
        (tenant_id, source),
    ).fetchone()
    return row["cursor"] if row else None


def _set_cursor(conn: psycopg.Connection, tenant_id: str, source: str, cursor: str | None) -> None:
    if cursor is None:
        return
    conn.execute(
        """
        INSERT INTO core.poll_cursors (tenant_id, source, cursor, updated_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (tenant_id, source) DO UPDATE SET cursor = EXCLUDED.cursor, updated_at = now()
        """,
        (tenant_id, source, cursor),
    )


def _upsert_utility_reading_from_bill(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    bill: UtilityBill,
) -> None:
    ua = conn.execute(
        """
        SELECT utility_account_id FROM core.utility_accounts
        WHERE tenant_id = %s AND customer_code = %s
        LIMIT 1
        """,
        (tenant_id, bill.customer_code),
    ).fetchone()
    if ua is None:
        return
    existing = conn.execute(
        """
        SELECT reading_id FROM core.utility_readings
        WHERE tenant_id = %s AND utility_account_id = %s AND billing_period = %s
        LIMIT 1
        """,
        (tenant_id, ua["utility_account_id"], bill.period),
    ).fetchone()
    if existing is not None:
        return

    lines = bill.readings.get("lines", []) if isinstance(bill.readings, dict) else []
    total_usage = bill.total_usage
    usage_unit = bill.usage_unit or ("m3" if bill.provider == "water" else "kWh")
    if total_usage is None and lines:
        from decimal import Decimal

        s = sum((Decimal(str(ln.get("usage", "0"))) for ln in lines if ln.get("usage") is not None), Decimal("0"))
        # For water, two lines (water + wastewater) both list same m3; take first line usage
        if bill.provider == "water" and lines[0].get("usage") is not None:
            total_usage = str(lines[0]["usage"])
        else:
            total_usage = str(s)
    total_usage = total_usage or "0"

    p_start = bill.period_start or date.fromisoformat(f"{bill.period}-01")
    p_end = bill.period_end or p_start
    subtotal = bill.subtotal_vnd if bill.subtotal_vnd is not None else bill.amount_vnd
    vat_total = bill.vat_total_vnd if bill.vat_total_vnd is not None else 0

    conn.execute(
        """
        INSERT INTO core.utility_readings (
            reading_id, utility_account_id, tenant_id, store_id, utility_type,
            billing_period, period_start, period_end, billing_days, due_date,
            statement_no, total_usage, usage_unit, subtotal_vnd, vat_total_vnd, total_vnd, lines
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 30, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            new_id("urd"),
            ua["utility_account_id"],
            tenant_id,
            bill.store_ref,
            bill.provider,
            bill.period,
            p_start,
            p_end,
            bill.due_date,
            bill.statement_no,
            total_usage,
            usage_unit,
            subtotal,
            vat_total,
            bill.amount_vnd,
            Jsonb(lines),
        ),
    )


def poll_sources_once(
    conn: psycopg.Connection,
    source_port: InvoiceSourcePort,
    *,
    clock: Clock | None = None,
) -> list[IngestResult]:
    """Poll sim-world inbox & bills for every tenant and ingest any new invoices."""
    clk = clock or SystemClock()
    results: list[IngestResult] = []
    tenants = conn.execute(
        "SELECT tenant_id, mailbox, wallet_id FROM core.tenants ORDER BY tenant_id"
    ).fetchall()

    for tenant in tenants:
        tid = tenant["tenant_id"]

        # 1. Poll inbox
        inbox_cursor = _get_cursor(conn, tid, "inbox")
        messages, next_inbox_cursor = source_port.list_inbox_messages(tenant["mailbox"], after=inbox_cursor)
        for msg in messages:
            for att in msg.attachments:
                try:
                    res = ingest_invoice(
                        conn,
                        IngestCommand(
                            tenant_id=tid,
                            raw_bytes=att.raw_bytes,
                            filename=att.filename,
                            content_type=att.content_type,
                            source="email",
                            message_text=msg.body_text,
                            external_message_id=msg.message_id,
                            from_address=msg.from_address,
                            subject=msg.subject,
                            received_at=msg.received_at,
                        ),
                        clock=clk,
                    )
                    results.append(res)
                except ProblemError:
                    # Unparseable attachment on inbox should not crash the poller loop
                    continue
        if next_inbox_cursor is not None:
            with conn.transaction():
                _set_cursor(conn, tid, "inbox", next_inbox_cursor)

        # 2. Poll utility bills
        bills_cursor = _get_cursor(conn, tid, "bills")
        bills, next_bills_cursor = source_port.list_bills(tenant["wallet_id"], after=bills_cursor)
        for bill in bills:
            with conn.transaction():
                _upsert_utility_reading_from_bill(conn, tenant_id=tid, bill=bill)
            xml_bytes = source_port.fetch_bill_document(bill.bill_id) if bill.xml_attachment_id else None
            if xml_bytes is None:
                continue
            try:
                res = ingest_invoice(
                    conn,
                    IngestCommand(
                        tenant_id=tid,
                        raw_bytes=xml_bytes,
                        filename=f"{bill.bill_id}.xml",
                        content_type="application/xml",
                        source="bill_pay",
                        invoice_type_hint="utility",
                        store_id_hint=bill.store_ref,
                        due_on_hint=bill.due_date,
                    ),
                    clock=clk,
                )
                results.append(res)
            except ProblemError:
                continue
        if next_bills_cursor is not None:
            with conn.transaction():
                _set_cursor(conn, tid, "bills", next_bills_cursor)

    return results

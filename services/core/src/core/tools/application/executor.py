"""Read-only tool executor for /internal/tools/{tool_id}:invoke with provenance and audit persistence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from core.merchant.application.serializers import (
    build_full_invoice,
    fmt_date,
    fmt_ts,
)
from core.shared.clock import Clock, SystemClock
from core.shared.errors import ProblemError
from core.shared.hashing import (
    hash_account_indicator,
    hash_phone_indicator,
    hash_tax_id_indicator,
)
from core.shared.ids import new_id
from core.tools.domain.calculations import (
    compute_price_check_item,
    compute_three_way_match,
    compute_utility_baseline,
    fmt_dec6,
)
from core.tools.domain.projections import (
    build_supervisor_invoice_summary,
    is_relevant_chat_thread,
    is_relevant_inbox_message,
)
from core.tools.domain.registry import V1_TOOL_SPECS
from core.tools.ports import GateClientPort, SimWorldToolPort, UpstreamToolError


@dataclass(frozen=True)
class ToolContext:
    tenant_id: str
    job_id: str
    attempt: int
    bot_id: str
    invoice_id: str | None
    store_ids: list[str] | None


def _get_invoice(conn: psycopg.Connection, tenant_id: str, invoice_id: str | None) -> dict[str, Any] | None:
    if not invoice_id:
        return None
    return conn.execute(
        "SELECT * FROM core.invoices WHERE tenant_id = %s AND invoice_id = %s",
        (tenant_id, invoice_id),
    ).fetchone()


def _get_tenant(conn: psycopg.Connection, tenant_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM core.tenants WHERE tenant_id = %s", (tenant_id,)
    ).fetchone()
    if row is None:
        raise ProblemError(404, "NOT_FOUND", "Tenant not found", f"Tenant {tenant_id} not found.")
    return row


def _collect_invoice_indicator_pairs(
    conn: psycopg.Connection, inv: dict[str, Any]
) -> list[tuple[str, str]]:
    """Collect (kind, sha256_value_hash) indicators for an invoice (I8: always 64-char sha256 hex, never raw)."""
    pairs: list[tuple[str, str]] = []
    tid = inv["tenant_id"]
    seller_tax = (inv.get("seller_tax_id") or "").strip()
    if seller_tax:
        pairs.append(("tax_id", hash_tax_id_indicator(seller_tax)))

    untrusted = inv.get("untrusted") or {}
    bank_accounts = list(untrusted.get("bank_accounts") or [])
    if not bank_accounts and untrusted.get("seller_bank_account"):
        bank_accounts = [untrusted["seller_bank_account"]]

    # Also check bank accounts from vendor registry to obtain bank_code when XML only has bank_name
    vendor_accounts = []
    if inv.get("vendor_id"):
        vendor_accounts = conn.execute(
            """
            SELECT bank_code, bank_name, account_number FROM core.vendor_accounts
            WHERE tenant_id = %s AND vendor_id = %s
            """,
            (tid, inv["vendor_id"]),
        ).fetchall()
        vrow = conn.execute(
            "SELECT phone_on_file FROM core.vendors WHERE tenant_id = %s AND vendor_id = %s",
            (tid, inv["vendor_id"]),
        ).fetchone()
        if vrow and vrow.get("phone_on_file"):
            pairs.append(("phone", hash_phone_indicator(vrow["phone_on_file"])))

    # Nit 2: derive bank_name -> bank_code mappings dynamically from seeded tenant vendor_accounts (no hard-coded demo banks)
    tenant_banks = conn.execute(
        """
        SELECT DISTINCT bank_code, bank_name
        FROM core.vendor_accounts
        WHERE tenant_id = %s AND bank_code IS NOT NULL
        """,
        (tid,),
    ).fetchall()
    bank_name_to_code: dict[str, str] = {}
    known_bank_codes: list[str] = []
    for tb in tenant_banks:
        bc = (tb.get("bank_code") or "").strip()
        bn = (tb.get("bank_name") or "").strip().lower()
        if bc:
            if bc not in known_bank_codes:
                known_bank_codes.append(bc)
            if bn:
                bank_name_to_code[bn] = bc

    for ba in bank_accounts:
        acc_num = (ba.get("number") or "").strip()
        if not acc_num:
            continue
        bname = (ba.get("bank_name") or "").strip().lower()
        code = bank_name_to_code.get(bname)
        if code:
            pairs.append(("account_hash", hash_account_indicator(code, acc_num)))
        else:
            for bc in known_bank_codes:
                pairs.append(("account_hash", hash_account_indicator(bc, acc_num)))
        # Also match raw account number hash in case indicator stored raw
        pairs.append(("account_hash", hash_account_indicator("", acc_num)))

    for va in vendor_accounts:
        if va.get("bank_code") and va.get("account_number"):
            pairs.append(("account_hash", hash_account_indicator(va["bank_code"], va["account_number"])))

    return list(dict.fromkeys(pairs))


def invoke_tool(
    conn: psycopg.Connection,
    *,
    tool_id: str,
    raw_input: dict[str, Any],
    ctx: ToolContext,
    sim_world: SimWorldToolPort,
    gate_client: GateClientPort,
    clock: Clock | None = None,
    lease_guard: Callable[[psycopg.Connection], None] | None = None,
    utility_outlier_ratio: Decimal = Decimal("1.5"),
) -> dict[str, Any]:
    """Validate input, execute read-only tool handler, record tool_calls row, and return ToolResult."""
    spec = V1_TOOL_SPECS.get(tool_id)
    if spec is None:
        raise ProblemError(404, "NOT_FOUND", "Unknown tool", f"Tool '{tool_id}' does not exist.")

    try:
        parsed_in = spec.input_model.model_validate(raw_input)
    except ValidationError as exc:
        raise ProblemError(
            status=400,
            code="VALIDATION_FAILED",
            title="Invalid tool input",
            detail=f"Input for tool '{tool_id}' failed schema validation.",
            errors=[
                {
                    "field": ".".join(str(p) for p in e.get("loc", [])) or "input",
                    "code": e.get("type", "invalid"),
                    "detail": e.get("msg", ""),
                }
                for e in exc.errors()
            ],
        ) from exc

    clk = clock or SystemClock()
    tool_call_id = new_id("tcl")
    provenance = spec.default_provenance
    error_obj: dict[str, Any] | None = None
    output_data: dict[str, Any] = {}

    try:
        output_data = _dispatch_tool(
            conn,
            tool_id=tool_id,
            inp=parsed_in.model_dump(mode="python", by_alias=True),
            ctx=ctx,
            sim_world=sim_world,
            gate_client=gate_client,
            clock=clk,
            utility_outlier_ratio=utility_outlier_ratio,
        )
    except UpstreamToolError as exc:
        # B1: preserve confirmed partial hits (e.g. SIMO listed=True before a later indicator errored)
        output_data = dict(exc.partial_output) if exc.partial_output else {}
        error_obj = {"code": exc.code, "detail": exc.detail}

    with conn.transaction():
        if lease_guard is not None:
            lease_guard(conn)
        conn.execute(
            """
            INSERT INTO core.tool_calls (
                tool_call_id, tenant_id, job_id, attempt, bot_id, tool_id,
                input, output, provenance, error, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tool_call_id,
                ctx.tenant_id,
                ctx.job_id,
                ctx.attempt,
                ctx.bot_id,
                tool_id,
                Jsonb(raw_input),
                Jsonb(output_data),
                provenance,
                Jsonb(error_obj) if error_obj is not None else None,
                clk.now(),
            ),
        )

    return {
        "data": output_data,
        "provenance": provenance,
        "evidence_ref": tool_call_id,
        "error": error_obj,
    }


def _dispatch_tool(
    conn: psycopg.Connection,
    *,
    tool_id: str,
    inp: dict[str, Any],
    ctx: ToolContext,
    sim_world: SimWorldToolPort,
    gate_client: GateClientPort,
    clock: Clock,
    utility_outlier_ratio: Decimal = Decimal("1.5"),
) -> dict[str, Any]:
    tid = ctx.tenant_id
    inv = _get_invoice(conn, tid, ctx.invoice_id)
    is_investigation = ctx.invoice_id is not None

    # ---- 1. invoices (I6: bind strictly to job invoice/vendor on investigations) ----
    if tool_id == "invoices":
        req_ids = inp.get("invoice_ids")
        if is_investigation:
            if inv is None:
                rows = []
            elif not inv.get("vendor_id"):
                # Vendor-less investigation: ONLY the job's own invoice is accessible!
                if req_ids and inv["invoice_id"] not in req_ids:
                    rows = []
                else:
                    rows = [inv]
            elif req_ids:
                rows = conn.execute(
                    """
                    SELECT * FROM core.invoices
                    WHERE tenant_id = %s AND invoice_id = ANY(%s) AND vendor_id = %s
                    """,
                    (tid, req_ids, inv["vendor_id"]),
                ).fetchall()
            else:
                rows = [inv]
        elif req_ids:
            clauses = ["tenant_id = %s", "invoice_id = ANY(%s)"]
            params: list[Any] = [tid, req_ids]
            if ctx.store_ids is not None:
                clauses.append("store_id = ANY(%s)")
                params.append(ctx.store_ids)
            rows = conn.execute(
                f"SELECT * FROM core.invoices WHERE {' AND '.join(clauses)}",
                params,
            ).fetchall()
        else:
            rows = []
        return {"invoices": [build_full_invoice(conn, r) for r in rows]}

    # ---- 2. vendor_contracts (I6: bind to job vendor during investigations) ----
    if tool_id == "vendor_contracts":
        if is_investigation:
            vid = inv["vendor_id"] if inv else None
            if inp.get("vendor_id") and inp["vendor_id"] != vid:
                return {"contracts": []}
        else:
            vid = inp.get("vendor_id")
        if not vid:
            return {"contracts": []}
        c_rows = conn.execute(
            """
            SELECT contract_id, vendor_id, valid_from, valid_to
            FROM core.vendor_contracts
            WHERE tenant_id = %s AND vendor_id = %s AND status = 'active'
            ORDER BY valid_from DESC
            """,
            (tid, vid),
        ).fetchall()
        contracts = []
        for c in c_rows:
            items = conn.execute(
                """
                SELECT item_id, sku, name, base_unit, pack_spec, pack_qty, unit_price, vat_rate
                FROM core.contract_items
                WHERE tenant_id = %s AND contract_id = %s
                ORDER BY item_id ASC
                """,
                (tid, c["contract_id"]),
            ).fetchall()
            contracts.append(
                {
                    "contract_id": c["contract_id"],
                    "vendor_id": c["vendor_id"],
                    "valid_from": fmt_date(c["valid_from"]),
                    "valid_to": fmt_date(c["valid_to"]),
                    "items": [dict(it) for it in items],
                }
            )
        return {"contracts": contracts}

    # ---- 3. price_check (I6: restrict contract lookup strictly to invoice vendor) ----
    if tool_id == "price_check":
        if inv is None:
            return {"items": []}
        vid = inv.get("vendor_id")
        if not vid:
            return {"items": []}
        results = []
        for m in inp["mappings"]:
            line = conn.execute(
                """
                SELECT line_id, name, unit, quantity, unit_price, amount_vnd
                FROM core.invoice_lines
                WHERE tenant_id = %s AND invoice_id = %s AND line_id = %s
                """,
                (tid, inv["invoice_id"], m["line_id"]),
            ).fetchone()
            if line is None:
                continue
            ci = conn.execute(
                """
                SELECT ci.item_id, ci.sku, ci.base_unit, ci.pack_qty, ci.unit_price
                FROM core.contract_items ci
                JOIN core.vendor_contracts vc
                  ON vc.tenant_id = ci.tenant_id AND vc.contract_id = ci.contract_id
                WHERE ci.tenant_id = %s AND vc.vendor_id = %s AND vc.status = 'active' AND ci.sku = %s
                LIMIT 1
                """,
                (tid, vid, m["sku"]),
            ).fetchone()
            if ci is None:
                continue
            line_name = line["name"]["text"] if isinstance(line["name"], dict) else str(line["name"])
            line_unit = (
                line["unit"]["text"]
                if isinstance(line["unit"], dict)
                else (str(line["unit"]) if line["unit"] else None)
            )
            results.append(
                compute_price_check_item(
                    line_id=line["line_id"],
                    sku=ci["sku"],
                    contract_item_id=ci["item_id"],
                    line_name=line_name,
                    line_unit=line_unit,
                    line_quantity=line["quantity"],
                    line_unit_price=line["unit_price"],
                    line_amount_vnd=line["amount_vnd"],
                    base_unit=ci["base_unit"],
                    pack_qty_contract_str=ci["pack_qty"],
                    unit_price_contract_str=ci["unit_price"],
                )
            )
        return {"items": results}

    # ---- 4. price_history ----
    if tool_id == "price_history":
        sku = inp["sku"]
        clauses = [
            "il.tenant_id = %s",
            "il.item_code->>'text' = %s",
            "i.issued_on IS NOT NULL",
            "il.quantity IS NOT NULL",
            "il.unit_price IS NOT NULL",
        ]
        params = [tid, sku]
        if is_investigation:
            if not inv or not inv.get("vendor_id"):
                return {"sku": sku, "points": []}
            clauses.append("i.vendor_id = %s")
            params.append(inv["vendor_id"])
        elif ctx.store_ids is not None:
            clauses.append("i.store_id = ANY(%s)")
            params.append(ctx.store_ids)
        rows = conn.execute(
            f"""
            SELECT i.invoice_id, i.issued_on, il.quantity, il.unit_price
            FROM core.invoice_lines il
            JOIN core.invoices i ON i.tenant_id = il.tenant_id AND i.invoice_id = il.invoice_id
            WHERE {' AND '.join(clauses)}
            ORDER BY i.issued_on DESC
            LIMIT 24
            """,
            params,
        ).fetchall()
        return {
            "sku": sku,
            "points": [
                {
                    "invoice_id": r["invoice_id"],
                    "issued_on": fmt_date(r["issued_on"]),
                    "quantity": r["quantity"],
                    "unit_price": r["unit_price"],
                }
                for r in rows
            ],
        }

    # ---- 5. purchase_orders (I6: bind strictly to job vendor during investigations) ----
    if tool_id == "purchase_orders":
        po_id = inp.get("purchase_order_id")
        if is_investigation:
            vid = inv["vendor_id"] if inv else None
            if not vid or (inp.get("vendor_id") and inp["vendor_id"] != vid):
                return {"purchase_orders": []}
            if po_id:
                rows = conn.execute(
                    """
                    SELECT * FROM core.purchase_orders
                    WHERE tenant_id = %s AND purchase_order_id = %s AND vendor_id = %s
                    """,
                    (tid, po_id, vid),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM core.purchase_orders
                    WHERE tenant_id = %s AND vendor_id = %s
                    ORDER BY created_at DESC LIMIT 20
                    """,
                    (tid, vid),
                ).fetchall()
        else:
            vid = inp.get("vendor_id")
            clauses = ["tenant_id = %s"]
            params = [tid]
            if ctx.store_ids is not None:
                clauses.append("store_id = ANY(%s)")
                params.append(ctx.store_ids)
            if po_id:
                clauses.append("purchase_order_id = %s")
                params.append(po_id)
                rows = conn.execute(
                    f"SELECT * FROM core.purchase_orders WHERE {' AND '.join(clauses)}",
                    params,
                ).fetchall()
            elif vid:
                clauses.append("vendor_id = %s")
                params.append(vid)
                rows = conn.execute(
                    f"SELECT * FROM core.purchase_orders WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT 20",
                    params,
                ).fetchall()
            else:
                rows = []
        return {
            "purchase_orders": [
                {
                    "purchase_order_id": r["purchase_order_id"],
                    "vendor_id": r["vendor_id"],
                    "store_id": r["store_id"],
                    "lines": list(r["lines"]),
                    "total_vnd": int(r["total_vnd"]),
                    "status": r["status"],
                    "created_by": r["created_by"],
                    "created_at": fmt_ts(r["created_at"]),
                }
                for r in rows
            ]
        }

    # ---- 6. goods_receipts (I6: bind strictly to job vendor during investigations) ----
    if tool_id == "goods_receipts":
        po_id = inp.get("purchase_order_id")
        if is_investigation:
            vid = inv["vendor_id"] if inv else None
            if not vid or (inp.get("vendor_id") and inp["vendor_id"] != vid):
                return {"goods_receipts": []}
            if po_id:
                rows = conn.execute(
                    """
                    SELECT g.* FROM core.goods_receipts g
                    JOIN core.purchase_orders p
                      ON p.tenant_id = g.tenant_id AND p.purchase_order_id = g.purchase_order_id
                    WHERE g.tenant_id = %s AND g.purchase_order_id = %s AND p.vendor_id = %s
                    ORDER BY g.confirmed_at DESC
                    """,
                    (tid, po_id, vid),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT g.* FROM core.goods_receipts g
                    JOIN core.purchase_orders p
                      ON p.tenant_id = g.tenant_id AND p.purchase_order_id = g.purchase_order_id
                    WHERE g.tenant_id = %s AND p.vendor_id = %s
                    ORDER BY g.confirmed_at DESC LIMIT 20
                    """,
                    (tid, vid),
                ).fetchall()
        else:
            vid = inp.get("vendor_id")
            clauses = ["g.tenant_id = %s"]
            params = [tid]
            if ctx.store_ids is not None:
                clauses.append("g.store_id = ANY(%s)")
                params.append(ctx.store_ids)
            if po_id:
                clauses.append("g.purchase_order_id = %s")
                params.append(po_id)
                rows = conn.execute(
                    f"SELECT g.* FROM core.goods_receipts g WHERE {' AND '.join(clauses)} ORDER BY g.confirmed_at DESC",
                    params,
                ).fetchall()
            elif vid:
                clauses.append("p.vendor_id = %s")
                params.append(vid)
                rows = conn.execute(
                    f"""
                    SELECT g.* FROM core.goods_receipts g
                    JOIN core.purchase_orders p
                      ON p.tenant_id = g.tenant_id AND p.purchase_order_id = g.purchase_order_id
                    WHERE {' AND '.join(clauses)}
                    ORDER BY g.confirmed_at DESC LIMIT 20
                    """,
                    params,
                ).fetchall()
            else:
                rows = []
        return {
            "goods_receipts": [
                {
                    "goods_receipt_id": r["goods_receipt_id"],
                    "purchase_order_id": r["purchase_order_id"],
                    "store_id": r["store_id"],
                    "lines": list(r["lines"]),
                    "confirmed_by": r["confirmed_by"],
                    "confirmed_at": fmt_ts(r["confirmed_at"]),
                }
                for r in rows
            ]
        }

    # ---- 7. payables_ledger (I6: bind to job vendor during investigations) ----
    if tool_id == "payables_ledger":
        if is_investigation:
            vid = inv["vendor_id"] if inv else None
            if not vid or (inp.get("vendor_id") and inp["vendor_id"] != vid):
                return {"entries": []}
        else:
            vid = inp.get("vendor_id")
        if not vid:
            return {"entries": []}
        p_rows = conn.execute(
            """
            SELECT invoice_id, vendor_id, symbol, number, issued_on, due_on, amount_vnd, status, paid_at
            FROM core.payables
            WHERE tenant_id = %s AND vendor_id = %s
            ORDER BY issued_on DESC NULLS LAST LIMIT 50
            """,
            (tid, vid),
        ).fetchall()
        i_rows = conn.execute(
            """
            SELECT invoice_id, vendor_id, symbol, number, issued_on, due_on,
                   COALESCE(total_vnd, 0) AS amount_vnd, status, NULL::timestamptz AS paid_at
            FROM core.invoices
            WHERE tenant_id = %s AND vendor_id = %s
            ORDER BY issued_on DESC NULLS LAST LIMIT 50
            """,
            (tid, vid),
        ).fetchall()
        seen: set[str] = set()
        entries = []
        for r in [*p_rows, *i_rows]:
            if r["invoice_id"] in seen:
                continue
            seen.add(r["invoice_id"])
            entries.append(
                {
                    "invoice_id": r["invoice_id"],
                    "vendor_id": r["vendor_id"],
                    "symbol": r["symbol"],
                    "number": r["number"],
                    "issued_on": fmt_date(r["issued_on"]),
                    "due_on": fmt_date(r["due_on"]),
                    "amount_vnd": int(r["amount_vnd"]),
                    "status": r["status"],
                    "paid_at": fmt_ts(r["paid_at"]),
                }
            )
        return {"entries": entries}

    # ---- 8. three_way_match ----
    if tool_id == "three_way_match":
        if inv is None:
            return compute_three_way_match(invoice_lines=[], purchase_order=None, goods_receipts=[])
        inv_lines = conn.execute(
            """
            SELECT line_id, kind, item_code, quantity
            FROM core.invoice_lines
            WHERE tenant_id = %s AND invoice_id = %s
            ORDER BY position ASC
            """,
            (tid, inv["invoice_id"]),
        ).fetchall()
        po = None
        if inv.get("purchase_order_id"):
            po = conn.execute(
                "SELECT * FROM core.purchase_orders WHERE tenant_id = %s AND purchase_order_id = %s",
                (tid, inv["purchase_order_id"]),
            ).fetchone()
        if po is None and inv.get("vendor_id"):
            # Match latest PO for this vendor (preferring matching SKU or store)
            candidate_pos = conn.execute(
                """
                SELECT * FROM core.purchase_orders
                WHERE tenant_id = %s AND vendor_id = %s AND status != 'cancelled'
                ORDER BY created_at DESC LIMIT 10
                """,
                (tid, inv["vendor_id"]),
            ).fetchall()
            inv_skus = {
                (ln["item_code"] or {}).get("text")
                for ln in inv_lines
                if isinstance(ln.get("item_code"), dict) and (ln["item_code"] or {}).get("text")
            }
            for cand in candidate_pos:
                po_skus = {pl.get("sku") for pl in (cand["lines"] or [])}
                if inv_skus and (inv_skus & po_skus):
                    po = cand
                    break
            if po is None and candidate_pos:
                po = candidate_pos[0]

        grns = []
        if po is not None:
            grns = conn.execute(
                """
                SELECT * FROM core.goods_receipts
                WHERE tenant_id = %s AND purchase_order_id = %s
                ORDER BY confirmed_at ASC
                """,
                (tid, po["purchase_order_id"]),
            ).fetchall()
        return compute_three_way_match(invoice_lines=inv_lines, purchase_order=po, goods_receipts=grns)

    # ---- 9. inbox (sim-world, untrusted; I6: filter to relevant correspondence) ----
    if tool_id == "inbox":
        tenant = _get_tenant(conn, tid)
        vendor_email: str | None = None
        vendor_name: str | None = None
        linked_ext_ids: set[str] = set()
        if inv is not None:
            if inv.get("vendor_id"):
                v = conn.execute(
                    "SELECT email, name FROM core.vendors WHERE tenant_id = %s AND vendor_id = %s",
                    (tid, inv["vendor_id"]),
                ).fetchone()
                if v:
                    vendor_email = v.get("email")
                    vendor_name = v.get("name")
            im_rows = conn.execute(
                "SELECT external_message_id FROM core.invoice_messages WHERE tenant_id = %s AND invoice_id = %s AND external_message_id IS NOT NULL",
                (tid, inv["invoice_id"]),
            ).fetchall()
            linked_ext_ids = {str(r["external_message_id"]) for r in im_rows}

        msgs = sim_world.get_inbox_messages(
            mailbox=tenant["mailbox"],
            from_address=None,  # include lookalike BEC emails matching vendor/invoice!
            since=fmt_ts(inp.get("since")),
        )
        if inv is not None:
            msgs = [
                m
                for m in msgs
                if is_relevant_inbox_message(
                    m,
                    linked_external_ids=linked_ext_ids,
                    vendor_email=vendor_email,
                    vendor_name=vendor_name,
                    invoice_symbol=inv.get("symbol"),
                    invoice_number=inv.get("number"),
                    invoice_number_norm=inv.get("number_norm"),
                    seller_tax_id=inv.get("seller_tax_id"),
                )
            ]
        return {
            "messages": [
                {
                    "message_id": m["message_id"],
                    "from_address": m["from"],
                    "received_at": m["received_at"],
                    "subject": {
                        "text": m["subject"],
                        "provenance": "untrusted",
                        "source": "email_body",
                    },
                    "body": {
                        "text": m["body_text"],
                        "provenance": "untrusted",
                        "source": "email_body",
                    },
                }
                for m in msgs
            ]
        }

    # ---- 10. chat_messages (sim-world, untrusted; I6: filter to relevant counterparty/invoice threads) ----
    if tool_id == "chat_messages":
        vendor_phone: str | None = None
        vendor_name_c: str | None = None
        if inv is not None and inv.get("vendor_id"):
            v = conn.execute(
                "SELECT phone_on_file, name FROM core.vendors WHERE tenant_id = %s AND vendor_id = %s",
                (tid, inv["vendor_id"]),
            ).fetchone()
            if v:
                vendor_phone = v.get("phone_on_file")
                vendor_name_c = v.get("name")

        threads = sim_world.get_chat_threads(tenant_ref=tid)
        since_str = fmt_ts(inp.get("since"))
        out_threads = []
        for thr in threads:
            msgs = sim_world.get_chat_messages(thread_id=thr["thread_id"], since=since_str)
            if inv is not None and not is_relevant_chat_thread(
                thr,
                msgs,
                vendor_phone=vendor_phone,
                vendor_name=vendor_name_c,
                invoice_symbol=inv.get("symbol"),
                invoice_number=inv.get("number"),
                invoice_number_norm=inv.get("number_norm"),
                seller_tax_id=inv.get("seller_tax_id"),
            ):
                continue
            out_threads.append(
                {
                    "thread_id": thr["thread_id"],
                    "counterparty_phone": thr["counterparty_phone"],
                    "counterparty_name": {
                        "text": thr["counterparty_name"],
                        "provenance": "untrusted",
                        "source": "chat_message",
                    },
                    "messages": [
                        {
                            "message_id": m["message_id"],
                            "sender": m["from"],
                            "sent_at": m["sent_at"],
                            "text": {
                                "text": m["text"],
                                "provenance": "untrusted",
                                "source": "chat_message",
                            },
                        }
                        for m in msgs
                    ],
                }
            )
        return {"threads": out_threads}

    # ---- 11. vendor_registry ----
    if tool_id == "vendor_registry":
        vrow = None
        if inv and inv.get("vendor_id"):
            vrow = conn.execute(
                "SELECT * FROM core.vendors WHERE tenant_id = %s AND vendor_id = %s",
                (tid, inv["vendor_id"]),
            ).fetchone()
        elif inv and inv.get("seller_tax_id"):
            vrow = conn.execute(
                "SELECT * FROM core.vendors WHERE tenant_id = %s AND tax_id = %s",
                (tid, inv["seller_tax_id"]),
            ).fetchone()
        if vrow is None:
            return {"vendor": None, "accounts": [], "approved_verifications": []}

        accs = conn.execute(
            """
            SELECT vendor_account_id, vendor_id, kind, bank_code, bank_name,
                   account_number_masked, merchant_id, account_name, status, verified_at
            FROM core.vendor_accounts
            WHERE tenant_id = %s AND vendor_id = %s
            ORDER BY (status = 'verified') DESC, vendor_account_id ASC
            """,
            (tid, vrow["vendor_id"]),
        ).fetchall()
        verifs = conn.execute(
            """
            SELECT verification_id, vendor_account_id, target_status, decided_at
            FROM core.vendor_verifications
            WHERE tenant_id = %s AND vendor_id = %s AND status = 'approved'
              AND vendor_account_id IS NOT NULL AND decided_at IS NOT NULL
            ORDER BY decided_at DESC
            """,
            (tid, vrow["vendor_id"]),
        ).fetchall()
        return {
            "vendor": {
                "vendor_id": vrow["vendor_id"],
                "name": vrow["name"],
                "tax_id": vrow["tax_id"],
                "phone_on_file_masked": vrow["phone_on_file_masked"],
                "status": vrow["status"],
                "created_at": fmt_ts(vrow["created_at"]),
            },
            "accounts": [
                {
                    "vendor_account_id": a["vendor_account_id"],
                    "vendor_id": a["vendor_id"],
                    "kind": a["kind"],
                    "bank_code": a["bank_code"],
                    "bank_name": a["bank_name"],
                    "account_number_masked": a["account_number_masked"],
                    "merchant_id": a["merchant_id"],
                    "account_name": a["account_name"],
                    "status": a["status"],
                    "verified_at": fmt_ts(a["verified_at"]),
                }
                for a in accs
            ],
            "approved_verifications": [
                {
                    "verification_id": vf["verification_id"],
                    "vendor_account_id": vf["vendor_account_id"],
                    "target_status": vf["target_status"],
                    "decided_at": fmt_ts(vf["decided_at"]),
                }
                for vf in verifs
            ],
        }

    # ---- 12. cross_alerts ----
    if tool_id == "cross_alerts":
        if inv is None:
            return {"matched": False, "hits": []}
        pairs = _collect_invoice_indicator_pairs(conn, inv)
        if not pairs:
            return {"matched": False, "hits": []}
        hits: list[dict[str, Any]] = []
        seen_cxa: set[str] = set()
        for kind, val_hash in pairs:
            rows = conn.execute(
                """
                SELECT ca.cross_alert_id,
                       COALESCE(ca.indicator_kind, i.kind) AS indicator_kind,
                       ca.reason_codes,
                       ca.published_at
                FROM risk.cross_alerts ca
                LEFT JOIN risk.indicators i ON i.indicator_id = ANY(ca.indicator_ids)
                WHERE ca.status = 'published'
                  AND (
                    (ca.indicator_kind = %s AND ca.value_hash = %s)
                    OR (i.kind = %s AND i.value_hash = %s)
                  )
                """,
                (kind, val_hash, kind, val_hash),
            ).fetchall()
            for r in rows:
                if r["cross_alert_id"] in seen_cxa:
                    continue
                seen_cxa.add(r["cross_alert_id"])
                hits.append(
                    {
                        "cross_alert_id": r["cross_alert_id"],
                        "indicator_kind": r["indicator_kind"],
                        "reason_codes": list(r["reason_codes"]),
                        "published_at": fmt_ts(r["published_at"]),
                    }
                )
        return {"matched": len(hits) > 0, "hits": hits}

    # ---- 13. official_fraud_list (sim-world SIMO) ----
    if tool_id == "official_fraud_list":
        if inv is None:
            return {"listed": False, "matches": []}
        pairs = _collect_invoice_indicator_pairs(conn, inv)
        matches = []
        listed_any = False
        first_err: UpstreamToolError | None = None
        for kind, val_hash in pairs:
            if kind not in {"account_hash", "phone", "tax_id"}:
                continue
            # SIMO expects 64-char sha256 hex
            if len(val_hash) != 64:
                continue
            try:
                res = sim_world.check_simo_indicator(kind=kind, value_hash=val_hash)
            except UpstreamToolError as exc:
                if first_err is None:
                    first_err = exc
                continue
            if res.get("listed"):
                listed_any = True
                matches.append(
                    {
                        "kind": kind,
                        "listed": True,
                        "list_ref": res.get("list_ref"),
                    }
                )
        result = {"listed": listed_any, "matches": matches}
        if first_err is not None:
            # B1: keep confirmed positive hits alongside the error so red floor is never lost
            raise UpstreamToolError(first_err.code, first_err.detail, partial_output=result)
        return result

    # ---- 14. einvoice_portal (sim-world) ----
    if tool_id == "einvoice_portal":
        if inv is None:
            return {
                "found": False,
                "invoice_status_code": None,
                "invoice_status_label": None,
                "processing_status_code": None,
                "processing_status_label": None,
                "illegal_flag": None,
                "tax_authority_code": None,
                "total_vnd": None,
                "related_invoice": None,
            }
        return sim_world.lookup_einvoice_portal(
            seller_tax_id=inv["seller_tax_id"],
            symbol=inv["symbol"],
            number=inv["number"],
        )

    # ---- 15. tax_id_lookup (sim-world; B1/N4: bind to invoice seller_tax_id, strict upstream validation) ----
    if tool_id == "tax_id_lookup":
        if is_investigation:
            target_tax_id = (inv.get("seller_tax_id") or "").strip() if inv else ""
            if not target_tax_id:
                raise UpstreamToolError("NOT_FOUND", "Bound invoice has no seller_tax_id.")
        else:
            target_tax_id = str(inp["tax_id"]).strip()
        res = sim_world.lookup_taxpayer(tax_id=target_tax_id)
        if res is None:
            raise UpstreamToolError("NOT_FOUND", f"Taxpayer {target_tax_id} not found.")
        if not isinstance(res, dict):
            raise UpstreamToolError("UPSTREAM_UNAVAILABLE", f"Malformed taxpayer response for {target_tax_id}.")
        resp_tax_id = res.get("tax_id")
        if not isinstance(resp_tax_id, str) or resp_tax_id.strip() != target_tax_id:
            raise UpstreamToolError(
                "UPSTREAM_UNAVAILABLE",
                f"Taxpayer response tax_id {resp_tax_id!r} does not match requested {target_tax_id!r}.",
            )
        status_code = res.get("status_code")
        valid_tax_statuses = {"00", "01", "02", "03", "04", "05", "06", "07", "09", "10"}
        if not isinstance(status_code, str) or status_code not in valid_tax_statuses:
            raise UpstreamToolError(
                "UPSTREAM_UNAVAILABLE",
                f"Malformed taxpayer status_code {status_code!r} for {target_tax_id}.",
            )
        return res

    # ---- 16. tax_risk_list (sim-world; B1/N4: bind to invoice seller_tax_id, strict boolean `listed`) ----
    if tool_id == "tax_risk_list":
        if is_investigation:
            target_tax_id = (inv.get("seller_tax_id") or "").strip() if inv else ""
            if not target_tax_id:
                raise UpstreamToolError("NOT_FOUND", "Bound invoice has no seller_tax_id.")
        else:
            target_tax_id = str(inp["tax_id"]).strip()
        res = sim_world.lookup_tax_risk_list(tax_id=target_tax_id)
        if not isinstance(res, dict):
            raise UpstreamToolError("UPSTREAM_UNAVAILABLE", f"Malformed tax_risk_list response for {target_tax_id}.")
        if "listed" not in res or not isinstance(res["listed"], bool):
            raise UpstreamToolError(
                "UPSTREAM_UNAVAILABLE",
                f"Malformed tax_risk_list response for {target_tax_id}: missing boolean 'listed'.",
            )
        if "tax_id" in res and res["tax_id"] is not None:
            if not isinstance(res["tax_id"], str) or res["tax_id"].strip() != target_tax_id:
                raise UpstreamToolError(
                    "UPSTREAM_UNAVAILABLE",
                    f"tax_risk_list response tax_id {res['tax_id']!r} does not match requested {target_tax_id!r}.",
                )
            out_tax_id = res["tax_id"].strip()
        else:
            out_tax_id = target_tax_id
        return {
            "tax_id": out_tax_id,
            "listed": res["listed"],
            "list_name": res.get("list_name"),
            "listed_on": res.get("listed_on"),
        }

    # ---- 17. utility_bills (B1/I6: bind strictly to invoice store on investigations, store_ids on Q&A) ----
    if tool_id == "utility_bills":
        if is_investigation:
            store_id = inv["store_id"] if inv else None
        else:
            store_id = inp.get("store_id")
            if ctx.store_ids is not None and store_id and store_id not in ctx.store_ids:
                return {"readings": []}
        months = int(inp.get("months", 12))
        if store_id:
            rows = conn.execute(
                """
                SELECT reading_id, store_id, utility_type, billing_period, period_start, period_end,
                       total_usage, usage_unit, total_vnd
                FROM core.utility_readings
                WHERE tenant_id = %s AND store_id = %s
                ORDER BY billing_period DESC
                LIMIT %s
                """,
                (tid, store_id, months * 2),
            ).fetchall()
        elif is_investigation:
            rows = []
        elif ctx.store_ids is not None:
            rows = conn.execute(
                """
                SELECT reading_id, store_id, utility_type, billing_period, period_start, period_end,
                       total_usage, usage_unit, total_vnd
                FROM core.utility_readings
                WHERE tenant_id = %s AND store_id = ANY(%s)
                ORDER BY billing_period DESC
                LIMIT %s
                """,
                (tid, ctx.store_ids, months * 2),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT reading_id, store_id, utility_type, billing_period, period_start, period_end,
                       total_usage, usage_unit, total_vnd
                FROM core.utility_readings
                WHERE tenant_id = %s
                ORDER BY billing_period DESC
                LIMIT %s
                """,
                (tid, months * 2),
            ).fetchall()
        return {
            "readings": [
                {
                    "reading_id": r["reading_id"],
                    "store_id": r["store_id"],
                    "utility_type": r["utility_type"],
                    "billing_period": r["billing_period"],
                    "period_start": fmt_date(r["period_start"]),
                    "period_end": fmt_date(r["period_end"]),
                    "total_usage": r["total_usage"],
                    "usage_unit": r["usage_unit"],
                    "total_vnd": int(r["total_vnd"]),
                }
                for r in rows
            ]
        }

    # ---- 18. utility_baseline (B1/I6: bind strictly to invoice store on investigations) ----
    if tool_id == "utility_baseline":
        if is_investigation:
            store_id = inv["store_id"] if inv else None
        else:
            store_id = inp.get("store_id")
            if ctx.store_ids is not None and store_id and store_id not in ctx.store_ids:
                store_id = None
        months = int(inp.get("months", 12))
        util_type: str | None = None
        if inv and inv.get("vendor_id"):
            ua = conn.execute(
                """
                SELECT utility_type FROM core.utility_accounts
                WHERE tenant_id = %s AND vendor_id = %s
                LIMIT 1
                """,
                (tid, inv["vendor_id"]),
            ).fetchone()
            if ua:
                util_type = ua["utility_type"]
        if util_type is None and inv:
            seller_lower = ((inv.get("untrusted") or {}).get("seller_name") or {}).get("text", "").lower()
            if "nước" in seller_lower:
                util_type = "water"
            elif "điện" in seller_lower:
                util_type = "electricity"

        # Current usage from invoice lines (first goods_service line)
        cur_usage: str | None = None
        cur_amount: int | None = inv["total_vnd"] if inv else None
        if inv:
            ln = conn.execute(
                """
                SELECT quantity FROM core.invoice_lines
                WHERE tenant_id = %s AND invoice_id = %s AND quantity IS NOT NULL
                ORDER BY position ASC LIMIT 1
                """,
                (tid, inv["invoice_id"]),
            ).fetchone()
            if ln:
                cur_usage = ln["quantity"]

        if store_id and util_type:
            hist = conn.execute(
                """
                SELECT reading_id, total_usage, total_vnd, billing_period
                FROM core.utility_readings
                WHERE tenant_id = %s AND store_id = %s AND utility_type = %s
                ORDER BY billing_period DESC
                LIMIT %s
                """,
                (tid, store_id, util_type, months),
            ).fetchall()
        elif store_id:
            hist = conn.execute(
                """
                SELECT reading_id, total_usage, total_vnd, billing_period
                FROM core.utility_readings
                WHERE tenant_id = %s AND store_id = %s
                ORDER BY billing_period DESC
                LIMIT %s
                """,
                (tid, store_id, months),
            ).fetchall()
        else:
            hist = []

        return compute_utility_baseline(
            store_id=store_id,
            utility_type=util_type,
            months=months,
            historical_readings=hist,
            current_usage_str=cur_usage,
            current_amount_vnd=cur_amount,
        )

    # ---- 19. momo_revenue (sim-world) ----
    if tool_id == "momo_revenue":
        tenant = _get_tenant(conn, tid)
        rev = sim_world.get_momo_revenue(
            wallet_id=tenant["wallet_id"],
            store_ref=inp["store_id"],
            month=inp["month"],
        )
        return {
            "store_id": inp["store_id"],
            "month": inp["month"],
            "revenue_vnd": int(rev["revenue_vnd"]),
            "transaction_count": int(rev["transaction_count"]),
        }

    # ---- 20. account_balance (sim-world) ----
    if tool_id == "account_balance":
        tenant = _get_tenant(conn, tid)
        return sim_world.get_wallet_balance(wallet_id=tenant["wallet_id"])

    # ---- 21. spending_limits (DB + Gate port) ----
    if tool_id == "spending_limits":
        m_row = conn.execute(
            """
            SELECT * FROM core.mandates
            WHERE tenant_id = %s
            ORDER BY version DESC LIMIT 1
            """,
            (tid,),
        ).fetchone()
        pol = conn.execute(
            """
            SELECT value, updated_at FROM control.policies
            WHERE kind = 'platform_limits' AND status = 'active'
            LIMIT 1
            """
        ).fetchone()
        # Nit 2: missing platform_limits policy fails closed (0 ceilings, not eligible for auto-pay)
        pl_payload = (
            dict(pol["value"])
            if pol
            else {"auto_pay_per_invoice_vnd": 0, "auto_pay_per_day_vnd": 0}
        )
        pl_payload.setdefault("updated_at", fmt_ts(pol["updated_at"]) if pol else fmt_ts(clock.now()))

        today_str = clock.today().isoformat()
        budget = gate_client.get_daily_budget(tenant_id=tid, date_str=today_str)
        mandate_out = None
        if m_row:
            mandate_out = {
                "mandate_id": m_row["mandate_id"],
                "version": m_row["version"],
                "mode": m_row["mode"],
                "limits": m_row["limits"],
                "auto_pay_vendor_ids": list(m_row["auto_pay_vendor_ids"]),
                "channel_rules": list(m_row["channel_rules"]),
                "bulk_approvable": list(m_row["bulk_approvable"]),
                "auto_pay_window": m_row["auto_pay_window"],
                "signed": m_row["signed"],
                "created_at": fmt_ts(m_row["created_at"]),
            }
        return {
            "mandate": mandate_out,
            "platform_limits": pl_payload,
            "daily_budget": budget,
        }

    # ---- 22. payment_policy_preview (Gate port) ----
    if tool_id == "payment_policy_preview":
        if inv is None:
            raise UpstreamToolError("NOT_FOUND", "No invoice bound to this job.")
        ev = gate_client.evaluate_invoice(invoice_id=inv["invoice_id"], tenant_id=tid)
        return ev.to_dict()

    # ---- 23-30. Trusted stats / search tools (for supervisor & Q&A) ----
    if tool_id == "invoice_search":
        clauses = ["i.tenant_id = %s"]
        params: list[Any] = [tid]
        if ctx.store_ids is not None:
            clauses.append("i.store_id = ANY(%s)")
            params.append(ctx.store_ids)
        if inp.get("status"):
            clauses.append("i.status = %s")
            params.append(inp["status"])
        if inp.get("severity"):
            clauses.append("i.severity = %s")
            params.append(inp["severity"])
        if inp.get("vendor_id"):
            clauses.append("i.vendor_id = %s")
            params.append(inp["vendor_id"])
        if inp.get("store_id"):
            clauses.append("i.store_id = %s")
            params.append(inp["store_id"])
        if inp.get("reason_code"):
            clauses.append("%s = ANY(i.reason_codes)")
            params.append(inp["reason_code"])
        if inp.get("issued_from"):
            clauses.append("i.issued_on >= %s")
            params.append(inp["issued_from"])
        if inp.get("issued_to"):
            clauses.append("i.issued_on <= %s")
            params.append(inp["issued_to"])
        limit = int(inp.get("limit", 20))
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT i.*, v.name AS vendor_name_reg
            FROM core.invoices i
            LEFT JOIN core.vendors v ON v.tenant_id = i.tenant_id AND v.vendor_id = i.vendor_id
            WHERE {' AND '.join(clauses)}
            ORDER BY i.updated_at DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
        # B4: supervisor-safe projection (drops unformatted XML seller_tax_id/symbol/number)
        return {
            "items": [
                build_supervisor_invoice_summary(
                    r,
                    vendor_name=r.get("vendor_name_reg"),
                    fmt_date_fn=fmt_date,
                    fmt_ts_fn=fmt_ts,
                )
                for r in rows
            ]
        }

    if tool_id == "invoice_explain":
        target = _get_invoice(conn, tid, inp["invoice_id"])
        if target is None or (ctx.store_ids is not None and target.get("store_id") not in ctx.store_ids):
            raise UpstreamToolError("NOT_FOUND", "Invoice not found.")
        vname = None
        if target.get("vendor_id"):
            v = conn.execute(
                "SELECT name FROM core.vendors WHERE tenant_id = %s AND vendor_id = %s",
                (tid, target["vendor_id"]),
            ).fetchone()
            vname = v["name"] if v else None
        latest_job = conn.execute(
            """
            SELECT job_id, attempt FROM core.jobs
            WHERE tenant_id = %s AND invoice_id = %s AND status = 'completed'
            ORDER BY completed_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            (tid, target["invoice_id"]),
        ).fetchone()
        if latest_job is not None:
            # I5: derive current findings from the completed attempt only
            f_rows = conn.execute(
                """
                SELECT finding_id, bot_id, severity, reason_codes, evidence
                FROM core.findings
                WHERE tenant_id = %s AND invoice_id = %s
                  AND superseded = FALSE
                  AND (
                    (job_id = %s AND attempt = %s)
                    OR bot_id = 'ingest'
                    OR (job_id IS NULL AND bot_id = 'system')
                  )
                ORDER BY created_at ASC
                """,
                (tid, target["invoice_id"], latest_job["job_id"], int(latest_job["attempt"])),
            ).fetchall()
        else:
            f_rows = conn.execute(
                """
                SELECT finding_id, bot_id, severity, reason_codes, evidence
                FROM core.findings
                WHERE tenant_id = %s AND invoice_id = %s
                  AND superseded = FALSE
                  AND (bot_id = 'ingest' OR (job_id IS NULL AND bot_id = 'system'))
                ORDER BY created_at ASC
                """,
                (tid, target["invoice_id"]),
            ).fetchall()
        return {
            "invoice": build_supervisor_invoice_summary(
                target,
                vendor_name=vname,
                fmt_date_fn=fmt_date,
                fmt_ts_fn=fmt_ts,
            ),
            "findings": [
                {
                    "finding_id": f["finding_id"],
                    "bot_id": f["bot_id"],
                    "severity": f["severity"],
                    "reason_codes": list(f["reason_codes"]),
                    "evidence": list(f["evidence"]),
                }
                for f in f_rows
            ],
        }

    if tool_id == "queue_status":
        clauses = ["tenant_id = %s"]
        params = [tid]
        if ctx.store_ids is not None:
            clauses.append("store_id = ANY(%s)")
            params.append(ctx.store_ids)
        rows = conn.execute(
            f"""
            SELECT status, COUNT(*) AS cnt, COALESCE(SUM(total_vnd), 0) AS total, MIN(due_on) AS min_due
            FROM core.invoices
            WHERE {' AND '.join(clauses)}
            GROUP BY status
            """,
            params,
        ).fetchall()
        counts = {r["status"]: int(r["cnt"]) for r in rows}
        pending_total = sum(
            int(r["total"]) for r in rows if r["status"] in {"pending_approval", "blocked"}
        )
        due_dates = [r["min_due"] for r in rows if r["status"] in {"pending_approval", "blocked"} and r["min_due"]]
        return {
            "counts_by_status": counts,
            "pending_approval_total_vnd": pending_total,
            "nearest_due_on": fmt_date(min(due_dates)) if due_dates else None,
        }

    if tool_id == "spending_summary":
        group_by = inp["group_by"]
        clauses = ["i.tenant_id = %s", "i.issued_on >= %s", "i.issued_on <= %s"]
        params = [tid, inp["from"], inp["to"]]
        if ctx.store_ids is not None:
            clauses.append("i.store_id = ANY(%s)")
            params.append(ctx.store_ids)
        if inp.get("store_id"):
            clauses.append("i.store_id = %s")
            params.append(inp["store_id"])
        rows = conn.execute(
            f"""
            SELECT i.vendor_id, v.name AS vendor_name, i.store_id, s.name AS store_name,
                   i.invoice_type, to_char(i.issued_on, 'YYYY-MM') AS month, COALESCE(i.total_vnd, 0) AS total_vnd
            FROM core.invoices i
            LEFT JOIN core.vendors v ON v.tenant_id = i.tenant_id AND v.vendor_id = i.vendor_id
            LEFT JOIN core.stores s ON s.tenant_id = i.tenant_id AND s.store_id = i.store_id
            WHERE {' AND '.join(clauses)}
            """,
            params,
        ).fetchall()
        buckets: dict[str, dict[str, Any]] = {}
        for r in rows:
            if group_by == "vendor":
                k = r["vendor_id"] or "unknown"
                lbl = r["vendor_name"] or "Chưa đăng ký"
            elif group_by == "store":
                k = r["store_id"] or "unknown"
                lbl = r["store_name"] or "Chưa gắn quán"
            elif group_by == "invoice_type":
                k = r["invoice_type"]
                lbl = r["invoice_type"]
            else:
                k = r["month"] or "unknown"
                lbl = k
            b = buckets.setdefault(k, {"key": k, "label": lbl, "invoice_count": 0, "total_vnd": 0})
            b["invoice_count"] += 1
            b["total_vnd"] += int(r["total_vnd"])
        groups = list(buckets.values())
        return {
            "from": fmt_date(inp["from"]),
            "to": fmt_date(inp["to"]),
            "group_by": group_by,
            "total_vnd": sum(g["total_vnd"] for g in groups),
            "invoice_count": sum(g["invoice_count"] for g in groups),
            "groups": groups,
        }

    if tool_id == "vendor_stats":
        vid = inp["vendor_id"]
        months = int(inp.get("months", 6))
        v = conn.execute(
            "SELECT name FROM core.vendors WHERE tenant_id = %s AND vendor_id = %s",
            (tid, vid),
        ).fetchone()
        if v is None:
            raise UpstreamToolError("NOT_FOUND", f"Vendor {vid} not found.")
        clauses = ["tenant_id = %s", "vendor_id = %s"]
        params = [tid, vid]
        # I6: enforce store_ids scope and months window
        if ctx.store_ids is not None:
            clauses.append("store_id = ANY(%s)")
            params.append(ctx.store_ids)
        cutoff = clock.today() - timedelta(days=months * 31)
        clauses.append("(issued_on IS NULL OR issued_on >= %s)")
        params.append(cutoff)
        rows = conn.execute(
            f"""
            SELECT total_vnd, severity, reason_codes FROM core.invoices
            WHERE {' AND '.join(clauses)}
            """,
            params,
        ).fetchall()
        return {
            "vendor_id": vid,
            "vendor_name": v["name"],
            "months": months,
            "invoice_count": len(rows),
            "total_vnd": sum(int(r["total_vnd"] or 0) for r in rows),
            "above_contract_count": sum(
                1 for r in rows if "PRICE_ABOVE_CONTRACT" in (r["reason_codes"] or [])
            ),
            "yellow_count": sum(1 for r in rows if r["severity"] == "yellow"),
            "red_count": sum(1 for r in rows if r["severity"] == "red"),
        }

    if tool_id == "price_trend":
        sku = inp["sku"]
        ci = conn.execute(
            """
            SELECT ci.unit_price FROM core.contract_items ci
            JOIN core.vendor_contracts vc
              ON vc.tenant_id = ci.tenant_id AND vc.contract_id = ci.contract_id
            WHERE ci.tenant_id = %s AND vc.status = 'active' AND ci.sku = %s
            LIMIT 1
            """,
            (tid, sku),
        ).fetchone()
        return {
            "sku": sku,
            "contract_unit_price": ci["unit_price"] if ci else None,
            "points": [],
        }

    if tool_id == "utility_summary":
        months = int(inp.get("months", 12))
        clauses = ["u.tenant_id = %s"]
        params = [tid]
        if ctx.store_ids is not None:
            clauses.append("u.store_id = ANY(%s)")
            params.append(ctx.store_ids)
        if inp.get("store_id"):
            clauses.append("u.store_id = %s")
            params.append(inp["store_id"])
        rows = conn.execute(
            f"""
            SELECT u.store_id, s.name AS store_name, u.utility_type, u.total_vnd, u.billing_period
            FROM core.utility_readings u
            JOIN core.stores s ON s.tenant_id = u.tenant_id AND s.store_id = u.store_id
            WHERE {' AND '.join(clauses)}
            ORDER BY u.billing_period DESC
            """,
            params,
        ).fetchall()
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in rows:
            grouped.setdefault((r["store_id"], r["utility_type"]), []).append(r)
        stores_out = []
        for (sid, utype), items in grouped.items():
            recent = items[:months]
            vals = sorted(int(x["total_vnd"]) for x in recent)
            med = vals[len(vals) // 2]
            out_cnt = sum(
                1 for x in recent if int(x["total_vnd"]) > int(Decimal(med) * utility_outlier_ratio)
            )
            stores_out.append(
                {
                    "store_id": sid,
                    "store_name": recent[0]["store_name"],
                    "utility_type": utype,
                    "latest_amount_vnd": int(recent[0]["total_vnd"]),
                    "median_amount_vnd": med,
                    "out_of_range_months": out_cnt,
                }
            )
        return {"months": months, "stores": stores_out}

    if tool_id == "payment_history":
        return {"payments": []}

    raise ProblemError(404, "NOT_FOUND", "Tool not implemented", f"Tool '{tool_id}' is not implemented.")

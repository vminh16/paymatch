"""Ingest use case: immutable document storage, sha256 idempotency, duplicate policy, normalization, ingest Findings, job + outbox in one transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

import psycopg
from psycopg.types.json import Jsonb

from core.ingest.domain.einvoice import (
    InvoiceUnparseable,
    ParsedInvoice,
    check_arithmetic,
    document_sha256,
    duplicate_key,
    parse_einvoice,
)
from core.shared.clock import Clock, SystemClock
from core.shared.errors import ProblemError
from core.shared.ids import new_id

InvoiceSource = Literal["email", "upload", "bill_pay", "scenario"]
InvoiceType = Literal["goods", "utility", "software"]
DocFormat = Literal["xml", "pdf", "image"]


@dataclass(frozen=True)
class IngestCommand:
    tenant_id: str
    raw_bytes: bytes
    filename: str
    content_type: str
    source: InvoiceSource
    message_text: str | None = None
    external_message_id: str | None = None
    from_address: str | None = None
    subject: str | None = None
    received_at: datetime | None = None
    invoice_type_hint: InvoiceType | None = None
    store_id_hint: str | None = None
    due_on_hint: date | None = None
    trace_id: str | None = None


@dataclass(frozen=True)
class IngestResult:
    invoice_id: str
    document_id: str
    job_id: str | None
    status: str
    already_existed: bool
    duplicate_of: str | None = None
    ingest_reason_codes: tuple[str, ...] = ()


def detect_document_format(filename: str, content_type: str, raw_bytes: bytes) -> DocFormat:
    ct = (content_type or "").lower()
    fn = (filename or "").lower()
    if "xml" in ct or fn.endswith(".xml"):
        return "xml"
    if "pdf" in ct or fn.endswith(".pdf") or raw_bytes.startswith(b"%PDF"):
        return "pdf"
    if ct.startswith("image/") or fn.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    # Sniff XML if content starts with '<' (after optional UTF-8 BOM/whitespace)
    stripped = raw_bytes.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith(b"<"):
        return "xml"
    return "pdf"


def _classify_invoice_type(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    vendor_row: dict[str, Any] | None,
    parsed: ParsedInvoice | None,
    source: InvoiceSource,
    hint: InvoiceType | None,
) -> InvoiceType:
    if hint is not None:
        return hint
    if source == "bill_pay":
        return "utility"
    if vendor_row is not None:
        category = vendor_row.get("category") or ""
        if category == "utility":
            return "utility"
        # Check if vendor has an active card_merchant account (POS software etc.)
        cm = conn.execute(
            """
            SELECT 1 FROM core.vendor_accounts
            WHERE tenant_id = %s AND vendor_id = %s AND kind = 'card_merchant' AND status != 'retired'
            LIMIT 1
            """,
            (tenant_id, vendor_row["vendor_id"]),
        ).fetchone()
        if cm is not None:
            return "software"
        if category == "software_ops":
            vname = (vendor_row.get("name") or "").lower()
            if "phần mềm" in vname or "software" in vname or "saas" in vname:
                return "software"
    if parsed is not None:
        seller_lower = parsed.untrusted.seller_name.text.lower()
        if "điện lực" in seller_lower or "cấp nước" in seller_lower:
            return "utility"
        if "phần mềm" in seller_lower:
            return "software"
    return "goods"


def _infer_store_id(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    store_id_hint: str | None,
    parsed: ParsedInvoice | None,
) -> str | None:
    if store_id_hint:
        row = conn.execute(
            "SELECT store_id FROM core.stores WHERE tenant_id = %s AND store_id = %s",
            (tenant_id, store_id_hint),
        ).fetchone()
        if row:
            return row["store_id"]

    stores = conn.execute(
        "SELECT store_id, name, kind, district, address FROM core.stores WHERE tenant_id = %s",
        (tenant_id,),
    ).fetchall()
    if not stores:
        return None

    hints_text = ""
    if parsed is not None:
        hint_parts = [h.text for h in parsed.untrusted.store_hint]
        for oi in parsed.untrusted.other_info:
            hint_parts.append(oi.value.text)
        hints_text = " ".join(hint_parts).lower()

    if hints_text:
        for st in stores:
            if st["store_id"].lower() in hints_text:
                return st["store_id"]
            if st["name"].lower() in hints_text:
                return st["store_id"]
            if st["address"] and st["address"].lower() in hints_text:
                return st["store_id"]
        if "bếp trung tâm" in hints_text or "khu công nghệ" in hints_text:
            for st in stores:
                if st["kind"] == "central_kitchen":
                    return st["store_id"]
        for st in stores:
            if st["district"] and st["district"].lower() in hints_text:
                return st["store_id"]

    # Default to central_kitchen if tenant has one, else first store
    for st in stores:
        if st["kind"] == "central_kitchen":
            return st["store_id"]
    return stores[0]["store_id"]


def _serialize_untrusted(parsed: ParsedInvoice) -> dict[str, Any]:
    seller_ba = None
    if parsed.untrusted.seller_bank_account is not None:
        seller_ba = {
            "number": parsed.untrusted.seller_bank_account.number,
            "bank_name": parsed.untrusted.seller_bank_account.bank_name,
        }
    return {
        "seller_name": {
            "text": parsed.untrusted.seller_name.text,
            "provenance": "untrusted",
            "source": parsed.untrusted.seller_name.source,
        },
        "seller_address": {
            "text": parsed.untrusted.seller_address.text,
            "provenance": "untrusted",
            "source": parsed.untrusted.seller_address.source,
        },
        "seller_bank_account": seller_ba,
        "bank_accounts": [
            {
                "number": ba.number,
                "bank_name": ba.bank_name,
                "source": ba.source,
            }
            for ba in parsed.untrusted.bank_accounts
        ],
        "payment_terms": (
            {
                "text": parsed.untrusted.payment_terms.text,
                "provenance": "untrusted",
                "source": parsed.untrusted.payment_terms.source,
            }
            if parsed.untrusted.payment_terms is not None
            else None
        ),
        "other_info": [
            {
                "field": oi.field,
                "value": {
                    "text": oi.value.text,
                    "provenance": "untrusted",
                    "source": oi.value.source,
                },
            }
            for oi in parsed.untrusted.other_info
        ],
    }


def _empty_untrusted(filename: str) -> dict[str, Any]:
    return {
        "seller_name": {"text": filename or "Chưa xác định", "provenance": "untrusted", "source": "ocr"},
        "seller_address": {"text": "", "provenance": "untrusted", "source": "ocr"},
        "seller_bank_account": None,
        "bank_accounts": [],
        "payment_terms": None,
        "other_info": [],
    }


def ingest_invoice(
    conn: psycopg.Connection,
    cmd: IngestCommand,
    *,
    clock: Clock | None = None,
) -> IngestResult:
    """Ingest raw invoice bytes atomically per einvoice-xml.md §4 and architecture.md §2."""
    clk = clock or SystemClock()
    now = clk.now()
    received_at = cmd.received_at or now
    sha = document_sha256(cmd.raw_bytes)

    # 1. Idempotency by (tenant_id, sha256) FIRST — before any duplicate check!
    existing_doc = conn.execute(
        """
        SELECT d.document_id, i.invoice_id, i.status, i.duplicate_of
        FROM core.invoice_documents d
        JOIN core.invoices i ON i.document_id = d.document_id
        WHERE d.tenant_id = %s AND d.sha256 = %s
        LIMIT 1
        """,
        (cmd.tenant_id, sha),
    ).fetchone()
    if existing_doc is not None:
        latest_job = conn.execute(
            """
            SELECT job_id FROM core.jobs
            WHERE tenant_id = %s AND invoice_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (cmd.tenant_id, existing_doc["invoice_id"]),
        ).fetchone()
        return IngestResult(
            invoice_id=existing_doc["invoice_id"],
            document_id=existing_doc["document_id"],
            job_id=latest_job["job_id"] if latest_job else None,
            status=existing_doc["status"],
            already_existed=True,
            duplicate_of=existing_doc["duplicate_of"],
        )

    # 2. Detect format & parse XML if applicable
    doc_format = detect_document_format(cmd.filename, cmd.content_type, cmd.raw_bytes)
    parsed: ParsedInvoice | None = None
    ingest_findings: list[tuple[str, str, str]] = []  # (reason_code, severity, reason_text)
    duplicate_of: str | None = None

    if doc_format == "xml":
        try:
            parsed = parse_einvoice(cmd.raw_bytes)
        except InvoiceUnparseable as exc:
            raise ProblemError(
                status=422,
                code="XML_UNPARSEABLE",
                title="Invoice XML could not be parsed",
                detail=f"Không đọc được cấu trúc HĐĐT: {exc.reason}",
            ) from exc

        # 3. Duplicate key check (different sha256)
        seller_tax_norm, symbol_norm, number_norm = duplicate_key(parsed)
        dup_row = conn.execute(
            """
            SELECT invoice_id FROM core.invoices
            WHERE tenant_id = %s
              AND seller_tax_id = %s
              AND symbol = %s
              AND number_norm = %s
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (cmd.tenant_id, seller_tax_norm, symbol_norm, number_norm),
        ).fetchone()

        if dup_row is not None:
            if cmd.source == "upload":
                raise ProblemError(
                    status=409,
                    code="DUPLICATE_INVOICE",
                    title="Duplicate invoice detected",
                    detail=(
                        f"Hóa đơn (MST {seller_tax_norm}, ký hiệu {symbol_norm}, số {number_norm}) "
                        "đã tồn tại với nội dung file khác."
                    ),
                    existing_invoice_id=dup_row["invoice_id"],
                )
            duplicate_of = dup_row["invoice_id"]
            ingest_findings.append(
                (
                    "DUPLICATE_INVOICE",
                    "red",
                    f"Phát hiện hóa đơn trùng khóa ({seller_tax_norm}, {symbol_norm}, {number_norm}) với {duplicate_of}.",
                )
            )

        # Arithmetic checks (Tiers 1-3)
        arith_issues = check_arithmetic(parsed)
        if arith_issues:
            details = "; ".join(i.detail for i in arith_issues[:3])
            ingest_findings.append(
                (
                    "AMOUNT_MISMATCH",
                    "yellow",
                    f"Sai lệch số học trên hóa đơn XML: {details}",
                )
            )
    else:
        ingest_findings.append(
            (
                "NON_XML_SOURCE",
                "yellow",
                "Hóa đơn được gửi dưới dạng PDF/ảnh không có file XML gốc; cần nhập/kiểm tra số liệu.",
            )
        )

    # 4. Vendor lookup
    vendor_row: dict[str, Any] | None = None
    if parsed is not None:
        vendor_row = conn.execute(
            """
            SELECT vendor_id, name, tax_id, category, status
            FROM core.vendors
            WHERE tenant_id = %s AND tax_id = %s
            LIMIT 1
            """,
            (cmd.tenant_id, parsed.seller_tax_id.strip()),
        ).fetchone()
        if vendor_row is None:
            ingest_findings.append(
                (
                    "UNKNOWN_VENDOR",
                    "yellow",
                    f"Mã số thuế người bán {parsed.seller_tax_id} chưa có trong danh bạ NCC.",
                )
            )

    invoice_type = _classify_invoice_type(
        conn,
        tenant_id=cmd.tenant_id,
        vendor_row=vendor_row,
        parsed=parsed,
        source=cmd.source,
        hint=cmd.invoice_type_hint,
    )
    store_id = _infer_store_id(
        conn,
        tenant_id=cmd.tenant_id,
        store_id_hint=cmd.store_id_hint,
        parsed=parsed,
    )

    # Compute due_on (default issued_on + 7 days if XML has issued_on and no hint)
    due_on = cmd.due_on_hint
    if due_on is None and parsed is not None and parsed.issued_on:
        try:
            due_on = date.fromisoformat(parsed.issued_on) + timedelta(days=7)
        except ValueError:
            due_on = None

    document_id = new_id("doc")
    invoice_id = new_id("inv")
    job_id = new_id("job")
    event_id = new_id("evt")

    if parsed is not None:
        _, symbol_norm, number_norm = duplicate_key(parsed)
        vat_breakdown = [
            {
                "vat_rate": vb.vat_rate,
                "taxable_vnd": vb.taxable_vnd,
                "vat_vnd": vb.vat_vnd if vb.vat_vnd is not None else 0,
            }
            for vb in parsed.vat_breakdown
        ]
        related_invoice = (
            {
                "relation": parsed.related_invoice.relation,
                "symbol": parsed.related_invoice.symbol,
                "number": parsed.related_invoice.number,
                "issued_on": parsed.related_invoice.issued_on,
            }
            if parsed.related_invoice is not None
            else None
        )
        untrusted_json = _serialize_untrusted(parsed)
    else:
        symbol_norm = ""
        number_norm = ""
        vat_breakdown = []
        related_invoice = None
        untrusted_json = _empty_untrusted(cmd.filename)

    # 5. Persist everything atomically in one transaction (savepoint if already in transaction)
    with conn.transaction():
        conn.execute(
            """
            INSERT INTO core.invoice_documents (
                document_id, tenant_id, format, sha256, raw_bytes, content_type, filename, received_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                document_id,
                cmd.tenant_id,
                doc_format,
                sha,
                cmd.raw_bytes,
                cmd.content_type or "application/octet-stream",
                cmd.filename or "",
                received_at,
            ),
        )

        conn.execute(
            """
            INSERT INTO core.invoices (
                invoice_id, tenant_id, document_id, document_sha256, store_id, vendor_id,
                seller_tax_id, buyer_tax_id, symbol, number, number_norm,
                issued_on, invoice_type, source, currency,
                subtotal_vnd, vat_total_vnd, total_vnd, vat_breakdown,
                tax_authority_code, einvoice_provider_tax_id, related_invoice,
                untrusted, status, severity, reason_codes, verification_required,
                duplicate_of, due_on, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, 'VND',
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, 'investigating', NULL, %s, FALSE,
                %s, %s, %s, %s
            )
            """,
            (
                invoice_id,
                cmd.tenant_id,
                document_id,
                sha,
                store_id,
                vendor_row["vendor_id"] if vendor_row else None,
                parsed.seller_tax_id.strip() if parsed else "",
                parsed.buyer_tax_id.strip() if parsed else "",
                symbol_norm,
                parsed.number if parsed else "",
                number_norm,
                parsed.issued_on if parsed else None,
                invoice_type,
                cmd.source,
                parsed.subtotal_vnd if parsed else None,
                parsed.vat_total_vnd if parsed else None,
                parsed.total_vnd if parsed else None,
                Jsonb(vat_breakdown),
                parsed.tax_authority_code if parsed else None,
                parsed.einvoice_provider_tax_id if parsed else None,
                Jsonb(related_invoice) if related_invoice is not None else None,
                Jsonb(untrusted_json),
                [rc for rc, _, _ in ingest_findings],
                duplicate_of,
                due_on,
                now,
                now,
            ),
        )

        if parsed is not None:
            for line in parsed.lines:
                line_id = new_id("lin")
                conn.execute(
                    """
                    INSERT INTO core.invoice_lines (
                        line_id, invoice_id, tenant_id, position, kind,
                        item_code, name, unit, quantity, unit_price,
                        discount_vnd, amount_vnd, vat_rate, arithmetic_ok
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        line_id,
                        invoice_id,
                        cmd.tenant_id,
                        line.position,
                        line.kind,
                        Jsonb(
                            {
                                "text": line.item_code.text,
                                "provenance": "untrusted",
                                "source": line.item_code.source,
                            }
                        )
                        if line.item_code is not None
                        else None,
                        Jsonb(
                            {
                                "text": line.name.text,
                                "provenance": "untrusted",
                                "source": line.name.source,
                            }
                        ),
                        Jsonb(
                            {
                                "text": line.unit.text,
                                "provenance": "untrusted",
                                "source": line.unit.source,
                            }
                        )
                        if line.unit is not None
                        else None,
                        line.quantity,
                        line.unit_price,
                        line.discount_vnd,
                        line.amount_vnd,
                        line.vat_rate,
                        line.arithmetic_ok,
                    ),
                )

        if cmd.message_text:
            msg_id = (
                cmd.external_message_id
                if cmd.external_message_id and cmd.external_message_id.startswith("msg_")
                else new_id("msg")
            )
            conn.execute(
                """
                INSERT INTO core.invoice_messages (
                    message_id, invoice_id, tenant_id, channel, external_message_id,
                    from_address, subject, body, received_at
                )
                VALUES (%s, %s, %s, 'email', %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO NOTHING
                """,
                (
                    msg_id,
                    invoice_id,
                    cmd.tenant_id,
                    cmd.external_message_id,
                    cmd.from_address,
                    cmd.subject,
                    Jsonb(
                        {
                            "text": cmd.message_text,
                            "provenance": "untrusted",
                            "source": "email_body",
                        }
                    ),
                    received_at,
                ),
            )

        # Create job queued in same transaction
        conn.execute(
            """
            INSERT INTO core.jobs (
                job_id, tenant_id, task_type, subject, invoice_id, status, attempt, created_at, updated_at
            )
            VALUES (%s, %s, 'investigate_invoice', %s, %s, 'queued', 0, %s, %s)
            """,
            (
                job_id,
                cmd.tenant_id,
                Jsonb({"invoice_id": invoice_id}),
                invoice_id,
                now,
                now,
            ),
        )

        # Store ingest system findings linked to this invoice & job
        for rc, sev, reason_txt in ingest_findings:
            conn.execute(
                """
                INSERT INTO core.findings (
                    finding_id, tenant_id, job_id, invoice_id, attempt, bot_id,
                    bot_version, skill_version, prompt_hash, severity, severity_reported,
                    reason_codes, reason, evidence, provenance, created_at
                )
                VALUES (
                    %s, %s, %s, %s, 0, 'ingest',
                    1, 1, 'ingest-deterministic', %s, %s,
                    %s, %s, '[]'::jsonb, 'trusted', %s
                )
                """,
                (
                    new_id("fnd"),
                    cmd.tenant_id,
                    job_id,
                    invoice_id,
                    sev,
                    sev,
                    [rc],
                    Jsonb({"text": reason_txt, "provenance": "untrusted", "source": "bot_reason"}),
                    now,
                ),
            )

        # Emit invoice.ingested to core.outbox in same transaction
        conn.execute(
            """
            INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
            VALUES (%s, 'invoice.ingested', 1, %s, %s, %s, %s)
            """,
            (
                event_id,
                now,
                cmd.tenant_id,
                cmd.trace_id,
                Jsonb(
                    {
                        "invoice_id": invoice_id,
                        "source": cmd.source,
                        "invoice_type": invoice_type,
                        "duplicate_of": duplicate_of,
                    }
                ),
            ),
        )

    return IngestResult(
        invoice_id=invoice_id,
        document_id=document_id,
        job_id=job_id,
        status="investigating",
        already_existed=False,
        duplicate_of=duplicate_of,
        ingest_reason_codes=tuple(rc for rc, _, _ in ingest_findings),
    )

"""Contract-compliant serializers from core DB rows to PayMatch Invoice, InvoiceSummary, Finding, Job dicts."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg

VN_TZ = timezone(timedelta(hours=7))


def fmt_ts(val: datetime | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    dt = val.astimezone(VN_TZ) if val.tzinfo else val.replace(tzinfo=VN_TZ)
    return dt.isoformat(timespec="seconds")


def fmt_date(val: date | str | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return val.isoformat()


def compute_allowed_actions(
    *,
    status: str,
    role: str,
    reason_codes: list[str],
    mandate_mode: str | None,
) -> list[str]:
    actions: list[str] = []
    is_owner = role == "owner"
    is_oa = role in {"owner", "accountant"}

    if status == "pending_approval":
        if is_owner and mandate_mode != "review_only":
            actions.append("approve")
        if is_owner:
            actions.append("reject")
        if is_oa:
            actions.append("reinvestigate")
        if is_oa and "NON_XML_SOURCE" in reason_codes:
            actions.append("enter_manual_fields")
    elif status == "blocked":
        if is_owner:
            actions.append("reject")
        if is_oa:
            actions.append("reinvestigate")
        if is_owner and "PAYEE_CHANGE_REQUEST" in reason_codes:
            actions.append("open_account_change")
        if is_owner and (
            "PERSONAL_ACCOUNT" in reason_codes or "UNKNOWN_VENDOR" in reason_codes
        ):
            actions.append("create_escrow")
    elif status == "escrow_held":
        if is_owner:
            actions.append("approve")
    elif status in {"approved", "scheduled"}:
        if is_oa:
            actions.append("schedule")
        if is_owner:
            actions.extend(["pay_now", "cancel_payment", "reject"])
        if is_oa:
            actions.append("reinvestigate")
    elif status == "payment_failed":
        if is_oa:
            actions.append("reinvestigate")

    return actions


def build_invoice_summary(
    inv_row: dict[str, Any],
    vendor_name: str | None = None,
) -> dict[str, Any]:
    return {
        "invoice_id": inv_row["invoice_id"],
        "store_id": inv_row.get("store_id"),
        "vendor_id": inv_row.get("vendor_id"),
        "vendor_name": vendor_name if inv_row.get("vendor_id") else None,
        "seller_tax_id": inv_row.get("seller_tax_id") or "",
        "symbol": inv_row.get("symbol") or "",
        "number": inv_row.get("number") or "",
        "issued_on": fmt_date(inv_row.get("issued_on")),
        "invoice_type": inv_row["invoice_type"],
        "total_vnd": inv_row.get("total_vnd"),
        "status": inv_row["status"],
        "severity": inv_row.get("severity"),
        "reason_codes": list(inv_row.get("reason_codes") or []),
        "verification_required": bool(inv_row.get("verification_required", False)),
        "due_on": fmt_date(inv_row.get("due_on")),
        "scheduled_for": fmt_date(inv_row.get("scheduled_for")),
        "updated_at": fmt_ts(inv_row["updated_at"]),
    }


def build_full_invoice(
    conn: psycopg.Connection,
    inv_row: dict[str, Any],
    *,
    role: str = "owner",
    mandate_mode: str | None = None,
) -> dict[str, Any]:
    tenant_id = inv_row["tenant_id"]
    invoice_id = inv_row["invoice_id"]

    vendor_name: str | None = None
    if inv_row.get("vendor_id"):
        vrow = conn.execute(
            "SELECT name FROM core.vendors WHERE tenant_id = %s AND vendor_id = %s",
            (tenant_id, inv_row["vendor_id"]),
        ).fetchone()
        if vrow:
            vendor_name = vrow["name"]

    doc_row = conn.execute(
        """
        SELECT document_id, format, sha256, received_at
        FROM core.invoice_documents
        WHERE tenant_id = %s AND document_id = %s
        """,
        (tenant_id, inv_row["document_id"]),
    ).fetchone()

    line_rows = conn.execute(
        """
        SELECT line_id, position, kind, item_code, name, unit, quantity, unit_price,
               discount_vnd, amount_vnd, vat_rate, arithmetic_ok
        FROM core.invoice_lines
        WHERE tenant_id = %s AND invoice_id = %s
        ORDER BY position ASC
        """,
        (tenant_id, invoice_id),
    ).fetchall()

    msg_rows = conn.execute(
        """
        SELECT message_id, channel, received_at, body
        FROM core.invoice_messages
        WHERE tenant_id = %s AND invoice_id = %s
        ORDER BY received_at ASC
        """,
        (tenant_id, invoice_id),
    ).fetchall()

    brief_row = conn.execute(
        """
        SELECT brief_id, job_id, lines, cited_evidence, model, prompt_hash
        FROM core.briefs
        WHERE tenant_id = %s AND invoice_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (tenant_id, invoice_id),
    ).fetchone()

    latest_job = conn.execute(
        """
        SELECT job_id, attempt FROM core.jobs
        WHERE tenant_id = %s AND invoice_id = %s AND status = 'completed'
        ORDER BY completed_at DESC NULLS LAST, created_at DESC
        LIMIT 1
        """,
        (tenant_id, invoice_id),
    ).fetchone()

    if latest_job:
        # I5: derive current findings_summary from the latest completed job's final attempt (plus invoice-level ingest/cross-alert findings)
        f_rows = conn.execute(
            """
            SELECT bot_id, severity, reason_codes
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
            (tenant_id, invoice_id, latest_job["job_id"], int(latest_job["attempt"])),
        ).fetchall()
    else:
        f_rows = conn.execute(
            """
            SELECT bot_id, severity, reason_codes
            FROM core.findings
            WHERE tenant_id = %s AND invoice_id = %s
              AND superseded = FALSE
              AND (bot_id = 'ingest' OR (job_id IS NULL AND bot_id = 'system'))
            ORDER BY created_at ASC
            """,
            (tenant_id, invoice_id),
        ).fetchall()

    apv_row = conn.execute(
        """
        SELECT approval_id, method, status, approver_user_id, created_at
        FROM core.approvals
        WHERE tenant_id = %s AND invoice_id = %s
        ORDER BY (status = 'active') DESC, created_at DESC
        LIMIT 1
        """,
        (tenant_id, invoice_id),
    ).fetchone()

    raw_untrusted = dict(inv_row.get("untrusted") or {})
    untrusted_payload = {
        "seller_name": raw_untrusted.get(
            "seller_name", {"text": "", "provenance": "untrusted", "source": "invoice_xml"}
        ),
        "seller_address": raw_untrusted.get(
            "seller_address", {"text": "", "provenance": "untrusted", "source": "invoice_xml"}
        ),
        "seller_bank_account": raw_untrusted.get("seller_bank_account"),
        "payment_terms": raw_untrusted.get("payment_terms"),
        "other_info": list(raw_untrusted.get("other_info") or []),
        "messages": [
            {
                "message_id": m["message_id"],
                "channel": m["channel"],
                "received_at": fmt_ts(m["received_at"]),
                "body": m["body"],
            }
            for m in msg_rows
        ],
    }

    summary = build_invoice_summary(inv_row, vendor_name=vendor_name)
    etag = f'"{invoice_id}:v{inv_row.get("version", 1)}"'

    return {
        **summary,
        "source": inv_row["source"],
        "duplicate_of": inv_row.get("duplicate_of"),
        "manual_fields": inv_row.get("manual_fields"),
        "document": {
            "document_id": doc_row["document_id"],
            "format": doc_row["format"],
            "sha256": doc_row["sha256"],
            "received_at": fmt_ts(doc_row["received_at"]),
        },
        "buyer_tax_id": inv_row.get("buyer_tax_id") or "",
        "currency": inv_row.get("currency") or "VND",
        "subtotal_vnd": inv_row.get("subtotal_vnd"),
        "vat_total_vnd": inv_row.get("vat_total_vnd"),
        "vat_breakdown": list(inv_row.get("vat_breakdown") or []),
        "tax_authority_code": inv_row.get("tax_authority_code"),
        "einvoice_provider_tax_id": inv_row.get("einvoice_provider_tax_id"),
        "related_invoice": inv_row.get("related_invoice"),
        "lines": [
            {
                "line_id": ln["line_id"],
                "position": ln["position"],
                "kind": ln["kind"],
                "item_code": ln["item_code"],
                "name": ln["name"],
                "unit": ln["unit"],
                "quantity": ln["quantity"],
                "unit_price": ln["unit_price"],
                "discount_vnd": ln["discount_vnd"],
                "amount_vnd": ln["amount_vnd"],
                "vat_rate": ln["vat_rate"],
                "arithmetic_ok": bool(ln["arithmetic_ok"]),
            }
            for ln in line_rows
        ],
        "untrusted": untrusted_payload,
        "brief": (
            {
                "brief_id": brief_row["brief_id"],
                "job_id": brief_row["job_id"],
                "lines": list(brief_row["lines"]),
                "cited_evidence": list(brief_row["cited_evidence"]),
                "model": brief_row["model"],
                "prompt_hash": brief_row["prompt_hash"],
            }
            if brief_row
            else None
        ),
        "findings_summary": [
            {
                "bot_id": f["bot_id"],
                "severity": f["severity"],
                "reason_codes": list(f["reason_codes"]),
            }
            for f in f_rows
        ],
        "approval": (
            {
                "approval_id": apv_row["approval_id"],
                "method": apv_row["method"],
                "status": apv_row["status"],
                "approver_user_id": apv_row["approver_user_id"],
                "created_at": fmt_ts(apv_row["created_at"]),
            }
            if apv_row
            else None
        ),
        "payment": None,
        "escrow": None,
        "allowed_actions": compute_allowed_actions(
            status=inv_row["status"],
            role=role,
            reason_codes=list(inv_row.get("reason_codes") or []),
            mandate_mode=mandate_mode,
        ),
        "etag": etag,
    }


def serialize_finding(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": row["finding_id"],
        "job_id": row["job_id"],
        "attempt": row["attempt"],
        "bot_id": row["bot_id"],
        "bot_version": row["bot_version"],
        "skill_version": row["skill_version"],
        "prompt_hash": row["prompt_hash"],
        "severity": row["severity"],
        "severity_reported": row["severity_reported"],
        "reason_codes": list(row["reason_codes"]),
        "reason": row["reason"],
        "evidence": list(row["evidence"]),
        "provenance": row["provenance"],
        "proposed_channel": row.get("proposed_channel"),
        "proposed_pay_on": fmt_date(row.get("proposed_pay_on")),
        "created_at": fmt_ts(row["created_at"]),
    }


def serialize_job(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "task_type": row["task_type"],
        "tenant_id": row["tenant_id"],
        "subject": row["subject"],
        "status": row["status"],
        "attempt": row["attempt"],
        "bots_called": list(row.get("bots_called") or []),
        "bot_states": list(row.get("bot_states") or []),
        "created_at": fmt_ts(row["created_at"]),
        "started_at": fmt_ts(row.get("started_at")),
        "completed_at": fmt_ts(row.get("completed_at")),
    }


def serialize_approval(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval_id": row["approval_id"],
        "invoice_id": row.get("invoice_id"),
        "purchase_order_id": row.get("purchase_order_id"),
        "source_invoice_id": row.get("source_invoice_id"),
        "job_id": row.get("job_id"),
        "status": row["status"],
        "amount_vnd": int(row["amount_vnd"]),
        "payee_account_id": row["payee_account_id"],
        "channel": row["channel"],
        "intent_hash": row["intent_hash"],
        "approver_user_id": row.get("approver_user_id"),
        "method": row["method"],
        "mandate_version": row.get("mandate_version"),
        "bulk_batch_id": row.get("bulk_batch_id"),
        "verification": row.get("verification"),
        "auth_proof_jti": row.get("auth_proof_jti"),
        "created_at": fmt_ts(row["created_at"]),
        "superseded_at": fmt_ts(row.get("superseded_at")),
        "superseded_reason": row.get("superseded_reason"),
    }

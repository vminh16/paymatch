"""Pure supervisor-safe projections and correspondence relevance filters (B4, I6).

NO I/O, NO DB, NO network.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

# Strict format patterns for XML-derived identifiers allowed into supervisor tool results (B4)
_SAFE_TAX_ID_RE = re.compile(r"^[0-9]{10}(-[0-9]{3})?$")
_SAFE_SYMBOL_RE = re.compile(r"^[1-6][A-Z0-9]{1,10}$")
_SAFE_NUMBER_RE = re.compile(r"^[0-9]{1,12}$")


def sanitize_supervisor_tax_id(raw: str | None) -> str:
    val = (raw or "").strip()
    return val if _SAFE_TAX_ID_RE.fullmatch(val) else ""


def sanitize_supervisor_symbol(raw: str | None) -> str:
    val = (raw or "").strip().upper()
    return val if _SAFE_SYMBOL_RE.fullmatch(val) else ""


def sanitize_supervisor_number(raw: str | None) -> str:
    val = (raw or "").strip()
    return val if _SAFE_NUMBER_RE.fullmatch(val) else ""


def build_supervisor_invoice_summary(
    inv_row: Mapping[str, Any],
    *,
    vendor_name: str | None,
    fmt_date_fn: Callable[[Any], str | None],
    fmt_ts_fn: Callable[[Any], str | None],
) -> dict[str, Any]:
    """Supervisor-safe InvoiceSummary projection (B4).

    Includes ONLY system IDs, code-derived numbers, registry-derived vendor_name
    (never XML seller_name), and strictly format-checked XML identifiers (dropped to ''
    if they fail strict numeric/alphanumeric validation).
    """
    return {
        "invoice_id": inv_row["invoice_id"],
        "store_id": inv_row.get("store_id"),
        "vendor_id": inv_row.get("vendor_id"),
        "vendor_name": vendor_name if inv_row.get("vendor_id") else None,
        "seller_tax_id": sanitize_supervisor_tax_id(inv_row.get("seller_tax_id")),
        "symbol": sanitize_supervisor_symbol(inv_row.get("symbol")),
        "number": sanitize_supervisor_number(inv_row.get("number")),
        "issued_on": fmt_date_fn(inv_row.get("issued_on")),
        "invoice_type": inv_row["invoice_type"],
        "total_vnd": inv_row.get("total_vnd"),
        "status": inv_row["status"],
        "severity": inv_row.get("severity"),
        "reason_codes": list(inv_row.get("reason_codes") or []),
        "verification_required": bool(inv_row.get("verification_required", False)),
        "due_on": fmt_date_fn(inv_row.get("due_on")),
        "scheduled_for": fmt_date_fn(inv_row.get("scheduled_for")),
        "updated_at": fmt_ts_fn(inv_row["updated_at"]),
    }


def _digits_only(text: str | None) -> str:
    return "".join(ch for ch in (text or "") if ch.isdigit())


def _email_domain_root(addr: str | None) -> str:
    if not addr or "@" not in addr:
        return ""
    domain = addr.rsplit("@", 1)[1].strip().lower()
    return domain.split(".", 1)[0]


def is_relevant_inbox_message(
    msg: Mapping[str, Any],
    *,
    linked_external_ids: set[str],
    vendor_email: str | None,
    vendor_name: str | None,
    invoice_symbol: str | None,
    invoice_number: str | None,
    invoice_number_norm: str | None,
    seller_tax_id: str | None,
) -> bool:
    """Deterministic correspondence filter for `inbox` tool (I6): avoids dumping unrelated tenant emails
    while still keeping BEC lookalike emails mentioning the vendor/invoice or similar domain root.
    """
    msg_id = str(msg.get("message_id") or "")
    if msg_id and msg_id in linked_external_ids:
        return True

    sender = str(msg.get("from") or "").strip().lower()
    subject = str(msg.get("subject") or "").lower()
    body = str(msg.get("body_text") or "").lower()
    haystack = f"{subject}\n{body}"

    if vendor_email:
        v_email_l = vendor_email.strip().lower()
        if sender == v_email_l:
            return True
        v_root = _email_domain_root(v_email_l)
        s_root = _email_domain_root(sender)
        # Allow lookalike BEC domain sharing >=4-char prefix (e.g. 'tradao' vs 'tradao-billing')
        if v_root and s_root and (v_root in s_root or s_root in v_root or (len(v_root) >= 4 and s_root.startswith(v_root[:4]))):
            return True

    for token in (invoice_symbol, invoice_number, invoice_number_norm, seller_tax_id):
        tok = (token or "").strip().lower()
        if tok and len(tok) >= 3 and tok in haystack:
            return True

    if vendor_name:
        v_words = [w for w in vendor_name.lower().split() if len(w) >= 4]
        if v_words and any(w in haystack for w in v_words[-2:]):
            return True

    return False


def is_relevant_chat_thread(
    thread: Mapping[str, Any],
    messages: list[Mapping[str, Any]],
    *,
    vendor_phone: str | None,
    vendor_name: str | None,
    invoice_symbol: str | None,
    invoice_number: str | None,
    invoice_number_norm: str | None,
    seller_tax_id: str | None,
) -> bool:
    """Deterministic correspondence filter for `chat_messages` tool (I6)."""
    v_digits = _digits_only(vendor_phone)
    t_digits = _digits_only(str(thread.get("counterparty_phone") or ""))
    if v_digits and t_digits and (v_digits == t_digits or v_digits[-8:] == t_digits[-8:]):
        return True

    parts = [str(thread.get("counterparty_name") or "").lower()]
    parts.extend(str(m.get("text") or "").lower() for m in messages)
    haystack = "\n".join(parts)

    for token in (invoice_symbol, invoice_number, invoice_number_norm, seller_tax_id):
        tok = (token or "").strip().lower()
        if tok and len(tok) >= 3 and tok in haystack:
            return True

    if vendor_name:
        v_words = [w for w in vendor_name.lower().split() if len(w) >= 4]
        if v_words and any(w in haystack for w in v_words[-2:]):
            return True

    return False

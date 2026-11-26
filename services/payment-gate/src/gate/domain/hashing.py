"""Intent hashing (via shared paymatch_hashing), indicator hashing, and transfer memo formatting."""

from __future__ import annotations

import hashlib
import re

from paymatch_hashing import intent_hash_escrow, intent_hash_invoice

from gate.domain.models import IndicatorRef, InvoiceSnapshot, VendorAccountSnapshot, VendorSnapshot

_DIGITS_RE = re.compile(r"\D+")


def compute_invoice_intent_hash(
    *,
    invoice_id: str,
    document_sha256: str,
    payee_account_id: str | None,
    amount_vnd: int,
    channel: str,
) -> str:
    """Delegate invoice intent_hash computation strictly to paymatch_hashing."""
    return intent_hash_invoice(
        invoice_id=invoice_id,
        document_sha256=document_sha256,
        payee_account_id=payee_account_id,
        amount_vnd=amount_vnd,
        channel=channel,
    )


def compute_escrow_intent_hash(
    *,
    purchase_order_id: str,
    payee_account_id: str,
    amount_vnd: int,
) -> str:
    """Delegate escrow intent_hash computation strictly to paymatch_hashing."""
    return intent_hash_escrow(
        purchase_order_id=purchase_order_id,
        payee_account_id=payee_account_id,
        amount_vnd=amount_vnd,
        channel="escrow",
    )


def _sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_account_indicator(bank_code: str, account_number: str) -> str:
    """Normalize and hash bank account per docs/04-data/sim-world-dataset.md §3.10."""
    return _sha256_hex(f"{bank_code.strip().upper()}:{account_number.strip()}")


def hash_phone_indicator(phone: str) -> str:
    """Normalize digits-only phone and hash per docs/04-data/sim-world-dataset.md §3.10."""
    return _sha256_hex(_DIGITS_RE.sub("", phone))


def hash_tax_id_indicator(tax_id: str) -> str:
    """Normalize and hash tax ID per docs/04-data/sim-world-dataset.md §3.10."""
    return _sha256_hex(tax_id.strip())


def hash_merchant_id_indicator(merchant_id: str) -> str:
    """Normalize and hash card merchant ID."""
    return _sha256_hex(merchant_id.strip())


def extract_indicators(
    *,
    seller_tax_id: str | None,
    vendor: VendorSnapshot | None,
    payee_account: VendorAccountSnapshot | None,
) -> tuple[IndicatorRef, ...]:
    """Collect deduplicated risk indicators for an invoice/vendor/payee pair."""
    seen: set[IndicatorRef] = set()
    ordered: list[IndicatorRef] = []

    def add(kind: str, value_hash: str) -> None:
        ref = IndicatorRef(kind=kind, value_hash=value_hash)
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)

    if seller_tax_id and seller_tax_id.strip():
        add("tax_id", hash_tax_id_indicator(seller_tax_id))
    if vendor is not None:
        if vendor.tax_id and vendor.tax_id.strip():
            add("tax_id", hash_tax_id_indicator(vendor.tax_id))
        if vendor.phone_on_file and _DIGITS_RE.sub("", vendor.phone_on_file):
            add("phone", hash_phone_indicator(vendor.phone_on_file))
    if payee_account is not None:
        if (
            payee_account.kind == "bank_account"
            and payee_account.bank_code
            and payee_account.account_number
        ):
            add(
                "account_hash",
                hash_account_indicator(payee_account.bank_code, payee_account.account_number),
            )
        elif payee_account.kind == "card_merchant" and payee_account.merchant_id:
            add("merchant_id", hash_merchant_id_indicator(payee_account.merchant_id))

    return tuple(ordered)


def format_transfer_memo(invoice: InvoiceSnapshot) -> str:
    """Format transfer memo per D2: 'MST · ký hiệu · số'."""
    return f"{invoice.seller_tax_id} · {invoice.symbol} · {invoice.number}"

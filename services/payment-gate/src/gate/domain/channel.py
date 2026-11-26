"""Pure channel selection and registry-only payee resolution."""

from __future__ import annotations

from collections.abc import Sequence

from paymatch_contracts.gate import Channel

from gate.domain.models import (
    EscrowRecord,
    InvoiceSnapshot,
    MandateSnapshot,
    VendorAccountSnapshot,
    VendorSnapshot,
)


def select_channel(
    *,
    invoice: InvoiceSnapshot,
    mandate: MandateSnapshot | None,
    held_po_escrow: EscrowRecord | None,
) -> Channel:
    """Choose payment channel per docs/05-api/gate-api.md §1.

    1. Invoice linked to a PO with a currently held escrow -> escrow.
    2. First matching mandate.channel_rules entry for invoice.invoice_type (non-escrow).
    3. Default -> bank_transfer.
    """
    if held_po_escrow is not None and held_po_escrow.status.value == "held":
        return Channel.escrow

    if mandate is not None:
        for rule in mandate.channel_rules:
            if rule.invoice_type == invoice.invoice_type and rule.channel != Channel.escrow.value:
                return Channel(rule.channel)

    return Channel.bank_transfer


def is_account_valid_for_channel(
    account: VendorAccountSnapshot,
    *,
    vendor: VendorSnapshot,
    channel: Channel,
) -> bool:
    """Verify account belongs to vendor, has allowed status, and matches channel kind."""
    if account.vendor_id != vendor.vendor_id or account.tenant_id != vendor.tenant_id:
        return False

    if channel == Channel.bank_transfer:
        return (
            account.status == "verified"
            and account.kind == "bank_account"
            and bool(account.bank_code)
            and bool(account.account_number)
        )

    if channel == Channel.virtual_card:
        return (
            account.status == "verified"
            and account.kind == "card_merchant"
            and bool(account.merchant_id)
        )

    if channel == Channel.escrow:
        return (
            account.status in ("verified", "escrow_only")
            and account.kind == "bank_account"
            and bool(account.bank_code)
            and bool(account.account_number)
        )

    return False


def resolve_payee_account(
    *,
    vendor: VendorSnapshot | None,
    seller_tax_id: str,
    accounts: Sequence[VendorAccountSnapshot],
    channel: Channel,
    held_po_escrow: EscrowRecord | None = None,
    preferred_account_id: str | None = None,
) -> VendorAccountSnapshot | None:
    """Resolve payee strictly from vendor registry matching MST (invariant #3).

    Never accepts bank details from invoice text or untrusted messages.
    """
    if vendor is None or vendor.status != "active":
        return None
    if vendor.tax_id.strip() != seller_tax_id.strip():
        return None

    # For an invoice bound to an already-held PO escrow, the escrow's registered account is authoritative.
    if channel == Channel.escrow and held_po_escrow is not None:
        for acc in accounts:
            if acc.vendor_account_id == held_po_escrow.vendor_account_id and is_account_valid_for_channel(
                acc, vendor=vendor, channel=Channel.escrow
            ):
                return acc
        return None

    eligible = [
        acc
        for acc in sorted(accounts, key=lambda a: a.vendor_account_id)
        if is_account_valid_for_channel(acc, vendor=vendor, channel=channel)
    ]
    if not eligible:
        return None

    if preferred_account_id is not None:
        for acc in eligible:
            if acc.vendor_account_id == preferred_account_id:
                return acc
        return None

    return eligible[0]

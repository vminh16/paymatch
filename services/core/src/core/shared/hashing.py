"""Hashing helpers: delegates intent/payload/action hashes to paymatch_hashing; indicator SHA-256 normalization."""

from __future__ import annotations

import hashlib
import re

from paymatch_hashing import (
    MAX_SAFE_INT,
    MIN_SAFE_INT,
    action_hash,
    intent_hash_escrow,
    intent_hash_invoice,
    jcs_canonicalize,
    normalize_timestamp_utc,
    payload_hash_approval,
    payload_hash_batch,
    sha256_jcs,
)

__all__ = [
    "MAX_SAFE_INT",
    "MIN_SAFE_INT",
    "action_hash",
    "hash_account_indicator",
    "hash_card_id_indicator",
    "hash_merchant_id_indicator",
    "hash_phone_indicator",
    "hash_tax_id_indicator",
    "intent_hash_escrow",
    "intent_hash_invoice",
    "jcs_canonicalize",
    "mask_account_number",
    "mask_phone",
    "normalize_timestamp_utc",
    "payload_hash_approval",
    "payload_hash_batch",
    "sha256_jcs",
]


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_account_indicator(bank_code: str, account_number: str) -> str:
    """Normalize account indicator per docs/04-data/sim-world-dataset.md §3.10."""
    return _sha256_hex(f"{bank_code.strip().upper()}:{account_number.strip()}")


def hash_phone_indicator(phone: str) -> str:
    """Normalize phone indicator (digits only) per docs/04-data/sim-world-dataset.md §3.10."""
    digits = re.sub(r"\D+", "", phone)
    return _sha256_hex(digits)


def hash_tax_id_indicator(tax_id: str) -> str:
    """Normalize tax_id indicator per docs/04-data/sim-world-dataset.md §3.10."""
    return _sha256_hex(tax_id.strip())


def hash_card_id_indicator(card_id: str) -> str:
    """Hash card_id indicator as 64-char lowercase sha256 hex (I8)."""
    return _sha256_hex(card_id.strip())


def hash_merchant_id_indicator(merchant_id: str) -> str:
    """Hash merchant_id indicator as 64-char lowercase sha256 hex (I8)."""
    return _sha256_hex(merchant_id.strip())


def mask_account_number(account_number: str | None) -> str | None:
    if not account_number:
        return None
    s = account_number.strip()
    if len(s) <= 4:
        return "****"
    return "****" + s[-4:]


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    s = phone.strip()
    if len(s) <= 4:
        return "***"
    return s[:4] + "***" + s[-3:]

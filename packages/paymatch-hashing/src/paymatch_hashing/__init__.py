"""RFC 8785 (JCS) canonical JSON and SHA-256 hashing per docs/05-api/schemas.md §4."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from enum import Enum
from typing import Any

MAX_SAFE_INT = 9007199254740991
MIN_SAFE_INT = -9007199254740991

_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)

__all__ = [
    "MAX_SAFE_INT",
    "MIN_SAFE_INT",
    "action_hash",
    "intent_hash_escrow",
    "intent_hash_invoice",
    "jcs_canonicalize",
    "normalize_timestamp_utc",
    "payload_hash_approval",
    "payload_hash_batch",
    "sha256_jcs",
]

_SHORT_ESCAPES: dict[int, str] = {
    0x08: r"\b",
    0x09: r"\t",
    0x0A: r"\n",
    0x0C: r"\f",
    0x0D: r"\r",
    0x22: r"\"",
    0x5C: r"\\",
}


def _escape_jcs_string(value: str) -> str:
    parts: list[str] = ['"']
    for ch in value:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            raise ValueError(f"Lone UTF-16 surrogate U+{code:04X} is not valid in JCS strings")
        if code in _SHORT_ESCAPES:
            parts.append(_SHORT_ESCAPES[code])
        elif code < 0x20:
            parts.append(f"\\u{code:04x}")
        else:
            parts.append(ch)
    parts.append('"')
    return "".join(parts)


def _utf16_sort_key(key: str) -> bytes:
    for ch in key:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            raise ValueError(f"Lone UTF-16 surrogate U+{code:04X} is not valid in JCS object keys")
    return key.encode("utf-16-be")


def jcs_canonicalize(value: Any) -> str:
    """Serialize a JSON-compatible value into RFC 8785 (JCS) canonical form.

    Supports dicts (string keys), lists/tuples, strings (and StrEnum/Enum values),
    integers, booleans, and None. Rejects floats and unsupported types.
    """
    if isinstance(value, Enum):
        value = value.value

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        raise TypeError("Floats are forbidden in PayMatch canonical JSON; use integer VND or string Decimal")
    if isinstance(value, int):
        if value < MIN_SAFE_INT or value > MAX_SAFE_INT:
            raise ValueError(
                f"Integer {value} is outside IEEE-754 safe integer range "
                f"[{MIN_SAFE_INT}, {MAX_SAFE_INT}]"
            )
        return str(value)
    if isinstance(value, str):
        return _escape_jcs_string(value)
    if isinstance(value, Mapping):
        items: list[tuple[bytes, str, Any]] = []
        for k, v in value.items():
            if isinstance(k, Enum):
                k = k.value
            if not isinstance(k, str):
                raise TypeError(f"JCS object keys must be strings, got {type(k).__name__}")
            items.append((_utf16_sort_key(k), k, v))
        items.sort(key=lambda entry: entry[0])
        for idx in range(1, len(items)):
            if items[idx][1] == items[idx - 1][1]:
                raise ValueError(f"Duplicate object key after normalization: {items[idx][1]!r}")
        rendered = [f"{_escape_jcs_string(k)}:{jcs_canonicalize(v)}" for _, k, v in items]
        return "{" + ",".join(rendered) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(jcs_canonicalize(elem) for elem in value) + "]"

    raise TypeError(f"Unsupported type for JCS canonicalization: {type(value).__name__}")


def sha256_jcs(value: Any) -> str:
    """Return lowercase hex SHA-256 of the RFC 8785 canonical JSON UTF-8 bytes."""
    canonical = jcs_canonicalize(value)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_non_empty_str(value: Any, name: str) -> str:
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_int_not_bool(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    if value < MIN_SAFE_INT or value > MAX_SAFE_INT:
        raise ValueError(
            f"{name} ({value}) is outside IEEE-754 safe integer range "
            f"[{MIN_SAFE_INT}, {MAX_SAFE_INT}]"
        )
    return value


def normalize_timestamp_utc(value: str | datetime) -> str:
    """Normalize an RFC 3339 timestamp with timezone offset to UTC 'YYYY-MM-DDTHH:MM:SSZ'.

    Drops fractional seconds (truncation toward zero) and rejects naive timestamps.
    """
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone offset (RFC 3339)")
    elif isinstance(value, str):
        if not _RFC3339_RE.match(value):
            raise ValueError(
                f"Timestamp must be RFC 3339 with explicit timezone offset, got {value!r}"
            )
        dt = datetime.fromisoformat(value)
    else:
        raise TypeError(f"Timestamp must be str or datetime, got {type(value).__name__}")
    utc_dt = dt.astimezone(timezone.utc)
    return (
        f"{utc_dt.year:04d}-{utc_dt.month:02d}-{utc_dt.day:02d}"
        f"T{utc_dt.hour:02d}:{utc_dt.minute:02d}:{utc_dt.second:02d}Z"
    )


def intent_hash_invoice(
    invoice_id: str,
    document_sha256: str,
    payee_account_id: str | None,
    amount_vnd: int,
    channel: str,
) -> str:
    """Compute invoice intent_hash per docs/05-api/schemas.md §4."""
    inv_id = _require_non_empty_str(invoice_id, "invoice_id")
    doc_sha = _require_non_empty_str(document_sha256, "document_sha256")
    payee_id = (
        None
        if payee_account_id is None
        else _require_non_empty_str(payee_account_id, "payee_account_id")
    )
    amt = _require_int_not_bool(amount_vnd, "amount_vnd")
    ch = _require_non_empty_str(channel, "channel")
    return sha256_jcs(
        {
            "v": 1,
            "kind": "invoice",
            "invoice_id": inv_id,
            "document_sha256": doc_sha,
            "payee_account_id": payee_id,
            "amount_vnd": amt,
            "channel": ch,
        }
    )


def intent_hash_escrow(
    purchase_order_id: str,
    payee_account_id: str,
    amount_vnd: int,
    channel: str = "escrow",
) -> str:
    """Compute escrow intent_hash per docs/05-api/schemas.md §4."""
    po_id = _require_non_empty_str(purchase_order_id, "purchase_order_id")
    payee_id = _require_non_empty_str(payee_account_id, "payee_account_id")
    amt = _require_int_not_bool(amount_vnd, "amount_vnd")
    ch = _require_non_empty_str(channel, "channel")
    if ch != "escrow":
        raise ValueError(f"Escrow intent channel must be 'escrow', got {ch!r}")
    return sha256_jcs(
        {
            "v": 1,
            "kind": "escrow",
            "purchase_order_id": po_id,
            "payee_account_id": payee_id,
            "amount_vnd": amt,
            "channel": "escrow",
        }
    )


def payload_hash_approval(
    intent_hash: str,
    verification: Any = None,
) -> str:
    """Compute single-approval payload_hash per docs/05-api/schemas.md §4."""
    ih = _require_non_empty_str(intent_hash, "intent_hash")
    if verification is None:
        ver_obj: dict[str, Any] | None = None
    else:
        if hasattr(verification, "model_dump"):
            raw = verification.model_dump(mode="json")
        elif isinstance(verification, Mapping):
            raw = dict(verification)
        else:
            raise TypeError(
                f"verification must be a mapping, Pydantic model, or None, got {type(verification).__name__}"
            )
        ver_obj = dict(raw)
        ver_obj.setdefault("note", None)
        expected_keys = {"called_phone_on_file", "result", "note", "at"}
        if set(ver_obj.keys()) != expected_keys:
            missing = sorted(expected_keys - set(ver_obj.keys()))
            extra = sorted(set(ver_obj.keys()) - expected_keys)
            raise ValueError(
                f"verification keys mismatch (missing={missing}, unexpected={extra})"
            )
        if not isinstance(ver_obj["called_phone_on_file"], bool):
            raise TypeError("verification.called_phone_on_file must be a boolean")
        ver_obj["result"] = _require_non_empty_str(ver_obj["result"], "verification.result")
        ver_obj["at"] = normalize_timestamp_utc(ver_obj["at"])
        if ver_obj["note"] is not None and not isinstance(ver_obj["note"], str):
            raise TypeError("verification.note must be a string or None")
    return sha256_jcs({"intent_hash": ih, "verification": ver_obj})


def payload_hash_batch(
    preview_id: str,
    items: Iterable[Sequence[str]],
) -> str:
    """Compute bulk-approval batch payload_hash per docs/05-api/schemas.md §4.

    Items are pairs [invoice_id, intent_hash] sorted ascending by invoice_id.
    """
    pvw_id = _require_non_empty_str(preview_id, "preview_id")
    normalized: list[list[str]] = []
    for pair in items:
        if isinstance(pair, (str, bytes)) or len(pair) != 2:
            raise ValueError("Each batch item must be a 2-element (invoice_id, intent_hash) sequence")
        inv_id = _require_non_empty_str(pair[0], "invoice_id")
        ih = _require_non_empty_str(pair[1], "intent_hash")
        normalized.append([inv_id, ih])
    normalized.sort(key=lambda p: _utf16_sort_key(p[0]))
    return sha256_jcs({"preview_id": pvw_id, "items": normalized})


def action_hash(
    action: str,
    resource_id: str,
    payload_hash: str,
) -> str:
    """Compute step-up action_hash per docs/05-api/schemas.md §4."""
    act = _require_non_empty_str(action, "action")
    res_id = _require_non_empty_str(resource_id, "resource_id")
    ph = _require_non_empty_str(payload_hash, "payload_hash")
    return sha256_jcs(
        {
            "v": 1,
            "action": act,
            "resource_id": res_id,
            "payload_hash": ph,
        }
    )

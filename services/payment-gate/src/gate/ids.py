"""Prefixed Crockford Base32 ULID generator (matches PayMatch ID conventions)."""

from __future__ import annotations

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_base32(value: int, length: int) -> str:
    chars = ["0"] * length
    for i in range(length - 1, -1, -1):
        chars[i] = _ALPHABET[value & 31]
        value >>= 5
    return "".join(chars)


def new_id(prefix: str) -> str:
    """Return '<prefix>_<26-char Crockford Base32 ULID>'."""
    ts_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_bits = int.from_bytes(os.urandom(10), "big")
    return f"{prefix}_{_encode_base32(ts_ms, 10)}{_encode_base32(rand_bits, 16)}"

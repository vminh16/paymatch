# generated — do not edit

from __future__ import annotations

from enum import StrEnum


class EscrowStatus(StrEnum):
    pending = 'pending'
    held = 'held'
    released = 'released'
    refunded = 'refunded'
    failed = 'failed'

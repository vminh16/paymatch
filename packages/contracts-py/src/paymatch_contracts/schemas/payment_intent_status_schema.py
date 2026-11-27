# generated — do not edit

from __future__ import annotations

from enum import StrEnum


class PaymentIntentStatus(StrEnum):
    created = 'created'
    authorized = 'authorized'
    executing = 'executing'
    settled = 'settled'
    failed = 'failed'
    expired = 'expired'
    denied = 'denied'

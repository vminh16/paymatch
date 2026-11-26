# generated — do not edit

from __future__ import annotations

from enum import StrEnum


class NotificationKind(StrEnum):
    cross_alert_affected = 'cross_alert_affected'
    payment_failed = 'payment_failed'
    daily_summary = 'daily_summary'
    verification_needed = 'verification_needed'
    bot_review_needed = 'bot_review_needed'
    escrow_expiring = 'escrow_expiring'

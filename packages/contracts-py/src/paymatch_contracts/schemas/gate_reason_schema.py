# generated — do not edit

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Code(StrEnum):
    BLOCKED_INVOICE = 'BLOCKED_INVOICE'
    PAYEE_NOT_VERIFIED = 'PAYEE_NOT_VERIFIED'
    ABOVE_PER_INVOICE_LIMIT = 'ABOVE_PER_INVOICE_LIMIT'
    ABOVE_DAILY_LIMIT = 'ABOVE_DAILY_LIMIT'
    CROSS_ALERT_UNVERIFIED = 'CROSS_ALERT_UNVERIFIED'
    OFFICIAL_FRAUD_LIST = 'OFFICIAL_FRAUD_LIST'
    KILL_SWITCH = 'KILL_SWITCH'
    POLICY_UNAVAILABLE = 'POLICY_UNAVAILABLE'
    CHANNEL_NOT_ALLOWED = 'CHANNEL_NOT_ALLOWED'
    ALREADY_PAID = 'ALREADY_PAID'
    OUTSIDE_TIME_WINDOW = 'OUTSIDE_TIME_WINDOW'
    MANDATE_NOT_AUTO_PAY = 'MANDATE_NOT_AUTO_PAY'
    VENDOR_NOT_IN_AUTO_PAY = 'VENDOR_NOT_IN_AUTO_PAY'
    VENDOR_SUSPENDED = 'VENDOR_SUSPENDED'
    APPROVAL_MISSING = 'APPROVAL_MISSING'
    APPROVAL_STALE = 'APPROVAL_STALE'


class Layer(StrEnum):
    hard_rule = 'hard_rule'
    platform_policy = 'platform_policy'
    mandate = 'mandate'


class GateReason(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Code
    layer: Layer
    detail: str

# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema


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
        populate_by_name=True,
    )
    code: Code
    layer: Layer
    detail: str


class PaymentDeniedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    payment_intent_id: Annotated[str, Field(pattern='^pi_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    gate_reasons: Annotated[list[GateReason], Field(min_length=1)]


class PaymentDeniedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['payment.denied']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[PaymentDeniedData, Field(title='PaymentDeniedData')]

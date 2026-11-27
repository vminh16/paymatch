# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema


class Reason(StrEnum):
    AUTHORIZATION_TIMEOUT = 'AUTHORIZATION_TIMEOUT'
    CROSS_ALERT = 'CROSS_ALERT'
    INVOICE_REINVESTIGATED = 'INVOICE_REINVESTIGATED'
    OWNER_CANCELLED = 'OWNER_CANCELLED'


class PaymentExpiredData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    payment_intent_id: Annotated[str, Field(pattern='^pi_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    reason: Reason


class PaymentExpiredEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['payment.expired']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[PaymentExpiredData, Field(title='PaymentExpiredData')]

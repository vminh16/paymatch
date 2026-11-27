# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema


class InvoiceStatus(StrEnum):
    new = 'new'
    investigating = 'investigating'
    auto_pay_eligible = 'auto_pay_eligible'
    pending_approval = 'pending_approval'
    blocked = 'blocked'
    approved = 'approved'
    scheduled = 'scheduled'
    paying = 'paying'
    paid = 'paid'
    payment_failed = 'payment_failed'
    escrow_held = 'escrow_held'
    no_payment_due = 'no_payment_due'
    rejected = 'rejected'


class Severity(StrEnum):
    green = 'green'
    yellow = 'yellow'
    red = 'red'


class InvoiceStatusChangedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    from_: Annotated[InvoiceStatus, Field(alias='from')]
    to: InvoiceStatus
    severity: Severity | None


class InvoiceStatusChangedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['invoice.status_changed']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[InvoiceStatusChangedData, Field(title='InvoiceStatusChangedData')]

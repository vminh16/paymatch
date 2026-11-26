# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema

type MoneyVnd = Annotated[
    int,
    Field(
        description='Số tiền VND không âm (integer, đơn vị đồng).',
        ge=0,
        title='MoneyVnd',
    ),
]


class Channel(StrEnum):
    bank_transfer = 'bank_transfer'
    virtual_card = 'virtual_card'
    escrow = 'escrow'


class PaymentAuthorizedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    payment_intent_id: Annotated[str, Field(pattern='^pi_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    amount_vnd: MoneyVnd
    channel: Channel


class PaymentAuthorizedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['payment.authorized']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[PaymentAuthorizedData, Field(title='PaymentAuthorizedData')]

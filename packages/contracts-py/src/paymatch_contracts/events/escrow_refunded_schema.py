# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema


class Reason(StrEnum):
    EXPIRED = 'EXPIRED'
    ORDER_CANCELLED = 'ORDER_CANCELLED'


class EscrowRefundedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    escrow_id: Annotated[str, Field(pattern='^esc_[0-9A-HJKMNP-TV-Z]{26}$')]
    source_invoice_id: Annotated[
        str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    reason: Reason


class EscrowRefundedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['escrow.refunded']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[EscrowRefundedData, Field(title='EscrowRefundedData')]

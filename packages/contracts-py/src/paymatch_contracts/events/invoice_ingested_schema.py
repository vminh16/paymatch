# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema


class InvoiceSource(StrEnum):
    email = 'email'
    upload = 'upload'
    bill_pay = 'bill_pay'
    scenario = 'scenario'


class InvoiceType(StrEnum):
    goods = 'goods'
    utility = 'utility'
    software = 'software'


class InvoiceIngestedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    source: InvoiceSource
    invoice_type: InvoiceType
    duplicate_of: Annotated[str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]


class InvoiceIngestedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['invoice.ingested']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[InvoiceIngestedData, Field(title='InvoiceIngestedData')]

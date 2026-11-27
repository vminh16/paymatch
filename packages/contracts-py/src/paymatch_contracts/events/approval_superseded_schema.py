# generated — do not edit

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema


class Reason(Enum):
    NEW_JOB = 'NEW_JOB'
    NEW_SYSTEM_FINDING = 'NEW_SYSTEM_FINDING'
    PAYMENT_FAILED = 'PAYMENT_FAILED'
    PAYMENT_DENIED = 'PAYMENT_DENIED'
    OWNER_CANCELLED = 'OWNER_CANCELLED'
    NoneType_None = None


class ApprovalSupersededData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    approval_id: Annotated[str, Field(pattern='^apv_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_id: Annotated[str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    purchase_order_id: Annotated[
        str | None, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    method: approval_created_schema.ApprovalMethod
    reason: Reason | None = None


class ApprovalSupersededEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['approval.superseded']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[ApprovalSupersededData, Field(title='ApprovalSupersededData')]

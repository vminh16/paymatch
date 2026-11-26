# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

type Timestamp = Annotated[
    AwareDatetime,
    Field(
        description='Thời điểm RFC 3339 có múi giờ (ví dụ 2026-11-26T09:15:00+07:00).',
        title='Timestamp',
    ),
]


class ApprovalMethod(StrEnum):
    single = 'single'
    bulk = 'bulk'
    mandate = 'mandate'


class ApprovalCreatedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    approval_id: Annotated[str, Field(pattern='^apv_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_id: Annotated[str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    purchase_order_id: Annotated[
        str | None, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    method: ApprovalMethod
    reason: str | None = None


class ApprovalCreatedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['approval.created']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[ApprovalCreatedData, Field(title='ApprovalCreatedData')]

# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import approval_method_schema, timestamp_schema


class Status(StrEnum):
    active = 'active'
    superseded = 'superseded'
    consumed = 'consumed'


class ApprovalSummary(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    approval_id: Annotated[str, Field(pattern='^apv_[0-9A-HJKMNP-TV-Z]{26}$')]
    method: approval_method_schema.ApprovalMethod
    status: Status
    approver_user_id: Annotated[
        str | None, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    created_at: timestamp_schema.Timestamp

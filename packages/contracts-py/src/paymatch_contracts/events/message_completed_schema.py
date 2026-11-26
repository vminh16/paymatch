# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema


class Status(StrEnum):
    completed = 'completed'
    failed = 'failed'


class MessageCompletedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    conversation_id: Annotated[str, Field(pattern='^cnv_[0-9A-HJKMNP-TV-Z]{26}$')]
    message_id: Annotated[str, Field(pattern='^cmg_[0-9A-HJKMNP-TV-Z]{26}$')]
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    status: Status


class MessageCompletedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['message.completed']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[MessageCompletedData, Field(title='MessageCompletedData')]

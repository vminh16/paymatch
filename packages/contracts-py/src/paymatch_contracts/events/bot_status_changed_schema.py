# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema


class BotStatus(StrEnum):
    draft = 'draft'
    pending_review = 'pending_review'
    active = 'active'
    disabled = 'disabled'
    archived = 'archived'


class BotStatusChangedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    bot_id: Annotated[str, Field(min_length=1)]
    version: Annotated[int, Field(ge=1)]
    from_: Annotated[BotStatus | None, Field(alias='from')]
    to: BotStatus


class BotStatusChangedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['bot.status_changed']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[BotStatusChangedData, Field(title='BotStatusChangedData')]

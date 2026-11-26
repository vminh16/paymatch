# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema

type UserId = Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]


class NotificationKind(StrEnum):
    cross_alert_affected = 'cross_alert_affected'
    payment_failed = 'payment_failed'
    daily_summary = 'daily_summary'
    verification_needed = 'verification_needed'
    bot_review_needed = 'bot_review_needed'
    escrow_expiring = 'escrow_expiring'


class NotificationCreatedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    notification_id: Annotated[str, Field(pattern='^ntf_[0-9A-HJKMNP-TV-Z]{26}$')]
    kind: NotificationKind
    user_ids: Annotated[list[UserId], Field(min_length=1)]


class NotificationCreatedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['notification.created']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[NotificationCreatedData, Field(title='NotificationCreatedData')]

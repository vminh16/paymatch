# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import notification_kind_schema, timestamp_schema

type InvoiceId = Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]


class Notification(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    notification_id: Annotated[str, Field(pattern='^ntf_[0-9A-HJKMNP-TV-Z]{26}$')]
    kind: notification_kind_schema.NotificationKind
    invoice_ids: list[InvoiceId]
    title: str
    body: str
    read_at: timestamp_schema.Timestamp | None
    created_at: timestamp_schema.Timestamp

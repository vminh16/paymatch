# generated — do not edit

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema


class CrossAlertWithdrawnData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    cross_alert_id: Annotated[str, Field(pattern='^cxa_[0-9A-HJKMNP-TV-Z]{26}$')]


class CrossAlertWithdrawnEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['cross_alert.withdrawn']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[CrossAlertWithdrawnData, Field(title='CrossAlertWithdrawnData')]

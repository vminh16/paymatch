# generated — do not edit

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema, kill_switch_engaged_schema


class KillSwitchReleasedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    kill_switch_id: Annotated[str, Field(pattern='^ksw_[0-9A-HJKMNP-TV-Z]{26}$')]
    scope: kill_switch_engaged_schema.KillSwitchScope
    target_id: str | None


class KillSwitchReleasedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['kill_switch.released']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[KillSwitchReleasedData, Field(title='KillSwitchReleasedData')]

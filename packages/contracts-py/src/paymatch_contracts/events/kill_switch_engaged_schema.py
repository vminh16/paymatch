# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema


class KillSwitchScope(StrEnum):
    indicator = 'indicator'
    tenant = 'tenant'
    bot = 'bot'
    tool = 'tool'
    auto_pay_global = 'auto_pay_global'


class KillSwitchEngagedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    kill_switch_id: Annotated[str, Field(pattern='^ksw_[0-9A-HJKMNP-TV-Z]{26}$')]
    scope: KillSwitchScope
    target_id: str | None


class KillSwitchEngagedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['kill_switch.engaged']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[KillSwitchEngagedData, Field(title='KillSwitchEngagedData')]

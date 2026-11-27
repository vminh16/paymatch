# generated — do not edit

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema, cross_alert_published_schema


class HardBlockAppliedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    hard_block_id: Annotated[str, Field(pattern='^hbk_[0-9A-HJKMNP-TV-Z]{26}$')]
    indicators: Annotated[
        list[cross_alert_published_schema.IndicatorRef], Field(min_length=1)
    ]


class HardBlockAppliedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['hard_block.applied']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[HardBlockAppliedData, Field(title='HardBlockAppliedData')]

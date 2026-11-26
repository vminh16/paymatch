# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema, cross_alert_published_schema


class FlaggedIndicatorItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    kind: cross_alert_published_schema.IndicatorKind
    value_hash: Annotated[str, Field(min_length=1)]


class Source(StrEnum):
    finding = 'finding'
    rail = 'rail'


class IndicatorFlaggedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    indicators: Annotated[list[FlaggedIndicatorItem], Field(min_length=1)]
    reason_codes: list[cross_alert_published_schema.ReasonCode]
    source: Source
    source_ref: Annotated[
        str,
        Field(
            description='Mã tham chiếu mờ (opaque), không lộ id hóa đơn hoặc Finding của tenant.',
            min_length=1,
        ),
    ]


class IndicatorFlaggedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['indicator.flagged']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[IndicatorFlaggedData, Field(title='IndicatorFlaggedData')]

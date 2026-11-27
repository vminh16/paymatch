# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import indicator_kind_schema


class IndicatorRef(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    kind: indicator_kind_schema.IndicatorKind
    value_hash: Annotated[str, Field(pattern='^[0-9a-f]{64}$')]

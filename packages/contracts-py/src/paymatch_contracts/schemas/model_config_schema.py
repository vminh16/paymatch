# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Purpose(StrEnum):
    bot = 'bot'
    brief = 'brief'


class ModelConfig(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    purpose: Purpose
    primary_model: Annotated[str, Field(min_length=1)]
    fallback_model: Annotated[str, Field(min_length=1)]
    max_tokens: Annotated[int, Field(ge=1)]
    timeout_s: Annotated[int, Field(ge=1)]
    etag: Annotated[str, Field(min_length=1)]

# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from . import timestamp_schema


class Result(StrEnum):
    confirmed = 'confirmed'
    not_reachable = 'not_reachable'
    denied_by_vendor = 'denied_by_vendor'


class Verification(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    called_phone_on_file: Literal[True]
    result: Result
    note: str | None = None
    at: timestamp_schema.Timestamp

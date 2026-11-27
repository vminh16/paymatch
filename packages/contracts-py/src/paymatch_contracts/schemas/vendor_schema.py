# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import timestamp_schema


class Status(StrEnum):
    active = 'active'
    inactive = 'inactive'


class Vendor(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor_id: Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    name: Annotated[str, Field(min_length=1)]
    tax_id: Annotated[str, Field(min_length=1)]
    phone_on_file_masked: Annotated[str, Field(min_length=1)]
    status: Status
    created_at: timestamp_schema.Timestamp

# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from . import provenance_schema


class Code(StrEnum):
    UPSTREAM_UNAVAILABLE = 'UPSTREAM_UNAVAILABLE'
    UPSTREAM_TIMEOUT = 'UPSTREAM_TIMEOUT'
    NOT_FOUND = 'NOT_FOUND'
    INVALID_INPUT = 'INVALID_INPUT'


class ToolResultError(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    code: Code
    detail: str


class ToolResult(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    data: dict[str, Any]
    provenance: provenance_schema.Provenance
    evidence_ref: Annotated[str, Field(pattern='^tcl_[0-9A-HJKMNP-TV-Z]{26}$')]
    error: ToolResultError | None

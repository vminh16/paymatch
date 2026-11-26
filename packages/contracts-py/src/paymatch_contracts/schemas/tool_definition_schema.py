# generated — do not edit

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import provenance_schema


class ToolDefinition(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    tool_id: Annotated[str, Field(pattern='^[a-z][a-z0-9_]*$')]
    description: Annotated[str, Field(min_length=1)]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    default_provenance: provenance_schema.Provenance
    scope: Literal['tenant']

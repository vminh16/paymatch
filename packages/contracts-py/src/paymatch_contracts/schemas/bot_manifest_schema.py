# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import invoice_type_schema, task_type_schema

type Skill = Annotated[str, Field(min_length=1)]


type Tool = Annotated[str, Field(pattern='^[a-z][a-z0-9_]*$')]


class BotManifestTriggers(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_types: list[invoice_type_schema.InvoiceType]


class BotManifest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    id: Annotated[str, Field(pattern='^[a-z][a-z0-9-]*$')]
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str, Field(min_length=1)]
    skills: Annotated[list[Skill], Field(min_length=1)]
    tools: list[Tool]
    task_types: Annotated[
        list[task_type_schema.TaskType] | None, Field(min_length=1)
    ] = None
    triggers: Annotated[BotManifestTriggers, Field(title='BotManifestTriggers')]
    required_for: list[invoice_type_schema.InvoiceType] | None = None

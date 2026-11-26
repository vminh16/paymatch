# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import reason_code_schema


class BotAnswerFact(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    key: Annotated[str, Field(min_length=1)]
    value: str | float
    tool_call_id: Annotated[str, Field(pattern='^tcl_[0-9A-HJKMNP-TV-Z]{26}$')]
    verified: bool


class BotAnswer(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    bot_id: Annotated[str, Field(min_length=1)]
    facts: list[BotAnswerFact]
    reason_codes: list[reason_code_schema.ReasonCode]

# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ChannelHint(StrEnum):
    email = 'email'
    chat = 'chat'


type CitedLine = Annotated[str, Field(pattern='^lin_[0-9A-HJKMNP-TV-Z]{26}$')]


class AdjustmentRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    adjustment_request_id: Annotated[str, Field(pattern='^adj_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    to_vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    channel_hint: ChannelHint
    subject: str
    body: str
    cited_lines: list[CitedLine]

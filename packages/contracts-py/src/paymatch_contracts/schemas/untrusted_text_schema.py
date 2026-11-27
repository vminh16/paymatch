# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Source(StrEnum):
    invoice_xml = 'invoice_xml'
    email_body = 'email_body'
    chat_message = 'chat_message'
    bot_reason = 'bot_reason'
    ocr = 'ocr'


class UntrustedText(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    text: str
    provenance: Literal['untrusted']
    source: Source

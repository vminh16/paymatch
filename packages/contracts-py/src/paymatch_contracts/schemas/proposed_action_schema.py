# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Kind(StrEnum):
    open_invoice = 'open_invoice'
    open_approval_queue = 'open_approval_queue'
    preview_bulk_approval = 'preview_bulk_approval'
    open_vendor = 'open_vendor'
    open_account_change = 'open_account_change'
    reinvestigate_invoice = 'reinvestigate_invoice'


type TargetId = Annotated[str, Field(min_length=1)]


class ProposedAction(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    kind: Kind
    target_ids: list[TargetId]
    label: Annotated[str, Field(min_length=1)]

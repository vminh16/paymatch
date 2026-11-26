# generated — do not edit

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Page(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    items: list[Any]
    next_cursor: str | None

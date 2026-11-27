# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    owner = 'owner'
    accountant = 'accountant'
    store_manager = 'store_manager'


type StoreId = Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]


class User(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    user_id: Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
    name: str
    role: Role
    store_ids: list[StoreId]

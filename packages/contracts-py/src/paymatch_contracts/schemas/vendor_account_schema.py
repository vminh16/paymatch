# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import timestamp_schema, vendor_account_status_schema


class Kind(StrEnum):
    bank_account = 'bank_account'
    card_merchant = 'card_merchant'


class VendorAccount(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor_account_id: Annotated[str, Field(pattern='^vac_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_id: Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    kind: Kind
    bank_code: str | None
    bank_name: str | None
    account_number_masked: str | None
    merchant_id: str | None
    account_name: Annotated[str, Field(min_length=1)]
    status: vendor_account_status_schema.VendorAccountStatus
    verified_at: timestamp_schema.Timestamp | None

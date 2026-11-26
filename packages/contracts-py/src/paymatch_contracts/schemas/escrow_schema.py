# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import (
    escrow_status_schema,
    local_date_schema,
    money_vnd_schema,
    timestamp_schema,
)


class Escrow(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    escrow_id: Annotated[str, Field(pattern='^esc_[0-9A-HJKMNP-TV-Z]{26}$')]
    purchase_order_id: Annotated[str, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_account_id: Annotated[str, Field(pattern='^vac_[0-9A-HJKMNP-TV-Z]{26}$')]
    amount_vnd: money_vnd_schema.MoneyVnd
    status: escrow_status_schema.EscrowStatus
    source_invoice_id: Annotated[
        str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    release_invoice_id: Annotated[
        str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    goods_receipt_id: Annotated[
        str | None, Field(pattern='^grn_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    expires_on: local_date_schema.LocalDate
    created_at: timestamp_schema.Timestamp
    released_at: timestamp_schema.Timestamp | None
    refunded_at: timestamp_schema.Timestamp | None

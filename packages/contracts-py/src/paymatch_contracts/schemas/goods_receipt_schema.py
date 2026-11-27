# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import decimal_schema, timestamp_schema


class GoodsReceiptLine(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    sku: Annotated[str, Field(min_length=1)]
    quantity_received: decimal_schema.Decimal


class GoodsReceipt(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    goods_receipt_id: Annotated[str, Field(pattern='^grn_[0-9A-HJKMNP-TV-Z]{26}$')]
    purchase_order_id: Annotated[str, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')]
    store_id: Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]
    lines: Annotated[list[GoodsReceiptLine], Field(min_length=1)]
    confirmed_by: Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
    confirmed_at: timestamp_schema.Timestamp

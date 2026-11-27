# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import decimal_schema, money_vnd_schema, timestamp_schema


class PurchaseOrderLine(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    sku: Annotated[str, Field(min_length=1)]
    quantity: Annotated[
        decimal_schema.Decimal, Field(description='Số lượng theo đơn vị `pack_spec`.')
    ]
    unit_price: Annotated[
        decimal_schema.Decimal,
        Field(description='Giá hợp đồng một `pack_spec`, CHƯA VAT.'),
    ]


class Status(StrEnum):
    open = 'open'
    received = 'received'
    closed = 'closed'
    cancelled = 'cancelled'


class PurchaseOrder(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    purchase_order_id: Annotated[str, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_id: Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    store_id: Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]
    lines: Annotated[list[PurchaseOrderLine], Field(min_length=1)]
    total_vnd: Annotated[
        money_vnd_schema.MoneyVnd,
        Field(description='Tổng PO GỒM VAT (so được với `total_vnd` của hóa đơn).'),
    ]
    status: Status
    created_by: Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
    created_at: timestamp_schema.Timestamp

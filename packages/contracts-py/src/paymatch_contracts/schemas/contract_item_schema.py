# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import decimal_schema


class ContractItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    item_id: Annotated[str, Field(pattern='^itm_[0-9A-HJKMNP-TV-Z]{26}$')]
    sku: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    base_unit: Annotated[str, Field(min_length=1)]
    pack_spec: Annotated[str, Field(min_length=1)]
    pack_qty: decimal_schema.Decimal
    unit_price: decimal_schema.Decimal
    vat_rate: Annotated[str, Field(min_length=1)]

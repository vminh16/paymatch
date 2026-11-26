# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import decimal_schema, signed_money_vnd_schema, untrusted_text_schema


class Kind(StrEnum):
    goods_service = 'goods_service'
    promotion = 'promotion'
    trade_discount = 'trade_discount'
    note = 'note'
    special_goods = 'special_goods'


class InvoiceLine(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    line_id: Annotated[str, Field(pattern='^lin_[0-9A-HJKMNP-TV-Z]{26}$')]
    position: Annotated[int, Field(ge=1)]
    kind: Kind
    item_code: untrusted_text_schema.UntrustedText | None
    name: untrusted_text_schema.UntrustedText
    unit: untrusted_text_schema.UntrustedText | None
    quantity: decimal_schema.Decimal | None
    unit_price: decimal_schema.Decimal | None
    discount_vnd: signed_money_vnd_schema.SignedMoneyVnd | None
    amount_vnd: signed_money_vnd_schema.SignedMoneyVnd | None
    vat_rate: str | None
    arithmetic_ok: bool

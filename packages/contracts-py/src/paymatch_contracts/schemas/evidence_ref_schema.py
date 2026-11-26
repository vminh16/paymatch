# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Kind(StrEnum):
    invoice_line = 'invoice_line'
    invoice_document = 'invoice_document'
    message = 'message'
    contract_item = 'contract_item'
    purchase_order = 'purchase_order'
    goods_receipt = 'goods_receipt'
    tool_call = 'tool_call'
    vendor_account = 'vendor_account'
    utility_reading = 'utility_reading'


class EvidenceRef(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    kind: Kind
    ref_id: Annotated[
        str,
        Field(pattern='^(lin|doc|msg|itm|po|grn|tcl|vac|urd)_[0-9A-HJKMNP-TV-Z]{26}$'),
    ]
    tool_call_id: Annotated[str, Field(pattern='^tcl_[0-9A-HJKMNP-TV-Z]{26}$')]

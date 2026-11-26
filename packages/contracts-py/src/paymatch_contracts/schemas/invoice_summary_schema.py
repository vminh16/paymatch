# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import (
    invoice_status_schema,
    invoice_type_schema,
    local_date_schema,
    reason_code_schema,
    severity_schema,
    signed_money_vnd_schema,
    timestamp_schema,
)


class InvoiceSummary(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    store_id: Annotated[str | None, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_name: Annotated[
        str | None,
        Field(
            description='Chỉ từ vendor registry; null khi NCC chưa có (UI hiển thị untrusted.seller_name).'
        ),
    ]
    seller_tax_id: str
    symbol: Annotated[str, Field(description='KHMSHDon + KHHDon, ví dụ 1C26TTN.')]
    number: Annotated[str, Field(description='SHDon.')]
    issued_on: local_date_schema.LocalDate | None
    invoice_type: invoice_type_schema.InvoiceType
    total_vnd: Annotated[
        signed_money_vnd_schema.SignedMoneyVnd | None,
        Field(
            description='Null với PDF/ảnh chưa nhập tay; có thể âm trên hóa đơn điều chỉnh (TCHDon 2/4).'
        ),
    ]
    status: invoice_status_schema.InvoiceStatus
    severity: severity_schema.Severity | None
    reason_codes: list[reason_code_schema.ReasonCode]
    verification_required: bool
    due_on: local_date_schema.LocalDate | None
    scheduled_for: local_date_schema.LocalDate | None
    updated_at: timestamp_schema.Timestamp

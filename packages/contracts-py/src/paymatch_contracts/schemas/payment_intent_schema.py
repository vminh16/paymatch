# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import (
    channel_schema,
    gate_reason_schema,
    money_vnd_schema,
    payment_intent_status_schema,
    timestamp_schema,
)


class PaymentIntentRail(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    rail_txn_id: str | None
    failure_code: str | None


class PaymentIntent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    payment_intent_id: Annotated[str, Field(pattern='^pi_[0-9A-HJKMNP-TV-Z]{26}$')]
    tenant_id: Annotated[str, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_id: Annotated[str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    purchase_order_id: Annotated[
        str | None, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    intent_hash: Annotated[str, Field(pattern='^[0-9a-f]{64}$')]
    approval_id: Annotated[str, Field(pattern='^apv_[0-9A-HJKMNP-TV-Z]{26}$')]
    payee_account_id: Annotated[str, Field(pattern='^vac_[0-9A-HJKMNP-TV-Z]{26}$')]
    channel: channel_schema.Channel
    amount_vnd: money_vnd_schema.MoneyVnd
    status: payment_intent_status_schema.PaymentIntentStatus
    gate_reasons: list[gate_reason_schema.GateReason]
    rail: Annotated[PaymentIntentRail, Field(title='PaymentIntentRail')]
    transfer_memo: Annotated[
        str, Field(description="Nội dung chuyển khoản chuẩn 'MST · ký hiệu · số' (D2).")
    ]
    authorized_at: timestamp_schema.Timestamp | None
    executed_at: timestamp_schema.Timestamp | None
    settled_at: timestamp_schema.Timestamp | None
    expires_at: timestamp_schema.Timestamp | None
    created_at: timestamp_schema.Timestamp

# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import channel_schema, gate_reason_schema, money_vnd_schema, timestamp_schema


class ApprovalPreviewPayee(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    vendor_account_id: Annotated[str, Field(pattern='^vac_[0-9A-HJKMNP-TV-Z]{26}$')]
    bank_name: str | None
    account_number_masked: str | None
    merchant_id: str | None
    account_name: str


class GateDecision(StrEnum):
    ALLOW = 'ALLOW'
    REQUIRE_APPROVAL = 'REQUIRE_APPROVAL'
    DENY = 'DENY'


class AllowedMethod(StrEnum):
    single = 'single'
    bulk = 'bulk'


class ApprovalPreview(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    intent_hash: Annotated[str, Field(pattern='^[0-9a-f]{64}$')]
    payee: Annotated[
        ApprovalPreviewPayee | None,
        Field(
            description='Từ vendor registry; null chỉ khi gate_decision = DENY và chưa có TK trong registry.'
        ),
    ]
    amount_vnd: money_vnd_schema.MoneyVnd
    channel: channel_schema.Channel
    gate_decision: GateDecision
    allowed_methods: list[AllowedMethod]
    verification_required: bool
    phone_on_file_masked: Annotated[
        str | None,
        Field(
            description='Chỉ khác null khi verification_required = true; SĐT lấy từ vendor registry.'
        ),
    ]
    gate_reasons: list[gate_reason_schema.GateReason]
    action_hash: Annotated[str, Field(pattern='^[0-9a-f]{64}$')]
    expires_at: timestamp_schema.Timestamp

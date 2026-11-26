# generated — do not edit

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import (
    channel_schema,
    invoice_type_schema,
    mandate_mode_schema,
    money_vnd_schema,
    reason_code_schema,
    timestamp_schema,
)

type AutoPayVendorId = Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]


class MandateChannelRule(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_type: invoice_type_schema.InvoiceType
    channel: channel_schema.Channel


class AutoPayWindow(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    start: Annotated[str, Field(pattern='^([01]\\d|2[0-3]):[0-5]\\d$')]
    end: Annotated[str, Field(pattern='^([01]\\d|2[0-3]):[0-5]\\d$')]


class MandateLimits(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    per_invoice_vnd: money_vnd_schema.MoneyVnd
    per_day_vnd: money_vnd_schema.MoneyVnd


class BulkApprovableRule(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    reason_codes: Annotated[list[reason_code_schema.ReasonCode], Field(min_length=1)]
    max_amount_vnd: money_vnd_schema.MoneyVnd


class MandateSignature(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    by_user_id: Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
    method: Annotated[str, Field(min_length=1)]
    auth_proof_jti: Annotated[str, Field(min_length=1)]
    at: timestamp_schema.Timestamp


class Mandate(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    mandate_id: Annotated[str, Field(pattern='^man_[0-9A-HJKMNP-TV-Z]{26}$')]
    version: Annotated[int, Field(ge=1)]
    mode: mandate_mode_schema.MandateMode
    limits: Annotated[MandateLimits, Field(title='MandateLimits')]
    auto_pay_vendor_ids: list[AutoPayVendorId]
    channel_rules: list[MandateChannelRule]
    bulk_approvable: list[BulkApprovableRule]
    auto_pay_window: Annotated[AutoPayWindow, Field(title='AutoPayWindow')]
    signed: Annotated[MandateSignature, Field(title='MandateSignature')]
    created_at: timestamp_schema.Timestamp

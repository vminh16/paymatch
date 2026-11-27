# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import approval_created_schema


class IndicatorKind(StrEnum):
    account_hash = 'account_hash'
    tax_id = 'tax_id'
    phone = 'phone'
    card_id = 'card_id'
    merchant_id = 'merchant_id'


class ReasonCode(StrEnum):
    OK = 'OK'
    PRICE_ABOVE_CONTRACT = 'PRICE_ABOVE_CONTRACT'
    PACK_SIZE_CHANGED = 'PACK_SIZE_CHANGED'
    QUANTITY_ABOVE_NORM = 'QUANTITY_ABOVE_NORM'
    NO_GOODS_RECEIPT = 'NO_GOODS_RECEIPT'
    DUPLICATE_INVOICE = 'DUPLICATE_INVOICE'
    PAYEE_CHANGE_REQUEST = 'PAYEE_CHANGE_REQUEST'
    PERSONAL_ACCOUNT = 'PERSONAL_ACCOUNT'
    HIDDEN_INSTRUCTION = 'HIDDEN_INSTRUCTION'
    URGENCY_PRESSURE = 'URGENCY_PRESSURE'
    CROSS_ALERT_HIT = 'CROSS_ALERT_HIT'
    OFFICIAL_FRAUD_LIST = 'OFFICIAL_FRAUD_LIST'
    TAX_RISK_LIST = 'TAX_RISK_LIST'
    MST_INACTIVE = 'MST_INACTIVE'
    INVOICE_NOT_FOUND_ON_PORTAL = 'INVOICE_NOT_FOUND_ON_PORTAL'
    VAT_DEDUCTION_RISK = 'VAT_DEDUCTION_RISK'
    UTILITY_OUT_OF_RANGE = 'UTILITY_OUT_OF_RANGE'
    OVER_LIMIT = 'OVER_LIMIT'
    LOW_BALANCE = 'LOW_BALANCE'
    NON_XML_SOURCE = 'NON_XML_SOURCE'
    AMOUNT_MISMATCH = 'AMOUNT_MISMATCH'
    UNKNOWN_VENDOR = 'UNKNOWN_VENDOR'
    BOT_TIMEOUT = 'BOT_TIMEOUT'
    BOT_INVALID_OUTPUT = 'BOT_INVALID_OUTPUT'
    BOT_NOT_RUN = 'BOT_NOT_RUN'
    BOT_DISABLED = 'BOT_DISABLED'
    CUSTOM = 'CUSTOM'


class IndicatorRef(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    kind: IndicatorKind
    value_hash: Annotated[str, Field(pattern='^[0-9a-f]{64}$')]


class CrossAlertPublishedData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    cross_alert_id: Annotated[str, Field(pattern='^cxa_[0-9A-HJKMNP-TV-Z]{26}$')]
    indicators: Annotated[list[IndicatorRef], Field(min_length=1)]
    reason_codes: Annotated[list[ReasonCode], Field(min_length=1)]


class CrossAlertPublishedEvent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['cross_alert.published']
    schema_version: Annotated[int, Field(ge=1)]
    occurred_at: approval_created_schema.Timestamp
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    trace_id: str | None
    data: Annotated[CrossAlertPublishedData, Field(title='CrossAlertPublishedData')]

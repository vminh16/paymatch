# generated — do not edit

from __future__ import annotations

from enum import Enum, StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import (
    approval_method_schema,
    channel_schema,
    money_vnd_schema,
    timestamp_schema,
    verification_schema,
)


class Status(StrEnum):
    active = 'active'
    superseded = 'superseded'
    consumed = 'consumed'


class SupersededReason(Enum):
    NEW_JOB = 'NEW_JOB'
    NEW_SYSTEM_FINDING = 'NEW_SYSTEM_FINDING'
    PAYMENT_FAILED = 'PAYMENT_FAILED'
    PAYMENT_DENIED = 'PAYMENT_DENIED'
    OWNER_CANCELLED = 'OWNER_CANCELLED'
    NoneType_None = None


class Approval(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    approval_id: Annotated[str, Field(pattern='^apv_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_id: Annotated[str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    purchase_order_id: Annotated[
        str | None, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    source_invoice_id: Annotated[
        str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    job_id: Annotated[str | None, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    status: Status
    amount_vnd: money_vnd_schema.MoneyVnd
    payee_account_id: Annotated[str, Field(pattern='^vac_[0-9A-HJKMNP-TV-Z]{26}$')]
    channel: channel_schema.Channel
    intent_hash: Annotated[str, Field(pattern='^[0-9a-f]{64}$')]
    approver_user_id: Annotated[
        str | None, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    method: approval_method_schema.ApprovalMethod
    mandate_version: Annotated[int | None, Field(ge=1)]
    bulk_batch_id: Annotated[str | None, Field(pattern='^abt_[0-9A-HJKMNP-TV-Z]{26}$')]
    verification: verification_schema.Verification | None
    auth_proof_jti: str | None
    created_at: timestamp_schema.Timestamp
    superseded_at: timestamp_schema.Timestamp | None
    superseded_reason: SupersededReason | None

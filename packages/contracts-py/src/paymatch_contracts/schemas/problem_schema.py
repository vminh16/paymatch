# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import AnyUrl, BaseModel, ConfigDict, Field

from . import (
    escrow_status_schema,
    gate_reason_schema,
    invoice_status_schema,
    job_status_schema,
    payment_intent_status_schema,
)


class Code(StrEnum):
    VALIDATION_FAILED = 'VALIDATION_FAILED'
    UNAUTHENTICATED = 'UNAUTHENTICATED'
    TOKEN_EXPIRED = 'TOKEN_EXPIRED'
    FORBIDDEN = 'FORBIDDEN'
    ROLE_NOT_ALLOWED = 'ROLE_NOT_ALLOWED'
    TOOL_NOT_GRANTED = 'TOOL_NOT_GRANTED'
    TENANT_MISMATCH = 'TENANT_MISMATCH'
    TICKET_REQUIRED = 'TICKET_REQUIRED'
    STEP_UP_REQUIRED = 'STEP_UP_REQUIRED'
    STEP_UP_INVALID = 'STEP_UP_INVALID'
    NOT_FOUND = 'NOT_FOUND'
    INVALID_STATE = 'INVALID_STATE'
    INTENT_HASH_MISMATCH = 'INTENT_HASH_MISMATCH'
    DUPLICATE_INVOICE = 'DUPLICATE_INVOICE'
    IDEMPOTENCY_KEY_REUSED = 'IDEMPOTENCY_KEY_REUSED'
    LEASE_LOST = 'LEASE_LOST'
    MAKER_CHECKER_VIOLATION = 'MAKER_CHECKER_VIOLATION'
    PRECONDITION_FAILED = 'PRECONDITION_FAILED'
    GATE_DENIED = 'GATE_DENIED'
    MANDATE_ABOVE_PLATFORM_CEILING = 'MANDATE_ABOVE_PLATFORM_CEILING'
    BOT_MANIFEST_INVALID = 'BOT_MANIFEST_INVALID'
    XML_UNPARSEABLE = 'XML_UNPARSEABLE'
    KILL_SWITCH_ACTIVE = 'KILL_SWITCH_ACTIVE'
    RATE_LIMITED = 'RATE_LIMITED'
    UPSTREAM_UNAVAILABLE = 'UPSTREAM_UNAVAILABLE'
    UPSTREAM_TIMEOUT = 'UPSTREAM_TIMEOUT'


class ProblemErrorItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    field: str
    code: str
    detail: str | None = None


class Problem(BaseModel):
    model_config = ConfigDict(
        extra='allow',
        populate_by_name=True,
    )
    type: AnyUrl
    title: str
    status: Annotated[int, Field(ge=400, le=599)]
    code: Code
    detail: str | None = None
    instance: str | None = None
    errors: list[ProblemErrorItem] | None = None
    current_status: (
        invoice_status_schema.InvoiceStatus
        | payment_intent_status_schema.PaymentIntentStatus
        | escrow_status_schema.EscrowStatus
        | job_status_schema.JobStatus
        | None
    ) = None
    existing_invoice_id: Annotated[
        str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')
    ] = None
    gate_reasons: list[gate_reason_schema.GateReason] | None = None

# generated — do not edit

from __future__ import annotations

from datetime import date as date_aliased
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AnyUrl, AwareDatetime, BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    status: Literal['ok']


class ReadyResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    status: Literal['ready']


class GateDecision(StrEnum):
    ALLOW = 'ALLOW'
    REQUIRE_APPROVAL = 'REQUIRE_APPROVAL'
    DENY = 'DENY'


class PaymentIntentStatus(StrEnum):
    created = 'created'
    authorized = 'authorized'
    executing = 'executing'
    settled = 'settled'
    failed = 'failed'
    expired = 'expired'
    denied = 'denied'


class EscrowStatus(StrEnum):
    pending = 'pending'
    held = 'held'
    released = 'released'
    refunded = 'refunded'
    failed = 'failed'


class EvaluateInvoiceRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )


type MoneyVnd = Annotated[
    int,
    Field(
        description='Số tiền VND không âm (integer, đơn vị đồng).',
        ge=0,
        title='MoneyVnd',
    ),
]


class AllowedMethod(StrEnum):
    single = 'single'
    bulk = 'bulk'


class Channel(StrEnum):
    bank_transfer = 'bank_transfer'
    virtual_card = 'virtual_card'
    escrow = 'escrow'


class Code(StrEnum):
    BLOCKED_INVOICE = 'BLOCKED_INVOICE'
    PAYEE_NOT_VERIFIED = 'PAYEE_NOT_VERIFIED'
    ABOVE_PER_INVOICE_LIMIT = 'ABOVE_PER_INVOICE_LIMIT'
    ABOVE_DAILY_LIMIT = 'ABOVE_DAILY_LIMIT'
    CROSS_ALERT_UNVERIFIED = 'CROSS_ALERT_UNVERIFIED'
    OFFICIAL_FRAUD_LIST = 'OFFICIAL_FRAUD_LIST'
    KILL_SWITCH = 'KILL_SWITCH'
    POLICY_UNAVAILABLE = 'POLICY_UNAVAILABLE'
    CHANNEL_NOT_ALLOWED = 'CHANNEL_NOT_ALLOWED'
    ALREADY_PAID = 'ALREADY_PAID'
    OUTSIDE_TIME_WINDOW = 'OUTSIDE_TIME_WINDOW'
    MANDATE_NOT_AUTO_PAY = 'MANDATE_NOT_AUTO_PAY'
    VENDOR_NOT_IN_AUTO_PAY = 'VENDOR_NOT_IN_AUTO_PAY'
    VENDOR_SUSPENDED = 'VENDOR_SUSPENDED'
    APPROVAL_MISSING = 'APPROVAL_MISSING'
    APPROVAL_STALE = 'APPROVAL_STALE'


class Layer(StrEnum):
    hard_rule = 'hard_rule'
    platform_policy = 'platform_policy'
    mandate = 'mandate'


class GateReason(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    code: Code
    layer: Layer
    detail: str


type Timestamp = Annotated[
    AwareDatetime,
    Field(
        description='Thời điểm RFC 3339 có múi giờ (ví dụ 2026-11-26T09:15:00+07:00).',
        title='Timestamp',
    ),
]


type LocalDate = Annotated[
    date_aliased,
    Field(
        description='Ngày theo giờ Việt Nam, định dạng YYYY-MM-DD.', title='LocalDate'
    ),
]


class CreatePaymentIntentRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    approval_id: Annotated[str, Field(pattern='^apv_[0-9A-HJKMNP-TV-Z]{26}$')]
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )


class ExecutePaymentIntentRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )


class CancelPaymentIntentReason(StrEnum):
    CROSS_ALERT = 'CROSS_ALERT'
    INVOICE_REINVESTIGATED = 'INVOICE_REINVESTIGATED'
    OWNER_CANCELLED = 'OWNER_CANCELLED'


class CancelPaymentIntentRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    reason: CancelPaymentIntentReason
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
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
    channel: Channel
    amount_vnd: MoneyVnd
    status: PaymentIntentStatus
    gate_reasons: list[GateReason]
    rail: Annotated[PaymentIntentRail, Field(title='PaymentIntentRail')]
    transfer_memo: Annotated[
        str, Field(description="Nội dung chuyển khoản chuẩn 'MST · ký hiệu · số' (D2).")
    ]
    authorized_at: Timestamp | None
    executed_at: Timestamp | None
    settled_at: Timestamp | None
    expires_at: Timestamp | None
    created_at: Timestamp


class CreateEscrowRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    approval_id: Annotated[str, Field(pattern='^apv_[0-9A-HJKMNP-TV-Z]{26}$')]
    expires_on: LocalDate
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )


class ReleaseEscrowRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    approval_id: Annotated[str, Field(pattern='^apv_[0-9A-HJKMNP-TV-Z]{26}$')]
    goods_receipt_id: Annotated[str, Field(pattern='^grn_[0-9A-HJKMNP-TV-Z]{26}$')]
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )


class RefundEscrowReason(StrEnum):
    EXPIRED = 'EXPIRED'
    ORDER_CANCELLED = 'ORDER_CANCELLED'


class RefundEscrowRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    reason: RefundEscrowReason
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )


class GateDeniedProblem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    type: AnyUrl
    title: str
    status: Literal[422]
    code: Literal['GATE_DENIED']
    detail: str | None = None
    instance: str | None = None
    gate_reasons: Annotated[list[GateReason], Field(min_length=1)]
    payment_intent: PaymentIntent | None = None


type PaymentIntentStateMachineStatus = PaymentIntentStatus


type EscrowStateMachineStatus = EscrowStatus


class EvaluateEscrowRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    purchase_order_id: Annotated[str, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_account_id: Annotated[str, Field(pattern='^vac_[0-9A-HJKMNP-TV-Z]{26}$')]
    amount_vnd: MoneyVnd
    tenant_id: Annotated[str | None, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )


type EvaluateRequest = Annotated[
    EvaluateInvoiceRequest | EvaluateEscrowRequest, Field(title='EvaluateRequest')
]


class EvaluateResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    decision: GateDecision
    allowed_methods: list[AllowedMethod]
    verification_required: bool
    intent_hash: Annotated[str, Field(pattern='^[0-9a-f]{64}$')]
    payee_account_id: Annotated[
        str | None,
        Field(
            description='Null chỉ khi `decision = DENY` và người bán chưa có tài khoản trong vendor registry.',
            pattern='^vac_[0-9A-HJKMNP-TV-Z]{26}$',
        ),
    ]
    amount_vnd: MoneyVnd
    channel: Channel
    reasons: Annotated[
        list[GateReason],
        Field(
            description='Danh sách mã lý do của Payment Gate (`BLOCKED_INVOICE`, `PAYEE_NOT_VERIFIED`, `ABOVE_PER_INVOICE_LIMIT`, `ABOVE_DAILY_LIMIT`, `CROSS_ALERT_UNVERIFIED`, `OFFICIAL_FRAUD_LIST`, `KILL_SWITCH`, `POLICY_UNAVAILABLE`, `CHANNEL_NOT_ALLOWED`, `ALREADY_PAID`, `OUTSIDE_TIME_WINDOW`, `MANDATE_NOT_AUTO_PAY`, `VENDOR_NOT_IN_AUTO_PAY`, `VENDOR_SUSPENDED`, `APPROVAL_MISSING`, `APPROVAL_STALE`).\n'
        ),
    ]
    evaluated_at: Timestamp


class DailyBudgetResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    date: LocalDate
    auto_pay_used_vnd: MoneyVnd
    auto_pay_reserved_vnd: MoneyVnd
    auto_pay_limit_vnd: MoneyVnd
    total_paid_vnd: MoneyVnd


class PaymentIntentPage(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    items: list[PaymentIntent]
    next_cursor: str | None

# generated — do not edit

from __future__ import annotations

from datetime import date
from enum import Enum, StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


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


class AuthSessionRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    momo_token: Annotated[str, Field(min_length=1)]


type Timestamp = Annotated[
    AwareDatetime,
    Field(
        description='Thời điểm RFC 3339 có múi giờ (ví dụ 2026-11-26T09:15:00+07:00).',
        title='Timestamp',
    ),
]


class Role(StrEnum):
    owner = 'owner'
    accountant = 'accountant'
    store_manager = 'store_manager'


type StoreId = Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]


class User(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    user_id: Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
    name: str
    role: Role
    store_ids: list[StoreId]


class Tenant(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    tenant_id: Annotated[str, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    name: str


class MeResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    user_id: Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
    name: str
    role: Role
    store_ids: list[StoreId]
    tenant: Tenant
    permissions: list[str]


type LocalDate = Annotated[
    date,
    Field(
        description='Ngày theo giờ Việt Nam, định dạng YYYY-MM-DD.', title='LocalDate'
    ),
]


class InvoiceType(StrEnum):
    goods = 'goods'
    utility = 'utility'
    software = 'software'


type SignedMoneyVnd = Annotated[
    int,
    Field(
        description='Số tiền VND có dấu (integer, đơn vị đồng; có thể âm trên hóa đơn điều chỉnh TCHDon 2/4).',
        title='SignedMoneyVnd',
    ),
]


class InvoiceStatus(StrEnum):
    new = 'new'
    investigating = 'investigating'
    auto_pay_eligible = 'auto_pay_eligible'
    pending_approval = 'pending_approval'
    blocked = 'blocked'
    approved = 'approved'
    scheduled = 'scheduled'
    paying = 'paying'
    paid = 'paid'
    payment_failed = 'payment_failed'
    escrow_held = 'escrow_held'
    rejected = 'rejected'


class Severity(StrEnum):
    green = 'green'
    yellow = 'yellow'
    red = 'red'


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


type InvoiceId = Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]


class NotificationKind(StrEnum):
    cross_alert_affected = 'cross_alert_affected'
    payment_failed = 'payment_failed'
    daily_summary = 'daily_summary'
    verification_needed = 'verification_needed'
    bot_review_needed = 'bot_review_needed'
    escrow_expiring = 'escrow_expiring'


class InvoiceUploadResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    job_id: Annotated[str | None, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    status: InvoiceStatus


class Result(StrEnum):
    confirmed = 'confirmed'
    not_reachable = 'not_reachable'
    denied_by_vendor = 'denied_by_vendor'


class Verification(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    called_phone_on_file: Literal[True]
    result: Result
    note: str | None = None
    at: Timestamp


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


type MoneyVnd = Annotated[
    int,
    Field(
        description='Số tiền VND không âm (integer, đơn vị đồng).',
        ge=0,
        title='MoneyVnd',
    ),
]


class Channel(StrEnum):
    bank_transfer = 'bank_transfer'
    virtual_card = 'virtual_card'
    escrow = 'escrow'


class ApprovalMethod(StrEnum):
    single = 'single'
    bulk = 'bulk'
    mandate = 'mandate'


class ReasonCode1(StrEnum):
    PRICE_ABOVE_CONTRACT = 'PRICE_ABOVE_CONTRACT'
    PACK_SIZE_CHANGED = 'PACK_SIZE_CHANGED'
    QUANTITY_ABOVE_NORM = 'QUANTITY_ABOVE_NORM'
    NO_GOODS_RECEIPT = 'NO_GOODS_RECEIPT'
    DUPLICATE_INVOICE = 'DUPLICATE_INVOICE'
    OTHER = 'OTHER'


class RejectInvoiceRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    reason_code: ReasonCode1
    note: Annotated[str | None, Field(max_length=1000)] = None


class ChannelHint(StrEnum):
    email = 'email'
    chat = 'chat'


type CitedLine = Annotated[str, Field(pattern='^lin_[0-9A-HJKMNP-TV-Z]{26}$')]


class AdjustmentRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    adjustment_request_id: Annotated[str, Field(pattern='^adj_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    to_vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    channel_hint: ChannelHint
    subject: str
    body: str
    cited_lines: list[CitedLine]


class DemoResetRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )


class DemoResetResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    reset_at: Timestamp
    counts: dict[str, int]


class SupervisorStepEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    step: Annotated[int, Field(ge=1)]
    at: Timestamp


class BotStartedEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    bot_id: str
    at: Timestamp


class BotToolCalledEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    bot_id: str
    tool_id: str
    at: Timestamp


class BotFinishedEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    bot_id: str
    severity: Severity
    at: Timestamp


class BotFailedEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    bot_id: str
    reason_code: ReasonCode
    at: Timestamp


class AnswerDeltaEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    text_delta: Annotated[
        str, Field(description='Chuỗi streaming từ LLM (hiển thị như untrusted).')
    ]
    at: Timestamp


class ResyncEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    reason: Literal['cursor_expired']


class TaskType(StrEnum):
    investigate_invoice = 'investigate_invoice'
    question = 'question'
    report = 'report'


class InvoiceStatusChangedEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    from_: Annotated[InvoiceStatus, Field(alias='from')]
    to: InvoiceStatus
    severity: Severity | None


class NotificationCreatedEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    notification_id: Annotated[str, Field(pattern='^ntf_[0-9A-HJKMNP-TV-Z]{26}$')]
    kind: NotificationKind


class TenantResyncEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    reason: Literal['cursor_expired']


class PaymentIntentStatus(StrEnum):
    created = 'created'
    authorized = 'authorized'
    executing = 'executing'
    settled = 'settled'
    failed = 'failed'
    expired = 'expired'
    denied = 'denied'


class AuthSessionResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    session_jwt: str
    expires_at: Timestamp
    user: User


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
    issued_on: LocalDate | None
    invoice_type: InvoiceType
    total_vnd: Annotated[
        SignedMoneyVnd | None,
        Field(
            description='Null với PDF/ảnh chưa nhập tay; có thể âm trên hóa đơn điều chỉnh (TCHDon 2/4).'
        ),
    ]
    status: InvoiceStatus
    severity: Severity | None
    reason_codes: list[ReasonCode]
    verification_required: bool
    due_on: LocalDate | None
    scheduled_for: LocalDate | None
    updated_at: Timestamp


class Notification(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    notification_id: Annotated[str, Field(pattern='^ntf_[0-9A-HJKMNP-TV-Z]{26}$')]
    kind: NotificationKind
    invoice_ids: list[InvoiceId]
    title: str
    body: str
    read_at: Timestamp | None
    created_at: Timestamp


class ApproveInvoiceRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    intent_hash: Annotated[str, Field(pattern='^[0-9a-f]{64}$')]
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    auth_proof: Annotated[
        str,
        Field(description='Step-up JWT một lần gắn đúng `action_hash`.', min_length=1),
    ]
    verification: Verification | None = None


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
    amount_vnd: MoneyVnd
    payee_account_id: Annotated[str, Field(pattern='^vac_[0-9A-HJKMNP-TV-Z]{26}$')]
    channel: Channel
    intent_hash: Annotated[str, Field(pattern='^[0-9a-f]{64}$')]
    approver_user_id: Annotated[
        str | None, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    method: ApprovalMethod
    mandate_version: Annotated[int | None, Field(ge=1)]
    bulk_batch_id: Annotated[str | None, Field(pattern='^abt_[0-9A-HJKMNP-TV-Z]{26}$')]
    verification: Verification | None
    auth_proof_jti: str | None
    created_at: Timestamp
    superseded_at: Timestamp | None
    superseded_reason: SupersededReason | None


class RejectInvoiceResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice: InvoiceSummary
    adjustment_request: AdjustmentRequest | None


class ApprovalQueueGroup(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    key: str
    label: Annotated[
        str,
        Field(
            description='Tên NCC từ vendor registry hoặc tên mã lý do chuẩn (trusted).'
        ),
    ]
    count: Annotated[int, Field(ge=0)]
    total_vnd: SignedMoneyVnd
    bulk_approvable_count: Annotated[int, Field(ge=0)]
    invoices: list[InvoiceSummary]


class ApprovalQueueResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    groups: list[ApprovalQueueGroup]


class JobCompletedEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    task_type: TaskType
    invoice_id: Annotated[str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )
    final_severity: Severity | None = None
    reason_codes: list[ReasonCode] | None = None
    at: Timestamp


type JobSseEventData = Annotated[
    SupervisorStepEventData
    | BotStartedEventData
    | BotToolCalledEventData
    | BotFinishedEventData
    | BotFailedEventData
    | AnswerDeltaEventData
    | JobCompletedEventData
    | ResyncEventData,
    Field(
        description='Cấu trúc payload `data` cho các sự kiện SSE trên `GET /m/jobs/{job_id}/events` (docs/05-api/events.md §3).'
    ),
]


class PaymentUpdatedEventData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    payment_intent_id: Annotated[str, Field(pattern='^pi_[0-9A-HJKMNP-TV-Z]{26}$')]
    status: PaymentIntentStatus


type TenantSseEventData = Annotated[
    InvoiceStatusChangedEventData
    | NotificationCreatedEventData
    | PaymentUpdatedEventData
    | TenantResyncEventData,
    Field(
        description='Cấu trúc payload `data` cho các sự kiện SSE trên `GET /m/events` (docs/05-api/events.md §3).'
    ),
]


class InvoicePage(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    items: list[InvoiceSummary]
    next_cursor: str | None


class NotificationPage(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    items: list[Notification]
    next_cursor: str | None


class ApproveInvoiceResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    approval: Approval
    invoice: InvoiceSummary

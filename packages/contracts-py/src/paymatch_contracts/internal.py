# generated — do not edit

from __future__ import annotations

from datetime import date as date_aliased
from enum import Enum, StrEnum
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from typing_extensions import TypeAliasType


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


class V1ToolId(StrEnum):
    invoices = 'invoices'
    vendor_contracts = 'vendor_contracts'
    price_check = 'price_check'
    price_history = 'price_history'
    purchase_orders = 'purchase_orders'
    goods_receipts = 'goods_receipts'
    payables_ledger = 'payables_ledger'
    three_way_match = 'three_way_match'
    inbox = 'inbox'
    chat_messages = 'chat_messages'
    vendor_registry = 'vendor_registry'
    cross_alerts = 'cross_alerts'
    official_fraud_list = 'official_fraud_list'
    einvoice_portal = 'einvoice_portal'
    tax_id_lookup = 'tax_id_lookup'
    tax_risk_list = 'tax_risk_list'
    utility_bills = 'utility_bills'
    utility_baseline = 'utility_baseline'
    momo_revenue = 'momo_revenue'
    account_balance = 'account_balance'
    spending_limits = 'spending_limits'
    payment_policy_preview = 'payment_policy_preview'
    invoice_search = 'invoice_search'
    invoice_explain = 'invoice_explain'
    spending_summary = 'spending_summary'
    vendor_stats = 'vendor_stats'
    price_trend = 'price_trend'
    queue_status = 'queue_status'
    utility_summary = 'utility_summary'
    payment_history = 'payment_history'


class TaskType(StrEnum):
    investigate_invoice = 'investigate_invoice'
    question = 'question'
    report = 'report'


class ClaimedInvoiceSubject(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]


class ClaimedQuestionSubject(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    conversation_id: Annotated[str, Field(pattern='^cnv_[0-9A-HJKMNP-TV-Z]{26}$')]
    message_id: Annotated[str, Field(pattern='^cmg_[0-9A-HJKMNP-TV-Z]{26}$')]


class ClaimedReportSubject(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    report_id: Annotated[str, Field(pattern='^rpt_[0-9A-HJKMNP-TV-Z]{26}$')]


type Timestamp = Annotated[
    AwareDatetime,
    Field(
        description='Thời điểm RFC 3339 có múi giờ (ví dụ 2026-11-26T09:15:00+07:00).',
        title='Timestamp',
    ),
]


class OpenJobSessionRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    worker_id: Annotated[str, Field(min_length=1)]
    attempt: Annotated[int, Field(ge=1)]


class SessionBudget(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    seconds: Annotated[int, Field(ge=1)]
    max_steps: Annotated[int, Field(ge=1)]


class Provenance(StrEnum):
    trusted = 'trusted'
    untrusted = 'untrusted'


class BotSkillContent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    skill_id: Annotated[str, Field(min_length=1)]
    version: Annotated[int, Field(ge=1)]
    content_md: str


type PrefetchItem = Annotated[str, Field(pattern='^[a-z][a-z0-9_]*$')]


type Skill = Annotated[str, Field(min_length=1)]


type Tool = Annotated[str, Field(pattern='^[a-z][a-z0-9_]*$')]


class InvoiceType(StrEnum):
    goods = 'goods'
    utility = 'utility'
    software = 'software'


class Reason(StrEnum):
    KILL_SWITCH = 'KILL_SWITCH'
    DISABLED = 'DISABLED'


class SkippedBotItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    bot_id: Annotated[str, Field(min_length=1)]
    reason: Reason


class Role(StrEnum):
    owner = 'owner'
    accountant = 'accountant'
    store_manager = 'store_manager'


type StoreId = Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]


class SessionUserContext(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    role: Role
    store_ids: list[StoreId]


class InvestigateSessionContext(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_type: InvoiceType


class QuestionHistoryUserMessage(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    role: Literal['user']
    text_trusted: str


class Kind(StrEnum):
    daily_summary = 'daily_summary'
    spending_by_vendor = 'spending_by_vendor'
    spending_by_store = 'spending_by_store'
    price_changes = 'price_changes'


type LocalDate = Annotated[
    date_aliased,
    Field(
        description='Ngày theo giờ Việt Nam, định dạng YYYY-MM-DD.', title='LocalDate'
    ),
]


class JobHeartbeatRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    worker_id: Annotated[str, Field(min_length=1)]
    attempt: Annotated[int, Field(ge=1)]


class RenewedCapabilityToken(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    holder: Annotated[
        str, Field(description="'supervisor' hoặc '<bot_id>'.", min_length=1)
    ]
    capability_token: Annotated[str, Field(min_length=1)]
    token_exp: Timestamp


class JobHeartbeatResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    lease_expires_at: Timestamp
    tokens: list[RenewedCapabilityToken]


class Type(StrEnum):
    supervisor_step = 'supervisor.step'
    bot_started = 'bot.started'
    bot_tool_called = 'bot.tool_called'
    bot_finished = 'bot.finished'
    bot_failed = 'bot.failed'
    answer_delta = 'answer.delta'


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


class FactKey(StrEnum):
    unit_price_invoice = 'unit_price_invoice'
    unit_price_contract = 'unit_price_contract'
    price_delta_pct = 'price_delta_pct'
    pack_qty_contract = 'pack_qty_contract'
    pack_qty_parsed = 'pack_qty_parsed'
    invoice_total_vnd = 'invoice_total_vnd'
    po_total_vnd = 'po_total_vnd'
    quantity_delta = 'quantity_delta'
    payables_open_vnd = 'payables_open_vnd'
    invoice_count = 'invoice_count'
    invoice_due_on = 'invoice_due_on'
    verified_account_id = 'verified_account_id'
    cross_alert_count = 'cross_alert_count'
    fraud_list_match_count = 'fraud_list_match_count'
    tax_status_code = 'tax_status_code'
    portal_invoice_status_code = 'portal_invoice_status_code'
    portal_processing_status_code = 'portal_processing_status_code'
    tax_risk_listed_on = 'tax_risk_listed_on'
    utility_amount_vnd = 'utility_amount_vnd'
    utility_median_vnd = 'utility_median_vnd'
    utility_ratio_to_median = 'utility_ratio_to_median'
    store_revenue_vnd = 'store_revenue_vnd'
    wallet_balance_vnd = 'wallet_balance_vnd'
    auto_pay_used_vnd = 'auto_pay_used_vnd'
    auto_pay_limit_vnd = 'auto_pay_limit_vnd'
    spending_total_vnd = 'spending_total_vnd'
    pending_approval_total_vnd = 'pending_approval_total_vnd'
    pending_approval_count = 'pending_approval_count'
    gate_decision = 'gate_decision'
    gate_channel = 'gate_channel'


type Line = Annotated[str, Field(max_length=200)]


class Kind1(StrEnum):
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
        populate_by_name=True,
    )
    kind: Kind1
    ref_id: Annotated[
        str,
        Field(pattern='^(lin|doc|msg|itm|po|grn|tcl|vac|urd)_[0-9A-HJKMNP-TV-Z]{26}$'),
    ]
    tool_call_id: Annotated[str, Field(pattern='^tcl_[0-9A-HJKMNP-TV-Z]{26}$')]


class AnswerCitationInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    tool_call_id: Annotated[str, Field(pattern='^tcl_[0-9A-HJKMNP-TV-Z]{26}$')]
    values: list[str]


class AnswerTableInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    title: str | None = None
    columns: list[str]
    rows: list[list[str | float]]
    tool_call_id: Annotated[str, Field(pattern='^tcl_[0-9A-HJKMNP-TV-Z]{26}$')]


class Kind2(StrEnum):
    open_invoice = 'open_invoice'
    open_approval_queue = 'open_approval_queue'
    preview_bulk_approval = 'preview_bulk_approval'
    open_vendor = 'open_vendor'
    open_account_change = 'open_account_change'
    reinvestigate_invoice = 'reinvestigate_invoice'


type TargetId = Annotated[str, Field(min_length=1)]


class ProposedAction(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    kind: Kind2
    target_ids: list[TargetId]
    label: Annotated[str, Field(min_length=1)]


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


class CompleteAnswerResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    status: Literal['completed']
    message_id: Annotated[str, Field(pattern='^cmg_[0-9A-HJKMNP-TV-Z]{26}$')]
    unverified_values: list[str]


class FailJobRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    worker_id: Annotated[str, Field(min_length=1)]
    attempt: Annotated[int, Field(ge=1)]
    error_code: Annotated[str, Field(min_length=1)]
    detail: str


class FailJobResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    will_retry: bool


class ToolInvokeRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    input: dict[str, Any]


class Reason1(StrEnum):
    wrong_merchant = 'wrong_merchant'
    already_used = 'already_used'
    over_amount = 'over_amount'


class CardAuthorizationDeclinedWebhookData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    card_id: Annotated[str, Field(min_length=1)]
    merchant_id: Annotated[str, Field(min_length=1)]
    reason: Reason1


class TransferSettledWebhookData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    rail_txn_id: Annotated[str, Field(min_length=1)]
    idempotency_key: Annotated[str, Field(min_length=1)]
    status: Literal['settled']
    failure_code: None


class TransferFailedWebhookData(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    rail_txn_id: Annotated[str, Field(min_length=1)]
    idempotency_key: Annotated[str, Field(min_length=1)]
    status: Literal['failed']
    failure_code: str | None


class CardAuthorizationDeclinedWebhookRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['card.authorization_declined']
    occurred_at: Timestamp
    data: CardAuthorizationDeclinedWebhookData


class TransferSettledWebhookRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['transfer.settled']
    occurred_at: Timestamp
    data: TransferSettledWebhookData


class TransferFailedWebhookRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    event_id: Annotated[str, Field(pattern='^evt_[0-9A-HJKMNP-TV-Z]{26}$')]
    type: Literal['transfer.failed']
    occurred_at: Timestamp
    data: TransferFailedWebhookData


type RailsWebhookRequest = Annotated[
    CardAuthorizationDeclinedWebhookRequest
    | TransferSettledWebhookRequest
    | TransferFailedWebhookRequest,
    Field(discriminator='type', title='RailsWebhookRequest'),
]


type InvoiceId = Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]


class InvoicesInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_ids: list[InvoiceId] | None = None


class ManualFieldsMeta(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    entered_by: Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
    entered_at: Timestamp


class Format(StrEnum):
    xml = 'xml'
    pdf = 'pdf'
    image = 'image'


class InvoiceDocumentMeta(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    document_id: Annotated[str, Field(pattern='^doc_[0-9A-HJKMNP-TV-Z]{26}$')]
    format: Format
    sha256: Annotated[str, Field(pattern='^[0-9a-f]{64}$')]
    received_at: Timestamp


class Relation(StrEnum):
    replace = 'replace'
    adjust = 'adjust'
    replace_multiple = 'replace_multiple'
    adjust_multiple = 'adjust_multiple'
    trade_discount = 'trade_discount'


class RelatedInvoice(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    relation: Relation
    symbol: str
    number: str
    issued_on: LocalDate


class UntrustedSellerBankAccount(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    number: str
    bank_name: str


class Channel(StrEnum):
    email = 'email'
    chat = 'chat'


class FindingSummaryItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    bot_id: str
    severity: Severity
    reason_codes: Annotated[list[ReasonCode], Field(min_length=1)]


class AllowedAction(StrEnum):
    approve = 'approve'
    reject = 'reject'
    schedule = 'schedule'
    pay_now = 'pay_now'
    cancel_payment = 'cancel_payment'
    reinvestigate = 'reinvestigate'
    enter_manual_fields = 'enter_manual_fields'
    create_escrow = 'create_escrow'
    open_account_change = 'open_account_change'


type SignedMoneyVnd = Annotated[
    int,
    Field(
        description='Số tiền VND có dấu (integer trong khoảng safe integer [-9007199254740991, 9007199254740991], đơn vị đồng; có thể âm trên hóa đơn điều chỉnh TCHDon 2/4).',
        ge=-9007199254740991,
        le=9007199254740991,
        title='SignedMoneyVnd',
    ),
]


class InvoiceSource(StrEnum):
    email = 'email'
    upload = 'upload'
    bill_pay = 'bill_pay'
    scenario = 'scenario'


class Kind3(StrEnum):
    goods_service = 'goods_service'
    promotion = 'promotion'
    trade_discount = 'trade_discount'
    note = 'note'
    special_goods = 'special_goods'


class Source(StrEnum):
    invoice_xml = 'invoice_xml'
    email_body = 'email_body'
    chat_message = 'chat_message'
    bot_reason = 'bot_reason'
    ocr = 'ocr'


class UntrustedText(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    text: str
    provenance: Literal['untrusted']
    source: Source


type Decimal = Annotated[
    str,
    Field(
        description='Chuỗi thập phân tối đa 6 chữ số sau dấu chấm (số lượng, đơn giá, tỷ lệ theo QĐ 1233).',
        pattern='^-?\\d{1,15}(\\.\\d{1,6})?$',
        title='Decimal',
    ),
]


class Brief(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    brief_id: Annotated[str, Field(pattern='^brf_[0-9A-HJKMNP-TV-Z]{26}$')]
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    lines: Annotated[list[UntrustedText], Field(max_length=5)]
    cited_evidence: list[EvidenceRef]
    model: str
    prompt_hash: str


class Status(StrEnum):
    active = 'active'
    superseded = 'superseded'
    consumed = 'consumed'


class ApprovalMethod(StrEnum):
    single = 'single'
    bulk = 'bulk'
    mandate = 'mandate'


class PaymentIntentStatus(StrEnum):
    created = 'created'
    authorized = 'authorized'
    executing = 'executing'
    settled = 'settled'
    failed = 'failed'
    expired = 'expired'
    denied = 'denied'


class Channel1(StrEnum):
    bank_transfer = 'bank_transfer'
    virtual_card = 'virtual_card'
    escrow = 'escrow'


class EscrowStatus(StrEnum):
    pending = 'pending'
    held = 'held'
    released = 'released'
    refunded = 'refunded'
    failed = 'failed'


class VendorContractsInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )


class ContractItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    item_id: Annotated[str, Field(pattern='^itm_[0-9A-HJKMNP-TV-Z]{26}$')]
    sku: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    base_unit: Annotated[str, Field(min_length=1)]
    pack_spec: Annotated[str, Field(min_length=1)]
    pack_qty: Decimal
    unit_price: Decimal
    vat_rate: Annotated[str, Field(min_length=1)]


class PriceCheckMapping(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    line_id: Annotated[str, Field(pattern='^lin_[0-9A-HJKMNP-TV-Z]{26}$')]
    sku: Annotated[str, Field(min_length=1)]


class PriceCheckInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    mappings: Annotated[list[PriceCheckMapping], Field(min_length=1)]


class PriceCheckLineResult(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    line_id: Annotated[str, Field(pattern='^lin_[0-9A-HJKMNP-TV-Z]{26}$')]
    sku: Annotated[str, Field(min_length=1)]
    contract_item_id: Annotated[
        str | None, Field(pattern='^itm_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    unit_price_invoice: Decimal
    unit_price_contract: Decimal
    delta_pct: Decimal
    pack_qty_contract: Decimal
    pack_qty_parsed: Decimal | None


class PriceCheckOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    items: list[PriceCheckLineResult]


class PriceHistoryInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    sku: Annotated[str, Field(min_length=1)]
    months: Annotated[int | None, Field(ge=1, le=12)] = 6


class PriceHistoryPoint(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    issued_on: LocalDate
    quantity: Decimal
    unit_price: Decimal


class PriceHistoryOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    sku: Annotated[str, Field(min_length=1)]
    points: list[PriceHistoryPoint]


class PurchaseOrdersInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )
    purchase_order_id: Annotated[
        str | None, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')
    ] = None


class PurchaseOrderLine(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    sku: Annotated[str, Field(min_length=1)]
    quantity: Decimal
    unit_price: Decimal


class Status1(StrEnum):
    open = 'open'
    received = 'received'
    closed = 'closed'
    cancelled = 'cancelled'


type MoneyVnd = Annotated[
    int,
    Field(
        description='Số tiền VND không âm (integer trong khoảng safe integer [0, 9007199254740991], đơn vị đồng).',
        ge=0,
        le=9007199254740991,
        title='MoneyVnd',
    ),
]


class GoodsReceiptsInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )
    purchase_order_id: Annotated[
        str | None, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')
    ] = None


class GoodsReceiptLine(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    sku: Annotated[str, Field(min_length=1)]
    quantity_received: Decimal


class GoodsReceipt(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    goods_receipt_id: Annotated[str, Field(pattern='^grn_[0-9A-HJKMNP-TV-Z]{26}$')]
    purchase_order_id: Annotated[str, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')]
    store_id: Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]
    lines: Annotated[list[GoodsReceiptLine], Field(min_length=1)]
    confirmed_by: Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
    confirmed_at: Timestamp


class PayablesLedgerInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )
    purchase_order_id: Annotated[
        str | None, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')
    ] = None


class PayableLedgerEntry(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    symbol: str
    number: str
    issued_on: LocalDate | None
    due_on: LocalDate | None
    amount_vnd: SignedMoneyVnd
    status: InvoiceStatus
    paid_at: Timestamp | None


class PayablesLedgerOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    entries: list[PayableLedgerEntry]


class ThreeWayMatchInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )


type GoodsReceiptId = Annotated[str, Field(pattern='^grn_[0-9A-HJKMNP-TV-Z]{26}$')]


class ThreeWayMatchLine(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    line_id: Annotated[str, Field(pattern='^lin_[0-9A-HJKMNP-TV-Z]{26}$')]
    sku: str | None
    po_quantity: Decimal | None
    grn_quantity: Decimal | None
    invoice_quantity: Decimal | None
    delta_quantity: Decimal | None
    within_norm: bool


class ThreeWayMatchOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    matched: bool
    missing_goods_receipt: bool
    quantity_above_norm: bool
    purchase_order_id: Annotated[
        str | None, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    goods_receipt_ids: list[GoodsReceiptId]
    lines: list[ThreeWayMatchLine]


class InboxInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    since: Timestamp | None = None


class InboxToolMessage(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    message_id: Annotated[str, Field(pattern='^msg_[0-9A-HJKMNP-TV-Z]{26}$')]
    from_address: str
    received_at: Timestamp
    subject: UntrustedText
    body: UntrustedText


class InboxOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    messages: list[InboxToolMessage]


class ChatMessagesInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    since: Timestamp | None = None


class Sender(StrEnum):
    tenant = 'tenant'
    counterparty = 'counterparty'


class ChatToolMessage(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    message_id: Annotated[str, Field(pattern='^msg_[0-9A-HJKMNP-TV-Z]{26}$')]
    sender: Sender
    sent_at: Timestamp
    text: UntrustedText


class ChatToolThread(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    thread_id: str
    counterparty_phone: str
    counterparty_name: UntrustedText
    messages: list[ChatToolMessage]


class ChatMessagesOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    threads: list[ChatToolThread]


class VendorRegistryInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )


class TargetStatus(StrEnum):
    verified = 'verified'
    escrow_only = 'escrow_only'


class ApprovedVendorVerificationSummary(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    verification_id: Annotated[str, Field(pattern='^vvf_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_account_id: Annotated[str, Field(pattern='^vac_[0-9A-HJKMNP-TV-Z]{26}$')]
    target_status: TargetStatus
    decided_at: Timestamp


class Status2(StrEnum):
    active = 'active'
    inactive = 'inactive'


class Vendor(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor_id: Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    name: Annotated[str, Field(min_length=1)]
    tax_id: Annotated[str, Field(min_length=1)]
    phone_on_file_masked: Annotated[str, Field(min_length=1)]
    status: Status2
    created_at: Timestamp


class Kind4(StrEnum):
    bank_account = 'bank_account'
    card_merchant = 'card_merchant'


class VendorAccountStatus(StrEnum):
    verified = 'verified'
    escrow_only = 'escrow_only'
    retired = 'retired'


class CrossAlertsInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )


class IndicatorKind(StrEnum):
    account_hash = 'account_hash'
    tax_id = 'tax_id'
    phone = 'phone'
    card_id = 'card_id'
    merchant_id = 'merchant_id'


class OfficialFraudListInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )


class Kind5(StrEnum):
    account_hash = 'account_hash'
    phone = 'phone'
    tax_id = 'tax_id'


class OfficialFraudListMatch(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    kind: Kind5
    listed: bool
    list_ref: str | None


class OfficialFraudListOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    listed: bool
    matches: list[OfficialFraudListMatch]


class EinvoicePortalInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )


class PortalRelatedInvoice(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    symbol: str
    number: str
    issued_on: LocalDate


class EinvoicePortalOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    found: bool
    invoice_status_code: Annotated[int | None, Field(ge=1, le=6)]
    invoice_status_label: str | None
    processing_status_code: Annotated[int | None, Field(ge=0, le=8)]
    processing_status_label: str | None
    illegal_flag: bool | None
    tax_authority_code: str | None
    total_vnd: SignedMoneyVnd | None
    related_invoice: PortalRelatedInvoice | None


class TaxIdLookupInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    tax_id: Annotated[str, Field(min_length=1)]


class StatusCode(StrEnum):
    field_00 = '00'
    field_01 = '01'
    field_02 = '02'
    field_03 = '03'
    field_04 = '04'
    field_05 = '05'
    field_06 = '06'
    field_07 = '07'
    field_09 = '09'
    field_10 = '10'


class TaxIdLookupOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    tax_id: str
    name: str
    status_code: StatusCode
    status_label: str
    status_reason_code: str | None
    address: str


class TaxRiskListInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    tax_id: Annotated[str, Field(min_length=1)]


class TaxRiskListOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    tax_id: str
    listed: bool
    list_name: str | None
    listed_on: LocalDate | None


class UtilityBillsInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    store_id: Annotated[str | None, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )
    months: Annotated[int | None, Field(ge=1, le=12)] = 12


class UtilityType(StrEnum):
    electricity = 'electricity'
    water = 'water'


class UtilityBillReadingItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    reading_id: Annotated[str, Field(pattern='^urd_[0-9A-HJKMNP-TV-Z]{26}$')]
    store_id: Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]
    utility_type: UtilityType
    billing_period: Annotated[str, Field(pattern='^\\d{4}-\\d{2}$')]
    period_start: LocalDate
    period_end: LocalDate
    total_usage: Decimal
    usage_unit: str
    total_vnd: MoneyVnd


class UtilityBillsOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    readings: list[UtilityBillReadingItem]


class UtilityBaselineInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    store_id: Annotated[str | None, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )
    months: Annotated[int | None, Field(ge=1, le=12)] = 12


class UtilityType1(Enum):
    electricity = 'electricity'
    water = 'water'
    NoneType_None = None


type ReadingId = Annotated[str, Field(pattern='^urd_[0-9A-HJKMNP-TV-Z]{26}$')]


class UtilityBaselineOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    store_id: Annotated[str | None, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]
    utility_type: UtilityType1 | None
    months: Annotated[int, Field(ge=1, le=12)]
    median_usage: Decimal | None
    normal_min_usage: Decimal | None
    normal_max_usage: Decimal | None
    median_amount_vnd: MoneyVnd | None
    normal_min_vnd: MoneyVnd | None
    normal_max_vnd: MoneyVnd | None
    current_usage: Decimal | None
    current_amount_vnd: MoneyVnd | None
    ratio_to_median: Decimal | None
    out_of_range: bool
    reading_ids: list[ReadingId]


class MomoRevenueInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    store_id: Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]
    month: Annotated[str, Field(pattern='^\\d{4}-\\d{2}$')]


class MomoRevenueOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    store_id: Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]
    month: Annotated[str, Field(pattern='^\\d{4}-\\d{2}$')]
    revenue_vnd: MoneyVnd
    transaction_count: Annotated[int, Field(ge=0)]


class AccountBalanceInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )


class AccountBalanceOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    wallet_id: Annotated[str, Field(pattern='^wal_[0-9A-HJKMNP-TV-Z]{26}$')]
    balance_vnd: MoneyVnd
    as_of: Timestamp


class SpendingLimitsInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )


class SpendingLimitsDailyBudget(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    date: LocalDate
    auto_pay_used_vnd: MoneyVnd
    auto_pay_reserved_vnd: MoneyVnd
    auto_pay_limit_vnd: MoneyVnd
    total_paid_vnd: MoneyVnd


class MandateLimits(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    per_invoice_vnd: MoneyVnd
    per_day_vnd: MoneyVnd


type AutoPayVendorId = Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]


class MandateChannelRule(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_type: InvoiceType
    channel: Channel1


class BulkApprovableRule(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    reason_codes: Annotated[list[ReasonCode], Field(min_length=1)]
    max_amount_vnd: MoneyVnd


class AutoPayWindow(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    start: Annotated[str, Field(pattern='^([01]\\d|2[0-3]):[0-5]\\d$')]
    end: Annotated[str, Field(pattern='^([01]\\d|2[0-3]):[0-5]\\d$')]


class MandateSignature(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    by_user_id: Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
    method: Annotated[str, Field(min_length=1)]
    auth_proof_jti: Annotated[str, Field(min_length=1)]
    at: Timestamp


class MandateMode(StrEnum):
    review_only = 'review_only'
    ask_first = 'ask_first'
    auto_pay = 'auto_pay'


class PlatformLimits(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    auto_pay_per_invoice_vnd: MoneyVnd
    auto_pay_per_day_vnd: MoneyVnd
    updated_at: Timestamp


class PaymentPolicyPreviewInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )


class Decision(StrEnum):
    ALLOW = 'ALLOW'
    REQUIRE_APPROVAL = 'REQUIRE_APPROVAL'
    DENY = 'DENY'


class AllowedMethod(StrEnum):
    single = 'single'
    bulk = 'bulk'


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
    ESCROW_MISMATCH = 'ESCROW_MISMATCH'


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


class InvoiceSearchInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    status: InvoiceStatus | None = None
    severity: Severity | None = None
    vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )
    store_id: Annotated[str | None, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )
    reason_code: ReasonCode | None = None
    issued_from: LocalDate | None = None
    issued_to: LocalDate | None = None
    limit: Annotated[int | None, Field(ge=1, le=50)] = 20


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


class InvoiceExplainInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]


class FindingForSupervisor(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    finding_id: Annotated[str, Field(pattern='^fnd_[0-9A-HJKMNP-TV-Z]{26}$')]
    bot_id: Annotated[str, Field(min_length=1)]
    severity: Severity
    reason_codes: Annotated[list[ReasonCode], Field(min_length=1)]
    evidence: list[EvidenceRef]


class GroupBy(StrEnum):
    vendor = 'vendor'
    store = 'store'
    invoice_type = 'invoice_type'
    month = 'month'


class SpendingSummaryInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    from_: Annotated[LocalDate, Field(alias='from')]
    to: LocalDate
    group_by: GroupBy
    store_id: Annotated[str | None, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )


class SpendingSummaryGroup(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    key: str
    label: str
    invoice_count: Annotated[int, Field(ge=0)]
    total_vnd: SignedMoneyVnd


class SpendingSummaryOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    from_: Annotated[LocalDate, Field(alias='from')]
    to: LocalDate
    group_by: GroupBy
    total_vnd: SignedMoneyVnd
    invoice_count: Annotated[int, Field(ge=0)]
    groups: list[SpendingSummaryGroup]


class VendorStatsInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor_id: Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    months: Annotated[int | None, Field(ge=1, le=12)] = 6


class VendorStatsOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor_id: Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_name: str
    months: Annotated[int, Field(ge=1, le=12)]
    invoice_count: Annotated[int, Field(ge=0)]
    total_vnd: SignedMoneyVnd
    above_contract_count: Annotated[int, Field(ge=0)]
    yellow_count: Annotated[int, Field(ge=0)]
    red_count: Annotated[int, Field(ge=0)]


class PriceTrendInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    sku: Annotated[str, Field(min_length=1)]
    months: Annotated[int | None, Field(ge=1, le=12)] = 6


class PriceTrendPoint(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    month: Annotated[str, Field(pattern='^\\d{4}-\\d{2}$')]
    avg_unit_price: Decimal
    min_unit_price: Decimal
    max_unit_price: Decimal
    delta_vs_contract_pct: Decimal | None


class PriceTrendOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    sku: str
    contract_unit_price: Decimal | None
    points: list[PriceTrendPoint]


class QueueStatusInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )


CountsByStatusAdditionalProperty = TypeAliasType(
    "CountsByStatusAdditionalProperty", Annotated[int, Field(ge=0)]
)


class QueueStatusOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    counts_by_status: dict[str, CountsByStatusAdditionalProperty]
    pending_approval_total_vnd: SignedMoneyVnd
    nearest_due_on: LocalDate | None


class UtilitySummaryInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    store_id: Annotated[str | None, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )
    months: Annotated[int | None, Field(ge=1, le=12)] = 12


class UtilityType2(StrEnum):
    electricity = 'electricity'
    water = 'water'


class UtilitySummaryStoreItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    store_id: Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]
    store_name: str
    utility_type: UtilityType2
    latest_amount_vnd: MoneyVnd
    median_amount_vnd: MoneyVnd
    out_of_range_months: Annotated[int, Field(ge=0)]


class UtilitySummaryOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    months: Annotated[int, Field(ge=1, le=12)]
    stores: list[UtilitySummaryStoreItem]


class PaymentHistoryInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    from_: Annotated[LocalDate, Field(alias='from')]
    to: LocalDate
    vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')] = (
        None
    )


class PaymentHistoryItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    payment_intent_id: Annotated[str, Field(pattern='^pi_[0-9A-HJKMNP-TV-Z]{26}$')]
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_name: str | None
    paid_on: LocalDate
    settled_at: Timestamp
    amount_vnd: MoneyVnd
    channel: Channel1


class PaymentHistoryOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    payments: list[PaymentHistoryItem]


class ClaimJobRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    worker_id: Annotated[str, Field(min_length=1)]
    task_types: Annotated[list[TaskType] | None, Field(min_length=1)] = None


class ClaimedJobResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    job_id: Annotated[str, Field(pattern='^job_[0-9A-HJKMNP-TV-Z]{26}$')]
    task_type: TaskType
    tenant_id: Annotated[str, Field(pattern='^ten_[0-9A-HJKMNP-TV-Z]{26}$')]
    attempt: Annotated[int, Field(ge=1)]
    lease_expires_at: Timestamp
    subject: ClaimedInvoiceSubject | ClaimedQuestionSubject | ClaimedReportSubject


class ToolDefinition(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    tool_id: Annotated[str, Field(pattern='^[a-z][a-z0-9_]*$')]
    description: Annotated[str, Field(min_length=1)]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    default_provenance: Provenance
    scope: Literal['tenant']


class BotManifestTriggers(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_types: list[InvoiceType]


class BotManifest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    id: Annotated[str, Field(pattern='^[a-z][a-z0-9-]*$')]
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str, Field(min_length=1)]
    skills: Annotated[list[Skill], Field(min_length=1)]
    tools: list[Tool]
    task_types: Annotated[list[TaskType] | None, Field(min_length=1)] = None
    triggers: Annotated[BotManifestTriggers, Field(title='BotManifestTriggers')]
    required_for: list[InvoiceType] | None = None


class QuestionHistoryAssistantMessage(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    role: Literal['assistant']
    message_id: Annotated[str, Field(pattern='^cmg_[0-9A-HJKMNP-TV-Z]{26}$')]
    citations: list[AnswerCitationInput]


type QuestionHistoryMessage = Annotated[
    QuestionHistoryUserMessage | QuestionHistoryAssistantMessage,
    Field(discriminator='role', title='QuestionHistoryMessage'),
]


class QuestionSessionContext(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    messages: list[QuestionHistoryMessage]
    user: SessionUserContext


class ReportSessionContext(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    report_id: Annotated[str, Field(pattern='^rpt_[0-9A-HJKMNP-TV-Z]{26}$')]
    kind: Kind
    from_: Annotated[LocalDate, Field(alias='from')]
    to: LocalDate
    user: SessionUserContext


class JobProgressEventItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    type: Type
    step: Annotated[int | None, Field(ge=1)] = None
    bot_id: str | None = None
    tool_id: str | None = None
    severity: Severity | None = None
    reason_code: ReasonCode | None = None
    text_delta: Annotated[
        str | None,
        Field(
            description='Chỉ được phép (và bắt buộc dạng chuỗi) khi `type = answer.delta`.'
        ),
    ] = None
    at: Timestamp


class JobProgressRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    worker_id: Annotated[str, Field(min_length=1)]
    attempt: Annotated[int, Field(ge=1)]
    events: Annotated[list[JobProgressEventItem], Field(min_length=1)]


class BotAnswerFactInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    key: FactKey
    value: str | float
    tool_call_id: Annotated[str, Field(pattern='^tcl_[0-9A-HJKMNP-TV-Z]{26}$')]


class BotAnswerSubmission(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    bot_id: Annotated[str, Field(min_length=1)]
    facts: list[BotAnswerFactInput]
    reason_codes: list[ReasonCode]


class BriefSubmission(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    lines: Annotated[list[Line], Field(max_length=5, min_length=1)]
    cited_evidence: list[EvidenceRef]
    model: Annotated[str, Field(min_length=1)]
    prompt_hash: Annotated[str, Field(min_length=1)]


class CompleteInvestigateResult(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    brief: BriefSubmission


class AnswerSubmission(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    text: str
    citations: list[AnswerCitationInput]
    tables: list[AnswerTableInput] | None = None
    proposed_actions: list[ProposedAction]


class CompleteAnswerResult(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    answer: AnswerSubmission


class CompleteJobRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    worker_id: Annotated[str, Field(min_length=1)]
    attempt: Annotated[int, Field(ge=1)]
    result: CompleteInvestigateResult | CompleteAnswerResult


class CompleteInvestigateResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    status: Literal['completed']
    final_severity: Severity
    invoice_status: InvoiceStatus


type CompleteJobResponse = Annotated[
    CompleteInvestigateResponse | CompleteAnswerResponse,
    Field(title='CompleteJobResponse'),
]


class VatBreakdownItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vat_rate: str
    taxable_vnd: SignedMoneyVnd
    vat_vnd: SignedMoneyVnd


class UntrustedOtherInfoItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    field: str
    value: UntrustedText


class UntrustedMessageItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    message_id: Annotated[str, Field(pattern='^msg_[0-9A-HJKMNP-TV-Z]{26}$')]
    channel: Channel
    received_at: Timestamp
    body: UntrustedText


class InvoiceUntrustedFields(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    seller_name: UntrustedText
    seller_address: UntrustedText
    seller_bank_account: UntrustedSellerBankAccount | None
    payment_terms: UntrustedText | None
    other_info: list[UntrustedOtherInfoItem]
    messages: list[UntrustedMessageItem]


class InvoicePaymentSummary(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    payment_intent_id: Annotated[str, Field(pattern='^pi_[0-9A-HJKMNP-TV-Z]{26}$')]
    status: PaymentIntentStatus
    channel: Channel1
    settled_at: Timestamp | None


class InvoiceEscrowSummary(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    escrow_id: Annotated[str, Field(pattern='^esc_[0-9A-HJKMNP-TV-Z]{26}$')]
    status: EscrowStatus


class InvoiceLine(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    line_id: Annotated[str, Field(pattern='^lin_[0-9A-HJKMNP-TV-Z]{26}$')]
    position: Annotated[int, Field(ge=1)]
    kind: Kind3
    item_code: UntrustedText | None
    name: UntrustedText
    unit: UntrustedText | None
    quantity: Decimal | None
    unit_price: Decimal | None
    discount_vnd: SignedMoneyVnd | None
    amount_vnd: SignedMoneyVnd | None
    vat_rate: str | None
    arithmetic_ok: bool


class ApprovalSummary(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    approval_id: Annotated[str, Field(pattern='^apv_[0-9A-HJKMNP-TV-Z]{26}$')]
    method: ApprovalMethod
    status: Status
    approver_user_id: Annotated[
        str | None, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')
    ]
    created_at: Timestamp


class ActiveVendorContract(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    contract_id: Annotated[str, Field(pattern='^ctr_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_id: Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    valid_from: LocalDate
    valid_to: LocalDate | None
    items: list[ContractItem]


class VendorContractsOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    contracts: list[ActiveVendorContract]


class PurchaseOrder(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    purchase_order_id: Annotated[str, Field(pattern='^po_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_id: Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    store_id: Annotated[str, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]
    lines: Annotated[list[PurchaseOrderLine], Field(min_length=1)]
    total_vnd: MoneyVnd
    status: Status1
    created_by: Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
    created_at: Timestamp


class GoodsReceiptsOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    goods_receipts: list[GoodsReceipt]


class VendorAccount(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor_account_id: Annotated[str, Field(pattern='^vac_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_id: Annotated[str, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    kind: Kind4
    bank_code: str | None
    bank_name: str | None
    account_number_masked: str | None
    merchant_id: str | None
    account_name: Annotated[str, Field(min_length=1)]
    status: VendorAccountStatus
    verified_at: Timestamp | None


class CrossAlertHitItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    cross_alert_id: Annotated[str, Field(pattern='^cxa_[0-9A-HJKMNP-TV-Z]{26}$')]
    indicator_kind: IndicatorKind
    reason_codes: list[ReasonCode]
    published_at: Timestamp


class CrossAlertsOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    matched: bool
    hits: list[CrossAlertHitItem]


class Mandate(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    mandate_id: Annotated[str, Field(pattern='^man_[0-9A-HJKMNP-TV-Z]{26}$')]
    version: Annotated[int, Field(ge=1)]
    mode: MandateMode
    limits: Annotated[MandateLimits, Field(title='MandateLimits')]
    auto_pay_vendor_ids: list[AutoPayVendorId]
    channel_rules: list[MandateChannelRule]
    bulk_approvable: list[BulkApprovableRule]
    auto_pay_window: Annotated[AutoPayWindow, Field(title='AutoPayWindow')]
    signed: Annotated[MandateSignature, Field(title='MandateSignature')]
    created_at: Timestamp


class PaymentPolicyPreviewOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    decision: Decision
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
    channel: Channel1
    reasons: list[GateReason]
    evaluated_at: Timestamp


class InvoiceSearchOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    items: list[InvoiceSummary]


class InvoiceExplainOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice: InvoiceSummary
    findings: list[FindingForSupervisor]


class SupervisorSessionGrant(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    capability_token: Annotated[str, Field(min_length=1)]
    token_exp: Timestamp
    tools: list[ToolDefinition]


class BotSessionGrant(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    bot_id: Annotated[str, Field(min_length=1)]
    bot_version: Annotated[int, Field(ge=1)]
    description: str
    manifest: BotManifest
    skills: list[BotSkillContent]
    prefetch: list[PrefetchItem]
    capability_token: Annotated[str, Field(min_length=1)]
    token_exp: Timestamp


class JobSessionResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    budget: SessionBudget
    supervisor: SupervisorSessionGrant
    bots: list[BotSessionGrant]
    required_bot_ids: list[str]
    skipped: list[SkippedBotItem]
    context: InvestigateSessionContext | QuestionSessionContext | ReportSessionContext


class Invoice(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoice_id: Annotated[str, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    store_id: Annotated[str | None, Field(pattern='^sto_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_id: Annotated[str | None, Field(pattern='^ven_[0-9A-HJKMNP-TV-Z]{26}$')]
    vendor_name: str | None
    seller_tax_id: str
    symbol: str
    number: str
    issued_on: LocalDate | None
    invoice_type: InvoiceType
    total_vnd: SignedMoneyVnd | None
    status: InvoiceStatus
    severity: Severity | None
    reason_codes: list[ReasonCode]
    verification_required: bool
    due_on: LocalDate | None
    scheduled_for: LocalDate | None
    updated_at: Timestamp
    source: InvoiceSource
    duplicate_of: Annotated[str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    manual_fields: ManualFieldsMeta | None
    document: Annotated[InvoiceDocumentMeta, Field(title='InvoiceDocumentMeta')]
    buyer_tax_id: str
    currency: Literal['VND']
    subtotal_vnd: SignedMoneyVnd | None
    vat_total_vnd: SignedMoneyVnd | None
    vat_breakdown: list[VatBreakdownItem]
    tax_authority_code: str | None
    einvoice_provider_tax_id: str | None
    related_invoice: RelatedInvoice | None
    lines: list[InvoiceLine]
    untrusted: Annotated[InvoiceUntrustedFields, Field(title='InvoiceUntrustedFields')]
    brief: Brief | None
    findings_summary: list[FindingSummaryItem]
    approval: ApprovalSummary | None
    payment: InvoicePaymentSummary | None
    escrow: InvoiceEscrowSummary | None
    allowed_actions: list[AllowedAction]
    etag: str


class PurchaseOrdersOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    purchase_orders: list[PurchaseOrder]


class VendorRegistryOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vendor: Vendor | None
    accounts: list[VendorAccount]
    approved_verifications: list[ApprovedVendorVerificationSummary]


class SpendingLimitsOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    mandate: Mandate | None
    platform_limits: PlatformLimits
    daily_budget: Annotated[
        SpendingLimitsDailyBudget, Field(title='SpendingLimitsDailyBudget')
    ]


class InvoicesOutput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    invoices: list[Invoice]

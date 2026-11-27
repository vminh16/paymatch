"""Pydantic request/response schemas matching contracts/openapi/sim-world.yaml."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    dataset: str
    loaded_at: str


# --- Identity ---


class JwkKey(BaseModel):
    kty: Literal["OKP"]
    crv: Literal["Ed25519"]
    alg: Literal["EdDSA"]
    use: Literal["sig"]
    kid: str
    x: str


class JwksResponse(BaseModel):
    keys: list[JwkKey]


class MerchantTokenRequest(BaseModel):
    user_id: str = Field(min_length=1)


class MerchantTokenResponse(BaseModel):
    momo_token: str


class StaffTokenRequest(BaseModel):
    staff_id: str = Field(min_length=1)


class StaffTokenResponse(BaseModel):
    sso_token: str


class StepUpChallengeRequest(BaseModel):
    momo_token: str = Field(min_length=1)
    action_hash: str = Field(min_length=1)


class StepUpChallengeResponse(BaseModel):
    challenge_id: str
    expires_at: str
    demo_otp: str | None = None


class StepUpVerifyRequest(BaseModel):
    otp: str = Field(min_length=1)


class StepUpVerifyResponse(BaseModel):
    auth_proof: str


# --- Rails ---


class BankAccountRef(BaseModel):
    bank_code: str = Field(min_length=1)
    account_number: str = Field(min_length=1)
    account_name: str = Field(min_length=1)


class TransferRequest(BaseModel):
    idempotency_key: str = Field(min_length=1)
    from_wallet_id: str = Field(min_length=1)
    to: BankAccountRef
    amount_vnd: int = Field(ge=1)
    memo: str


class TransferResponse(BaseModel):
    rail_txn_id: str
    status: Literal["settled", "failed"]
    failure_code: Literal["INSUFFICIENT_FUNDS", "ACCOUNT_NOT_FOUND", "NAME_MISMATCH", "RAIL_DOWN"] | None
    settled_at: str | None


class CreateCardRequest(BaseModel):
    idempotency_key: str = Field(min_length=1)
    from_wallet_id: str = Field(min_length=1)
    merchant_id: str = Field(min_length=1)
    amount_vnd: int = Field(ge=1)
    single_use: bool = True


class CreateCardResponse(BaseModel):
    card_id: str
    last4: str
    status: Literal["issued", "captured"]


class CardCapture(BaseModel):
    merchant_id: str
    amount_vnd: int
    captured_at: str


class CardDeclinedAttempt(BaseModel):
    merchant_id: str
    amount_vnd: int
    reason: Literal["wrong_merchant", "already_used", "over_amount"]
    at: str


class CardDetailResponse(BaseModel):
    card_id: str
    status: Literal["issued", "captured"]
    captures: list[CardCapture]
    declined_attempts: list[CardDeclinedAttempt]


class CreateEscrowRequest(BaseModel):
    idempotency_key: str = Field(min_length=1)
    from_wallet_id: str = Field(min_length=1)
    to: BankAccountRef
    amount_vnd: int = Field(ge=1)
    expires_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class CreateEscrowResponse(BaseModel):
    rail_escrow_id: str
    status: Literal["held"]


class EscrowActionRequest(BaseModel):
    idempotency_key: str = Field(min_length=1)


class EscrowActionResponse(BaseModel):
    status: Literal["released", "refunded"]


class WalletResponse(BaseModel):
    wallet_id: str
    balance_vnd: int
    as_of: str


# --- Inbox & Bills ---


class InboxAttachmentMeta(BaseModel):
    attachment_id: str
    filename: str
    content_type: str
    size: int


class InboxMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: str
    from_: str = Field(alias="from")
    subject: str
    body_text: str
    received_at: str
    attachments: list[InboxAttachmentMeta]


class InboxMessagesPage(BaseModel):
    items: list[InboxMessage]
    next_cursor: str | None


class UtilityReadingLine(BaseModel):
    line_code: str
    meter_serial: str
    time_band: str | None = None
    old_index: str | None = None
    new_index: str | None = None
    multiplier: str | None = None
    usage: str
    unit: str
    unit_price_vnd: int
    amount_vnd: int
    vat_rate_pct: int
    vat_amount_vnd: int


class UtilityReadings(BaseModel):
    lines: list[UtilityReadingLine]


class BillItem(BaseModel):
    bill_id: str
    provider: Literal["electricity", "water"]
    vendor_tax_id: str | None = None
    customer_code: str
    store_ref: str
    period: str
    period_start: str | None = None
    period_end: str | None = None
    billing_days: int | None = None
    due_date: str | None = None
    statement_no: str | None = None
    total_usage: str | None = None
    usage_unit: str | None = None
    subtotal_vnd: int | None = None
    vat_total_vnd: int | None = None
    amount_vnd: int
    readings: UtilityReadings
    xml_attachment_id: str | None


class BillsPage(BaseModel):
    items: list[BillItem]
    next_cursor: str | None


# --- Chat ---


class ChatThread(BaseModel):
    thread_id: str
    counterparty_name: str
    counterparty_phone: str


class ChatMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: str
    from_: Literal["tenant", "counterparty"] = Field(alias="from")
    text: str
    sent_at: str


# --- Lookups ---


class RelatedInvoiceRef(BaseModel):
    symbol: str
    number: str
    issued_on: str


class EinvoiceLookupResponse(BaseModel):
    found: bool
    invoice_status_code: Literal[1, 2, 3, 4, 5, 6] | None
    invoice_status_label: str | None
    processing_status_code: Literal[0, 1, 2, 3, 4, 5, 6, 7, 8] | None
    processing_status_label: str | None
    illegal_flag: bool | None
    tax_authority_code: str | None
    total_vnd: int | None
    related_invoice: RelatedInvoiceRef | None


class TaxpayerResponse(BaseModel):
    tax_id: str
    name: str
    status_code: Literal["00", "01", "02", "03", "04", "05", "06", "07", "09", "10"]
    status_label: str
    status_reason_code: str | None
    address: str


class TaxRiskListResponse(BaseModel):
    listed: bool
    list_name: str | None
    listed_on: str | None


class SimoCheckResponse(BaseModel):
    listed: bool
    list_ref: str | None


class RevenueResponse(BaseModel):
    revenue_vnd: int
    transaction_count: int


# --- Scenario ---


class ScenarioResetRequest(BaseModel):
    dataset: str = "demo"
    seed: int = 42


class ScenarioResetResponse(BaseModel):
    loaded_at: str
    counts: dict[str, int]


class WebhookRecordSchema(BaseModel):
    event_id: str
    type: Literal["card.authorization_declined", "transfer.settled", "transfer.failed"]
    occurred_at: str
    data: dict[str, Any]
    delivered: bool
    error: str | None = None


class ScenarioWalletSummary(BaseModel):
    wallet_id: str
    tenant_id: str
    balance_vnd: int
    as_of: str


class ScenarioCardSummary(BaseModel):
    card_id: str
    merchant_id: str
    amount_vnd: int
    last4: str
    status: Literal["issued", "captured"]
    captures_count: int
    declined_attempts_count: int


class ScenarioStateResponse(BaseModel):
    dataset: str
    seed: int
    loaded_at: str
    clock: str
    inbox_count: int
    bills_count: int
    wallets: list[ScenarioWalletSummary]
    cards: list[ScenarioCardSummary]
    escrows_count: int
    transfers_count: int
    webhooks: list[WebhookRecordSchema]


class ScenarioCatalogItem(BaseModel):
    template_id: str
    title: str
    expected_severity: Literal["green", "yellow", "red"] | None
    expected_reason_codes: list[str]
    group: str | None = None
    channel: str | None = None
    notes: str | None = None


class SendScenarioInvoiceRequest(BaseModel):
    template_id: str = Field(min_length=1)
    overrides: dict[str, Any] | None = None


class SendScenarioInvoiceResponse(BaseModel):
    message_id: str | None = None
    bill_id: str | None = None
    extra_message_ids: list[str] | None = None
    chat_message_ids: list[str] | None = None


class SendScenarioChatRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class SendScenarioChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: str
    thread_id: str
    from_: Literal["tenant", "counterparty"] = Field(alias="from")
    text: str
    sent_at: str


class CardSwipeRequest(BaseModel):
    merchant_id: str = Field(min_length=1)
    amount_vnd: int = Field(ge=1)


class CardSwipeResponse(BaseModel):
    approved: bool
    reason: Literal["wrong_merchant", "already_used", "over_amount"] | None


class ClockResponse(BaseModel):
    now: str


class ClockAdvanceRequest(BaseModel):
    to: str = Field(min_length=1)

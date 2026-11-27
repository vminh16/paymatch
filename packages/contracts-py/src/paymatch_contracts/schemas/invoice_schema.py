# generated — do not edit

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import (
    approval_summary_schema,
    brief_schema,
    channel_schema,
    escrow_status_schema,
    invoice_line_schema,
    invoice_source_schema,
    invoice_status_schema,
    invoice_type_schema,
    local_date_schema,
    payment_intent_status_schema,
    reason_code_schema,
    severity_schema,
    signed_money_vnd_schema,
    timestamp_schema,
    untrusted_text_schema,
)


class Format(StrEnum):
    xml = 'xml'
    pdf = 'pdf'
    image = 'image'


class Relation(StrEnum):
    replace = 'replace'
    adjust = 'adjust'
    replace_multiple = 'replace_multiple'
    adjust_multiple = 'adjust_multiple'
    trade_discount = 'trade_discount'


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


class InvoiceEscrowSummary(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    escrow_id: Annotated[str, Field(pattern='^esc_[0-9A-HJKMNP-TV-Z]{26}$')]
    status: escrow_status_schema.EscrowStatus


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


class ManualFieldsMeta(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    entered_by: Annotated[str, Field(pattern='^usr_[0-9A-HJKMNP-TV-Z]{26}$')]
    entered_at: timestamp_schema.Timestamp


class InvoiceDocumentMeta(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    document_id: Annotated[str, Field(pattern='^doc_[0-9A-HJKMNP-TV-Z]{26}$')]
    format: Format
    sha256: Annotated[str, Field(pattern='^[0-9a-f]{64}$')]
    received_at: timestamp_schema.Timestamp


class VatBreakdownItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    vat_rate: str
    taxable_vnd: signed_money_vnd_schema.SignedMoneyVnd
    vat_vnd: signed_money_vnd_schema.SignedMoneyVnd


class RelatedInvoice(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    relation: Relation
    symbol: str
    number: str
    issued_on: local_date_schema.LocalDate


class UntrustedOtherInfoItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    field: str
    value: untrusted_text_schema.UntrustedText


class UntrustedMessageItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    message_id: Annotated[str, Field(pattern='^msg_[0-9A-HJKMNP-TV-Z]{26}$')]
    channel: Channel
    received_at: timestamp_schema.Timestamp
    body: untrusted_text_schema.UntrustedText


class InvoiceUntrustedFields(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    seller_name: untrusted_text_schema.UntrustedText
    seller_address: untrusted_text_schema.UntrustedText
    seller_bank_account: UntrustedSellerBankAccount | None
    payment_terms: untrusted_text_schema.UntrustedText | None
    other_info: list[UntrustedOtherInfoItem]
    messages: list[UntrustedMessageItem]


class FindingSummaryItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    bot_id: str
    severity: severity_schema.Severity
    reason_codes: Annotated[list[reason_code_schema.ReasonCode], Field(min_length=1)]


class InvoicePaymentSummary(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=True,
    )
    payment_intent_id: Annotated[str, Field(pattern='^pi_[0-9A-HJKMNP-TV-Z]{26}$')]
    status: payment_intent_status_schema.PaymentIntentStatus
    channel: channel_schema.Channel
    settled_at: timestamp_schema.Timestamp | None


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
    issued_on: local_date_schema.LocalDate | None
    invoice_type: invoice_type_schema.InvoiceType
    total_vnd: signed_money_vnd_schema.SignedMoneyVnd | None
    status: invoice_status_schema.InvoiceStatus
    severity: severity_schema.Severity | None
    reason_codes: list[reason_code_schema.ReasonCode]
    verification_required: bool
    due_on: local_date_schema.LocalDate | None
    scheduled_for: local_date_schema.LocalDate | None
    updated_at: timestamp_schema.Timestamp
    source: invoice_source_schema.InvoiceSource
    duplicate_of: Annotated[str | None, Field(pattern='^inv_[0-9A-HJKMNP-TV-Z]{26}$')]
    manual_fields: ManualFieldsMeta | None
    document: Annotated[InvoiceDocumentMeta, Field(title='InvoiceDocumentMeta')]
    buyer_tax_id: str
    currency: Literal['VND']
    subtotal_vnd: signed_money_vnd_schema.SignedMoneyVnd | None
    vat_total_vnd: signed_money_vnd_schema.SignedMoneyVnd | None
    vat_breakdown: list[VatBreakdownItem]
    tax_authority_code: str | None
    einvoice_provider_tax_id: str | None
    related_invoice: RelatedInvoice | None
    lines: list[invoice_line_schema.InvoiceLine]
    untrusted: Annotated[InvoiceUntrustedFields, Field(title='InvoiceUntrustedFields')]
    brief: brief_schema.Brief | None
    findings_summary: list[FindingSummaryItem]
    approval: approval_summary_schema.ApprovalSummary | None
    payment: InvoicePaymentSummary | None
    escrow: InvoiceEscrowSummary | None
    allowed_actions: list[AllowedAction]
    etag: str

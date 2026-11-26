"""Pure domain models, snapshots, and errors for Payment Gate (zero I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from paymatch_contracts.gate import (
    AllowedMethod,
    Channel,
    Code as GateReasonCode,
    EscrowStatus,
    GateDecision,
    Layer as GateReasonLayer,
    PaymentIntentStatus,
)

ApprovalMethod = Literal["single", "bulk", "mandate"]
MandateMode = Literal["review_only", "ask_first", "auto_pay"]
VendorAccountKind = Literal["bank_account", "card_merchant"]
VendorAccountStatus = Literal["verified", "escrow_only", "retired"]
KillSwitchScope = Literal["indicator", "tenant", "bot", "tool", "auto_pay_global"]
IndicatorKind = Literal["account_hash", "tax_id", "phone", "card_id", "merchant_id"]


@dataclass(frozen=True, slots=True)
class GateReasonItem:
    code: GateReasonCode
    layer: GateReasonLayer
    detail: str


@dataclass(frozen=True, slots=True)
class VerificationRecord:
    called_phone_on_file: bool
    result: str
    note: str | None = None
    at: str | None = None

    def is_confirmed(self) -> bool:
        return self.called_phone_on_file is True and self.result == "confirmed"


@dataclass(frozen=True, slots=True)
class InvoiceSnapshot:
    invoice_id: str
    tenant_id: str
    vendor_id: str | None
    purchase_order_id: str | None
    seller_tax_id: str
    symbol: str
    number: str
    invoice_type: str
    total_vnd: int | None
    status: str
    severity: str | None
    reason_codes: tuple[str, ...]
    document_sha256: str


@dataclass(frozen=True, slots=True)
class VendorSnapshot:
    vendor_id: str
    tenant_id: str
    name: str
    tax_id: str
    phone_on_file: str | None
    status: str


@dataclass(frozen=True, slots=True)
class VendorAccountSnapshot:
    vendor_account_id: str
    vendor_id: str
    tenant_id: str
    kind: str
    bank_code: str | None
    bank_name: str | None
    account_number: str | None
    merchant_id: str | None
    account_name: str
    status: str


@dataclass(frozen=True, slots=True)
class ApprovalSnapshot:
    approval_id: str
    tenant_id: str
    invoice_id: str | None
    purchase_order_id: str | None
    source_invoice_id: str | None
    job_id: str | None
    status: str
    method: str
    amount_vnd: int
    payee_account_id: str
    channel: str
    intent_hash: str
    approver_user_id: str | None = None
    mandate_version: int | None = None
    bulk_batch_id: str | None = None
    verification: VerificationRecord | None = None


@dataclass(frozen=True, slots=True)
class ChannelRule:
    invoice_type: str
    channel: str


@dataclass(frozen=True, slots=True)
class BulkApprovableRule:
    reason_codes: tuple[str, ...]
    max_amount_vnd: int


@dataclass(frozen=True, slots=True)
class MandateSnapshot:
    mandate_id: str
    tenant_id: str
    version: int
    mode: str
    per_invoice_vnd: int
    per_day_vnd: int
    auto_pay_vendor_ids: frozenset[str]
    channel_rules: tuple[ChannelRule, ...]
    bulk_approvable: tuple[BulkApprovableRule, ...]
    auto_pay_window_start: str
    auto_pay_window_end: str


@dataclass(frozen=True, slots=True)
class PlatformLimitsSnapshot:
    auto_pay_per_invoice_vnd: int
    auto_pay_per_day_vnd: int


@dataclass(frozen=True, slots=True)
class KillSwitchSnapshot:
    kill_switch_id: str
    scope: str
    target_id: str | None
    indicator_kind: str | None = None
    value_hash: str | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class PolicyState:
    available: bool
    platform_limits: PlatformLimitsSnapshot | None = None
    kill_switches: tuple[KillSwitchSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class IndicatorRef:
    kind: str
    value_hash: str


@dataclass(frozen=True, slots=True)
class RiskSignals:
    hard_block_hits: tuple[IndicatorRef, ...] = ()
    cross_alert_hits: tuple[IndicatorRef, ...] = ()
    matched_indicator_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class DailyBudgetSnapshot:
    budget_date: date
    auto_pay_used_vnd: int = 0
    auto_pay_reserved_vnd: int = 0
    total_paid_vnd: int = 0


@dataclass(frozen=True, slots=True)
class PurchaseOrderSnapshot:
    purchase_order_id: str
    tenant_id: str
    vendor_id: str
    store_id: str
    total_vnd: int
    status: str


@dataclass(frozen=True, slots=True)
class GoodsReceiptSnapshot:
    goods_receipt_id: str
    tenant_id: str
    purchase_order_id: str
    store_id: str


@dataclass(frozen=True, slots=True)
class PaymentIntentRecord:
    payment_intent_id: str
    tenant_id: str
    invoice_id: str | None
    purchase_order_id: str | None
    intent_hash: str
    approval_id: str
    approval_method: str
    budget_date: date | None
    payee_account_id: str
    channel: Channel
    amount_vnd: int
    status: PaymentIntentStatus
    gate_reasons: tuple[GateReasonItem, ...]
    rail_txn_id: str | None
    failure_code: str | None
    transfer_memo: str
    authorized_at: datetime | None
    executed_at: datetime | None
    settled_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    stuck_notified_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EscrowRecord:
    escrow_id: str
    tenant_id: str
    purchase_order_id: str
    vendor_account_id: str
    approval_id: str
    amount_vnd: int
    status: EscrowStatus
    source_invoice_id: str | None
    release_invoice_id: str | None
    goods_receipt_id: str | None
    rail_escrow_id: str | None
    failure_code: str | None
    expires_on: date
    created_at: datetime
    released_at: datetime | None
    refunded_at: datetime | None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    decision: GateDecision
    allowed_methods: tuple[AllowedMethod, ...]
    verification_required: bool
    intent_hash: str
    payee_account_id: str | None
    amount_vnd: int
    channel: Channel
    reasons: tuple[GateReasonItem, ...]
    evaluated_at: datetime
    kill_switch_blocked: bool = False
    policy_unavailable: bool = False


class GateError(Exception):
    """Base domain/application error for Payment Gate."""


class PolicyUnavailableError(GateError):
    """Raised when control.policies cannot be read (fail-closed)."""


class ResourceNotFoundError(GateError):
    """Raised when a referenced invoice/PO/approval/intent/escrow is not found."""


class TenantMismatchError(GateError):
    """Raised when caller-supplied tenant_id does not match the DB resource owner."""


class InvalidStateTransitionError(GateError):
    """Raised when a state machine transition is not allowed."""

    def __init__(self, message: str, current_status: str | None = None) -> None:
        super().__init__(message)
        self.current_status = current_status


class GateDeniedError(GateError):
    """Raised when Payment Gate denies creating or executing a payment/escrow."""

    def __init__(
        self,
        reasons: tuple[GateReasonItem, ...],
        *,
        kill_switch_blocked: bool = False,
        policy_unavailable: bool = False,
        payment_intent: PaymentIntentRecord | None = None,
        detail: str | None = None,
    ) -> None:
        msg = detail or (reasons[0].detail if reasons else "Payment Gate denied request.")
        super().__init__(msg)
        self.reasons = reasons
        self.kill_switch_blocked = kill_switch_blocked
        self.policy_unavailable = policy_unavailable
        self.payment_intent = payment_intent
        self.detail = msg

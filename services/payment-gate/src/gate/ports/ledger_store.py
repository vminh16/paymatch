"""LedgerStore port interface (sole writer for schema `ledger`)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from gate.domain.models import (
    DailyBudgetSnapshot,
    EscrowRecord,
    EvaluationResult,
    PaymentIntentRecord,
)


@dataclass(frozen=True, slots=True)
class RailTransactionRecord:
    rail_tx_pk: str
    tenant_id: str
    payment_intent_id: str | None
    escrow_id: str | None
    channel: str
    operation: str
    idempotency_key: str
    rail_ref_id: str | None
    status: str
    failure_code: str | None
    request_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CreateIntentOutcome:
    intent: PaymentIntentRecord
    created: bool  # True -> 201 Created, False -> 200 OK (idempotent existing active/settled)


@dataclass(frozen=True, slots=True)
class CreateEscrowOutcome:
    escrow: EscrowRecord
    created: bool  # True -> 201 Created, False -> 200 OK (idempotent existing for approval_id)


@dataclass(frozen=True, slots=True)
class ExecutePrepareOutcome:
    intent: PaymentIntentRecord
    should_call_rail: bool
    denied_result: EvaluationResult | None = None
    request_payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class EscrowActionPrepareOutcome:
    escrow: EscrowRecord
    should_call_rail: bool
    denied_result: EvaluationResult | None = None


@dataclass(frozen=True, slots=True)
class VerifiedExecutionTuple:
    invoice_id: str
    document_sha256: str
    payee_account_id: str
    amount_vnd: int
    channel: str
    approval_method: str
    intent_hash: str


class LedgerStore(Protocol):
    def check_required_relations(self) -> bool: ...

    def has_settled_ledger_for_invoice(self, invoice_id: str) -> bool: ...

    def is_approval_tainted(self, approval_id: str) -> bool:
        """True if approval_id already produced a failed, denied, or settled intent (B5)."""
        ...

    def get_open_escrow_for_po(self, purchase_order_id: str) -> EscrowRecord | None: ...

    def get_daily_budget(self, tenant_id: str, budget_date: date) -> DailyBudgetSnapshot: ...

    def get_intent(self, payment_intent_id: str) -> PaymentIntentRecord | None: ...

    def list_intents(
        self,
        *,
        tenant_id: str,
        invoice_id: str | None = None,
        statuses: tuple[str, ...] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[PaymentIntentRecord], str | None]: ...

    def create_authorized_intent(
        self,
        *,
        tenant_id: str,
        invoice_id: str,
        purchase_order_id: str | None,
        document_sha256: str,
        approval_id: str,
        approval_method: str,
        budget_date: date,
        payee_account_id: str,
        channel: str,
        amount_vnd: int,
        intent_hash: str,
        transfer_memo: str,
        now: datetime,
        expires_at: datetime,
        trace_id: str | None,
        validate_with_locked_budget: Callable[[DailyBudgetSnapshot, bool, bool], EvaluationResult],
    ) -> CreateIntentOutcome:
        """Atomically check active intent + cross-channel claim + taint, lock daily_budget, validate, and authorize or deny.

        Callback receives (locked_budget, has_other_invoice_claim, approval_tainted).
        """
        ...

    def prepare_execute_intent(
        self,
        *,
        payment_intent_id: str,
        now: datetime,
        exec_date: date,
        trace_id: str | None,
        reevaluate: Callable[
            [PaymentIntentRecord, DailyBudgetSnapshot, bool],
            tuple[EvaluationResult, VerifiedExecutionTuple | None],
        ],
        build_rail_request: Callable[[PaymentIntentRecord], tuple[str, dict[str, Any]]],
    ) -> ExecutePrepareOutcome:
        """Lock intent, handle midnight rollover to exec_date (B4), re-evaluate & verify full tuple
        against intent + token (B5), consume token, transition authorized->executing, or deny."""
        ...

    def finalize_intent_settled(
        self,
        *,
        payment_intent_id: str,
        rail_txn_id: str,
        settled_at: datetime,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> PaymentIntentRecord: ...

    def finalize_intent_failed(
        self,
        *,
        payment_intent_id: str,
        rail_txn_id: str | None,
        failure_code: str,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> PaymentIntentRecord: ...

    def cancel_authorized_intent(
        self,
        *,
        payment_intent_id: str,
        reason: str,
        now: datetime,
        trace_id: str | None,
    ) -> PaymentIntentRecord: ...

    def expire_stale_authorized_intents(self, *, now: datetime) -> list[PaymentIntentRecord]: ...

    def list_executing_intents(self) -> list[tuple[PaymentIntentRecord, RailTransactionRecord | None]]: ...

    def record_intent_rail_ref(
        self, *, payment_intent_id: str, rail_ref_id: str, now: datetime
    ) -> None: ...

    def mark_intent_stuck_notified(self, *, payment_intent_id: str, now: datetime) -> bool: ...

    # --- Escrows ---

    def get_escrow(self, escrow_id: str) -> EscrowRecord | None: ...

    def get_escrow_by_approval_id(self, approval_id: str) -> EscrowRecord | None: ...

    def create_pending_escrow_atomic(
        self,
        *,
        approval_id: str,
        purchase_order_id: str,
        tenant_id: str,
        vendor_account_id: str,
        amount_vnd: int,
        source_invoice_id: str | None,
        expires_on: date,
        now: datetime,
        request_payload: dict[str, Any],
        validate_with_open_po: Callable[[bool], EvaluationResult],
    ) -> CreateEscrowOutcome:
        """Atomically check B2 approval_id idempotency FIRST, then PO lock + open-PO check + insert."""
        ...

    def finalize_escrow_held(
        self,
        *,
        escrow_id: str,
        rail_escrow_id: str,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> EscrowRecord: ...

    def finalize_escrow_failed(
        self,
        *,
        escrow_id: str,
        failure_code: str,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> EscrowRecord: ...

    def prepare_escrow_release(
        self,
        *,
        escrow_id: str,
        release_invoice_id: str | None,
        release_approval_id: str,
        goods_receipt_id: str,
        now: datetime,
        reevaluate: Callable[[EscrowRecord, bool], EvaluationResult],
    ) -> EscrowActionPrepareOutcome:
        """Atomically lock escrow, claim release_invoice_id across ALL channels (B1),
        persist pending_action='release' + rail_transactions BEFORE calling rail."""
        ...

    def finalize_escrow_released(
        self,
        *,
        escrow_id: str,
        budget_date: date,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> EscrowRecord: ...

    def prepare_escrow_refund(
        self,
        *,
        escrow_id: str,
        reason: str,
        now: datetime,
    ) -> EscrowActionPrepareOutcome:
        """Atomically lock escrow and persist pending_action='refund' + rail_transactions before rail call."""
        ...

    def finalize_escrow_refunded(
        self,
        *,
        escrow_id: str,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> EscrowRecord: ...

    def list_pending_escrows(self) -> list[tuple[EscrowRecord, RailTransactionRecord | None]]: ...

    def list_escrows_with_pending_action(
        self,
    ) -> list[tuple[EscrowRecord, RailTransactionRecord | None]]: ...

    def mark_escrow_stuck_notified(self, *, escrow_id: str, now: datetime) -> bool: ...

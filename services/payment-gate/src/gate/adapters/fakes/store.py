"""Lightweight in-memory fake stores for fast HTTP/auth/poller tests.

All complex DB locking, uniqueness, and mutation invariants are tested against real
Postgres 16 in `tests/test_db_invariants.py`.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date, datetime
from typing import Any

from paymatch_contracts.gate import (
    Channel,
    Code as GateReasonCode,
    EscrowStatus,
    GateDecision,
    Layer as GateReasonLayer,
    PaymentIntentStatus,
)

from gate.domain.models import (
    ApprovalSnapshot,
    DailyBudgetSnapshot,
    EscrowRecord,
    EvaluationResult,
    GateDeniedError,
    GateReasonItem,
    GoodsReceiptSnapshot,
    IndicatorRef,
    InvalidStateTransitionError,
    InvoiceSnapshot,
    MandateSnapshot,
    PaymentIntentRecord,
    PlatformLimitsSnapshot,
    PolicyState,
    PolicyUnavailableError,
    PurchaseOrderSnapshot,
    ResourceNotFoundError,
    RiskSignals,
    VendorAccountSnapshot,
    VendorSnapshot,
)
from gate.domain.state_machine import require_escrow_transition, require_intent_transition
from gate.ids import new_id
from gate.ports.ledger_store import (
    CreateEscrowOutcome,
    CreateIntentOutcome,
    EscrowActionPrepareOutcome,
    ExecutePrepareOutcome,
    RailTransactionRecord,
    VerifiedExecutionTuple,
)


class InMemoryCoreReadStore:
    def __init__(self) -> None:
        self.tenant_wallets: dict[str, str] = {}
        self.owner_users: set[tuple[str, str]] = set()
        self.invoices: dict[str, InvoiceSnapshot] = {}
        self.vendors: dict[tuple[str, str], VendorSnapshot] = {}
        self.vendor_accounts: dict[tuple[str, str], VendorAccountSnapshot] = {}
        self.mandates: dict[str, MandateSnapshot] = {}
        self.suspended_vendors: set[tuple[str, str]] = set()
        self.approvals: dict[str, ApprovalSnapshot] = {}
        self.latest_jobs: dict[tuple[str, str], str] = {}
        self.purchase_orders: dict[str, PurchaseOrderSnapshot] = {}
        self.goods_receipts: dict[str, GoodsReceiptSnapshot] = {}
        self.policy_state: PolicyState = PolicyState(
            available=True,
            platform_limits=PlatformLimitsSnapshot(
                auto_pay_per_invoice_vnd=30_000_000,
                auto_pay_per_day_vnd=50_000_000,
            ),
            kill_switches=(),
        )
        self.hard_blocks: set[tuple[str, str]] = set()
        self.cross_alerts: set[tuple[str, str]] = set()
        self.indicator_ids: dict[tuple[str, str], str] = {}
        self.healthy: bool = True
        self.risk_readable: bool = True

    def check_required_relations(self) -> bool:
        return self.healthy and self.risk_readable

    def get_tenant_wallet_id(self, tenant_id: str) -> str | None:
        return self.tenant_wallets.get(tenant_id)

    def is_tenant_owner(self, tenant_id: str, user_id: str) -> bool:
        return (tenant_id, user_id) in self.owner_users

    def get_invoice(self, invoice_id: str) -> InvoiceSnapshot | None:
        return self.invoices.get(invoice_id)

    def get_vendor(self, tenant_id: str, vendor_id: str) -> VendorSnapshot | None:
        return self.vendors.get((tenant_id, vendor_id))

    def get_vendor_by_tax_id(self, tenant_id: str, tax_id: str) -> VendorSnapshot | None:
        return next(
            (v for (tid, _), v in self.vendors.items() if tid == tenant_id and v.tax_id == tax_id),
            None,
        )

    def list_vendor_accounts(
        self, tenant_id: str, vendor_id: str
    ) -> tuple[VendorAccountSnapshot, ...]:
        return tuple(
            sorted(
                (a for (tid, _), a in self.vendor_accounts.items() if tid == tenant_id and a.vendor_id == vendor_id),
                key=lambda a: a.vendor_account_id,
            )
        )

    def get_vendor_account(self, tenant_id: str, vendor_account_id: str) -> VendorAccountSnapshot | None:
        return self.vendor_accounts.get((tenant_id, vendor_account_id))

    def get_latest_mandate(self, tenant_id: str) -> MandateSnapshot | None:
        return self.mandates.get(tenant_id)

    def is_vendor_suspended(self, tenant_id: str, vendor_id: str) -> bool:
        return (tenant_id, vendor_id) in self.suspended_vendors

    def get_approval(self, approval_id: str) -> ApprovalSnapshot | None:
        return self.approvals.get(approval_id)

    def get_latest_completed_job_id(self, tenant_id: str, invoice_id: str) -> str | None:
        return self.latest_jobs.get((tenant_id, invoice_id))

    def get_purchase_order(self, purchase_order_id: str) -> PurchaseOrderSnapshot | None:
        return self.purchase_orders.get(purchase_order_id)

    def get_goods_receipt(self, goods_receipt_id: str) -> GoodsReceiptSnapshot | None:
        return self.goods_receipts.get(goods_receipt_id)

    def load_policy_state(self) -> PolicyState:
        return self.policy_state

    def check_risk_signals(self, indicators: Sequence[IndicatorRef]) -> RiskSignals:
        if not self.risk_readable:
            raise PolicyUnavailableError("Risk tables unavailable (fail-closed).")
        hard_hits = tuple(i for i in indicators if (i.kind, i.value_hash.lower()) in self.hard_blocks)
        cross_hits = tuple(i for i in indicators if (i.kind, i.value_hash.lower()) in self.cross_alerts)
        matched_ids = frozenset(
            self.indicator_ids[(i.kind, i.value_hash.lower())]
            for i in indicators
            if (i.kind, i.value_hash.lower()) in self.indicator_ids
        )
        return RiskSignals(hard_block_hits=hard_hits, cross_alert_hits=cross_hits, matched_indicator_ids=matched_ids)


class InMemoryLedgerStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.intents: dict[str, PaymentIntentRecord] = {}
        self.tokens: dict[str, tuple[str, VerifiedExecutionTuple]] = {}
        self.invoice_claims: dict[str, tuple[str, str, str]] = {}  # invoice_id -> (kind, owner_id, status)
        self.ledger_entries: list[dict[str, Any]] = []
        self.escrows: dict[str, EscrowRecord] = {}
        self.budgets: dict[tuple[str, date], DailyBudgetSnapshot] = {}
        self.rail_txs: dict[str, RailTransactionRecord] = {}
        self.outbox: list[dict[str, Any]] = []
        self.healthy: bool = True

    def _emit(self, event_type: str, occurred_at: datetime, tenant_id: str | None, trace_id: str | None, data: dict[str, Any]) -> None:
        self.outbox.append(
            {
                "seq": len(self.outbox) + 1,
                "event_id": new_id("evt"),
                "type": event_type,
                "schema_version": 1,
                "occurred_at": occurred_at.isoformat(),
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "data": data,
            }
        )

    def _budget(self, tenant_id: str, d: date) -> DailyBudgetSnapshot:
        return self.budgets.get((tenant_id, d), DailyBudgetSnapshot(budget_date=d))

    def _release_reserve(self, intent: PaymentIntentRecord) -> None:
        if intent.approval_method == "mandate" and intent.budget_date is not None:
            b = self._budget(intent.tenant_id, intent.budget_date)
            self.budgets[(intent.tenant_id, intent.budget_date)] = replace(
                b, auto_pay_reserved_vnd=max(0, b.auto_pay_reserved_vnd - intent.amount_vnd)
            )

    def _release_claim_for_owner(self, owner_id: str) -> None:
        for inv_id, (_, oid, st) in list(self.invoice_claims.items()):
            if oid == owner_id and st == "claimed":
                del self.invoice_claims[inv_id]

    def check_required_relations(self) -> bool:
        return self.healthy

    def has_settled_ledger_for_invoice(self, invoice_id: str) -> bool:
        with self._lock:
            return any(e["invoice_id"] == invoice_id and e["entry_type"] in ("settled", "escrow_released") for e in self.ledger_entries)

    def has_active_or_settled_claim_for_invoice(self, invoice_id: str) -> bool:
        with self._lock:
            return invoice_id in self.invoice_claims

    def is_approval_tainted(self, approval_id: str) -> bool:
        with self._lock:
            return any(
                i.approval_id == approval_id
                and i.status in (PaymentIntentStatus.failed, PaymentIntentStatus.denied, PaymentIntentStatus.settled)
                for i in self.intents.values()
            )

    def get_open_escrow_for_po(self, purchase_order_id: str) -> EscrowRecord | None:
        with self._lock:
            return next(
                (e for e in self.escrows.values() if e.purchase_order_id == purchase_order_id and e.status in (EscrowStatus.pending, EscrowStatus.held)),
                None,
            )

    def get_daily_budget(self, tenant_id: str, budget_date: date) -> DailyBudgetSnapshot:
        with self._lock:
            return self._budget(tenant_id, budget_date)

    def get_intent(self, payment_intent_id: str) -> PaymentIntentRecord | None:
        with self._lock:
            return self.intents.get(payment_intent_id)

    def list_intents(
        self,
        *,
        tenant_id: str,
        invoice_id: str | None = None,
        statuses: tuple[str, ...] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[PaymentIntentRecord], str | None]:
        with self._lock:
            items = [i for i in self.intents.values() if i.tenant_id == tenant_id]
            if invoice_id is not None:
                items = [i for i in items if i.invoice_id == invoice_id]
            if statuses:
                items = [i for i in items if i.status.value in statuses]
            items.sort(key=lambda i: (i.created_at, i.payment_intent_id), reverse=True)
            offset = int(cursor) if cursor else 0
            page = items[offset : offset + limit]
            return page, (str(offset + limit) if offset + limit < len(items) else None)

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
        with self._lock:
            for existing in self.intents.values():
                if existing.invoice_id == invoice_id and existing.status in (
                    PaymentIntentStatus.authorized,
                    PaymentIntentStatus.executing,
                    PaymentIntentStatus.settled,
                ):
                    return CreateIntentOutcome(intent=existing, created=False)

            budget = self._budget(tenant_id, budget_date)
            eval_res = validate_with_locked_budget(
                budget, invoice_id in self.invoice_claims, self.is_approval_tainted(approval_id)
            )
            intent_id = new_id("pi")
            if eval_res.decision != GateDecision.ALLOW:
                denied = PaymentIntentRecord(
                    payment_intent_id=intent_id,
                    tenant_id=tenant_id,
                    invoice_id=invoice_id,
                    purchase_order_id=purchase_order_id,
                    document_sha256=document_sha256,
                    intent_hash=eval_res.intent_hash,
                    approval_id=approval_id,
                    approval_method=approval_method,
                    budget_date=None,
                    payee_account_id=payee_account_id,
                    channel=Channel(channel),
                    amount_vnd=amount_vnd,
                    status=PaymentIntentStatus.denied,
                    gate_reasons=eval_res.reasons,
                    rail_txn_id=None,
                    failure_code=None,
                    transfer_memo=transfer_memo,
                    authorized_at=None,
                    executed_at=None,
                    settled_at=None,
                    expires_at=None,
                    created_at=now,
                )
                self.intents[intent_id] = denied
                self._emit(
                    "payment.denied",
                    now,
                    tenant_id,
                    trace_id,
                    {
                        "payment_intent_id": intent_id,
                        "invoice_id": invoice_id,
                        "gate_reasons": [{"code": r.code.value, "layer": r.layer.value, "detail": r.detail} for r in eval_res.reasons],
                    },
                )
                raise GateDeniedError(
                    eval_res.reasons,
                    kill_switch_blocked=eval_res.kill_switch_blocked,
                    policy_unavailable=eval_res.policy_unavailable,
                    payment_intent=denied,
                )

            rec = PaymentIntentRecord(
                payment_intent_id=intent_id,
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                purchase_order_id=purchase_order_id,
                document_sha256=document_sha256,
                intent_hash=eval_res.intent_hash,
                approval_id=approval_id,
                approval_method=approval_method,
                budget_date=budget_date,
                payee_account_id=payee_account_id,
                channel=Channel(channel),
                amount_vnd=amount_vnd,
                status=PaymentIntentStatus.authorized,
                gate_reasons=(),
                rail_txn_id=None,
                failure_code=None,
                transfer_memo=transfer_memo,
                authorized_at=now,
                executed_at=None,
                settled_at=None,
                expires_at=expires_at,
                created_at=now,
            )
            self.intents[intent_id] = rec
            self.invoice_claims[invoice_id] = ("payment_intent", intent_id, "claimed")
            self.tokens[intent_id] = (
                "issued",
                VerifiedExecutionTuple(
                    invoice_id=invoice_id,
                    document_sha256=document_sha256,
                    payee_account_id=payee_account_id,
                    amount_vnd=amount_vnd,
                    channel=channel,
                    approval_method=approval_method,
                    intent_hash=eval_res.intent_hash,
                ),
            )
            if approval_method == "mandate":
                self.budgets[(tenant_id, budget_date)] = replace(
                    budget, auto_pay_reserved_vnd=budget.auto_pay_reserved_vnd + amount_vnd
                )
            self._emit(
                "payment.authorized",
                now,
                tenant_id,
                trace_id,
                {"payment_intent_id": intent_id, "invoice_id": invoice_id, "amount_vnd": amount_vnd, "channel": channel},
            )
            return CreateIntentOutcome(intent=rec, created=True)

    def prepare_execute_intent(
        self,
        *,
        payment_intent_id: str,
        now: datetime,
        exec_date: date,
        trace_id: str | None,
        reevaluate: Callable[[PaymentIntentRecord, DailyBudgetSnapshot, bool], tuple[EvaluationResult, VerifiedExecutionTuple | None]],
        build_rail_request: Callable[[PaymentIntentRecord], tuple[str, dict[str, Any]]],
    ) -> ExecutePrepareOutcome:
        with self._lock:
            intent = self.intents.get(payment_intent_id)
            if intent is None:
                raise ResourceNotFoundError(f"PaymentIntent '{payment_intent_id}' not found.")
            if intent.status in (PaymentIntentStatus.executing, PaymentIntentStatus.settled):
                return ExecutePrepareOutcome(intent=intent, should_call_rail=False)
            if intent.status != PaymentIntentStatus.authorized:
                raise InvalidStateTransitionError(f"Cannot execute intent in status '{intent.status.value}'.", current_status=intent.status.value)
            if intent.expires_at is not None and now > intent.expires_at:
                self.intents[payment_intent_id] = replace(intent, status=PaymentIntentStatus.expired)
                if payment_intent_id in self.tokens:
                    self.tokens[payment_intent_id] = ("expired", self.tokens[payment_intent_id][1])
                self._release_claim_for_owner(payment_intent_id)
                self._release_reserve(intent)
                if intent.invoice_id:
                    self._emit("payment.expired", now, intent.tenant_id, trace_id, {"payment_intent_id": payment_intent_id, "invoice_id": intent.invoice_id, "reason": "AUTHORIZATION_TIMEOUT"})
                raise InvalidStateTransitionError("PaymentIntent authorization has expired.", current_status="expired")

            old_date = intent.budget_date or exec_date
            is_rollover = intent.approval_method == "mandate" and old_date != exec_date
            exec_budget = self._budget(intent.tenant_id, exec_date)
            already_reserved = intent.approval_method == "mandate" and not is_rollover
            eval_res, verified = reevaluate(intent, exec_budget, already_reserved)

            tok_status, tok_tuple = self.tokens.get(payment_intent_id, ("missing", None))
            mismatch = None
            if eval_res.decision == GateDecision.ALLOW:
                intent_tuple = VerifiedExecutionTuple(
                    invoice_id=intent.invoice_id or "",
                    document_sha256=intent.document_sha256,
                    payee_account_id=intent.payee_account_id,
                    amount_vnd=intent.amount_vnd,
                    channel=intent.channel.value,
                    approval_method=intent.approval_method,
                    intent_hash=intent.intent_hash,
                )
                if tok_status != "issued" or verified is None or not (verified == intent_tuple == tok_tuple):
                    mismatch = GateReasonItem(code=GateReasonCode.APPROVAL_STALE, layer=GateReasonLayer.hard_rule, detail="Execution tuple mismatch.")

            if eval_res.decision != GateDecision.ALLOW or mismatch is not None:
                final_eval = eval_res if eval_res.decision != GateDecision.ALLOW else replace(eval_res, decision=GateDecision.DENY, reasons=(mismatch,))
                denied = replace(intent, status=PaymentIntentStatus.denied, gate_reasons=final_eval.reasons)
                self.intents[payment_intent_id] = denied
                if payment_intent_id in self.tokens:
                    self.tokens[payment_intent_id] = ("revoked", self.tokens[payment_intent_id][1])
                self._release_claim_for_owner(payment_intent_id)
                self._release_reserve(intent)
                if intent.invoice_id:
                    self._emit("payment.denied", now, intent.tenant_id, trace_id, {"payment_intent_id": payment_intent_id, "invoice_id": intent.invoice_id, "gate_reasons": [{"code": r.code.value, "layer": r.layer.value, "detail": r.detail} for r in final_eval.reasons]})
                return ExecutePrepareOutcome(intent=denied, should_call_rail=False, denied_result=final_eval)

            if is_rollover:
                self._release_reserve(intent)
                self.budgets[(intent.tenant_id, exec_date)] = replace(exec_budget, auto_pay_reserved_vnd=exec_budget.auto_pay_reserved_vnd + intent.amount_vnd)

            self.tokens[payment_intent_id] = ("consumed", self.tokens[payment_intent_id][1])
            op, payload = build_rail_request(intent)
            executing = replace(intent, status=PaymentIntentStatus.executing, executed_at=now, budget_date=exec_date)
            self.intents[payment_intent_id] = executing
            self.rail_txs[payment_intent_id] = RailTransactionRecord(
                rail_tx_pk=new_id("rtx"), tenant_id=intent.tenant_id, payment_intent_id=payment_intent_id,
                escrow_id=None, channel=intent.channel.value, operation=op, idempotency_key=payment_intent_id,
                rail_ref_id=None, status="pending", failure_code=None, request_payload=payload,
            )
            return ExecutePrepareOutcome(intent=executing, should_call_rail=True, request_payload=payload)

    def finalize_intent_settled(self, *, payment_intent_id: str, rail_txn_id: str, settled_at: datetime, response_payload: dict[str, Any] | None, now: datetime, trace_id: str | None) -> PaymentIntentRecord:
        with self._lock:
            intent = self.intents[payment_intent_id]
            if intent.status != PaymentIntentStatus.executing:
                return intent
            require_intent_transition(intent.status, PaymentIntentStatus.settled)
            updated = replace(intent, status=PaymentIntentStatus.settled, rail_txn_id=rail_txn_id, failure_code=None, settled_at=settled_at)
            self.intents[payment_intent_id] = updated
            if intent.invoice_id:
                self.invoice_claims[intent.invoice_id] = ("payment_intent", payment_intent_id, "settled")
            if payment_intent_id in self.rail_txs:
                self.rail_txs[payment_intent_id] = replace(self.rail_txs[payment_intent_id], status="settled", rail_ref_id=rail_txn_id)
            bdate = intent.budget_date or settled_at.date()
            b = self._budget(intent.tenant_id, bdate)
            self.budgets[(intent.tenant_id, bdate)] = replace(
                b,
                auto_pay_reserved_vnd=(max(0, b.auto_pay_reserved_vnd - intent.amount_vnd) if intent.approval_method == "mandate" else b.auto_pay_reserved_vnd),
                auto_pay_used_vnd=(b.auto_pay_used_vnd + intent.amount_vnd if intent.approval_method == "mandate" else b.auto_pay_used_vnd),
                total_paid_vnd=b.total_paid_vnd + intent.amount_vnd,
            )
            self.ledger_entries.append({"entry_id": new_id("led"), "tenant_id": intent.tenant_id, "payment_intent_id": payment_intent_id, "invoice_id": intent.invoice_id, "entry_type": "settled", "amount_vnd": intent.amount_vnd, "rail_txn_id": rail_txn_id})
            if intent.invoice_id:
                self._emit("payment.executed", now, intent.tenant_id, trace_id, {"payment_intent_id": payment_intent_id, "invoice_id": intent.invoice_id, "rail_txn_id": rail_txn_id, "settled_at": settled_at.isoformat()})
            return updated

    def finalize_intent_failed(self, *, payment_intent_id: str, rail_txn_id: str | None, failure_code: str, response_payload: dict[str, Any] | None, now: datetime, trace_id: str | None) -> PaymentIntentRecord:
        with self._lock:
            intent = self.intents[payment_intent_id]
            if intent.status != PaymentIntentStatus.executing:
                return intent
            require_intent_transition(intent.status, PaymentIntentStatus.failed)
            updated = replace(intent, status=PaymentIntentStatus.failed, rail_txn_id=rail_txn_id or intent.rail_txn_id, failure_code=failure_code)
            self.intents[payment_intent_id] = updated
            self._release_claim_for_owner(payment_intent_id)
            self._release_reserve(intent)
            if payment_intent_id in self.rail_txs:
                self.rail_txs[payment_intent_id] = replace(self.rail_txs[payment_intent_id], status="failed", rail_ref_id=rail_txn_id, failure_code=failure_code)
            self.ledger_entries.append({"entry_id": new_id("led"), "tenant_id": intent.tenant_id, "payment_intent_id": payment_intent_id, "invoice_id": intent.invoice_id, "entry_type": "failed", "amount_vnd": intent.amount_vnd, "failure_code": failure_code})
            if intent.invoice_id:
                self._emit("payment.failed", now, intent.tenant_id, trace_id, {"payment_intent_id": payment_intent_id, "invoice_id": intent.invoice_id, "failure_code": failure_code})
            return updated

    def finalize_intent_denied_from_executing(self, *, payment_intent_id: str, reasons: tuple[GateReasonItem, ...], now: datetime, trace_id: str | None) -> PaymentIntentRecord:
        with self._lock:
            intent = self.intents[payment_intent_id]
            if intent.status != PaymentIntentStatus.executing:
                return intent
            require_intent_transition(intent.status, PaymentIntentStatus.denied)
            updated = replace(intent, status=PaymentIntentStatus.denied, gate_reasons=reasons)
            self.intents[payment_intent_id] = updated
            self._release_claim_for_owner(payment_intent_id)
            self._release_reserve(intent)
            if intent.invoice_id:
                self._emit("payment.denied", now, intent.tenant_id, trace_id, {"payment_intent_id": payment_intent_id, "invoice_id": intent.invoice_id, "gate_reasons": [{"code": r.code.value, "layer": r.layer.value, "detail": r.detail} for r in reasons]})
            return updated

    def cancel_authorized_intent(self, *, payment_intent_id: str, reason: str, now: datetime, trace_id: str | None) -> PaymentIntentRecord:
        with self._lock:
            intent = self.intents.get(payment_intent_id)
            if intent is None:
                raise ResourceNotFoundError(f"PaymentIntent '{payment_intent_id}' not found.")
            if intent.status != PaymentIntentStatus.authorized:
                raise InvalidStateTransitionError(f"Cannot cancel intent in status '{intent.status.value}'.", current_status=intent.status.value)
            updated = replace(intent, status=PaymentIntentStatus.expired)
            self.intents[payment_intent_id] = updated
            self._release_claim_for_owner(payment_intent_id)
            self._release_reserve(intent)
            if intent.invoice_id:
                self._emit("payment.expired", now, intent.tenant_id, trace_id, {"payment_intent_id": payment_intent_id, "invoice_id": intent.invoice_id, "reason": reason})
            return updated

    def expire_stale_authorized_intents(self, *, now: datetime) -> list[PaymentIntentRecord]:
        with self._lock:
            expired: list[PaymentIntentRecord] = []
            for pid, intent in list(self.intents.items()):
                if intent.status == PaymentIntentStatus.authorized and intent.expires_at is not None and intent.expires_at <= now:
                    updated = replace(intent, status=PaymentIntentStatus.expired)
                    self.intents[pid] = updated
                    self._release_claim_for_owner(pid)
                    self._release_reserve(intent)
                    if intent.invoice_id:
                        self._emit("payment.expired", now, intent.tenant_id, None, {"payment_intent_id": pid, "invoice_id": intent.invoice_id, "reason": "AUTHORIZATION_TIMEOUT"})
                    expired.append(updated)
            return expired

    def list_executing_intents(self) -> list[tuple[PaymentIntentRecord, RailTransactionRecord | None]]:
        with self._lock:
            return [(i, self.rail_txs.get(i.payment_intent_id)) for i in self.intents.values() if i.status == PaymentIntentStatus.executing]

    def record_intent_rail_ref(self, *, payment_intent_id: str, rail_ref_id: str, now: datetime) -> None:
        with self._lock:
            if payment_intent_id in self.rail_txs:
                self.rail_txs[payment_intent_id] = replace(self.rail_txs[payment_intent_id], rail_ref_id=rail_ref_id)
            if payment_intent_id in self.intents:
                self.intents[payment_intent_id] = replace(self.intents[payment_intent_id], rail_txn_id=self.intents[payment_intent_id].rail_txn_id or rail_ref_id)

    def mark_intent_stuck_notified(self, *, payment_intent_id: str, now: datetime) -> bool:
        with self._lock:
            intent = self.intents.get(payment_intent_id)
            if intent is None or intent.status != PaymentIntentStatus.executing or intent.stuck_notified_at is not None:
                return False
            self.intents[payment_intent_id] = replace(intent, stuck_notified_at=now)
            if intent.invoice_id:
                self._emit("payment.stuck", now, intent.tenant_id, None, {"payment_intent_id": payment_intent_id, "invoice_id": intent.invoice_id, "executing_since": (intent.executed_at or intent.created_at).isoformat()})
            return True

    # --- Escrows ---

    def get_escrow(self, escrow_id: str) -> EscrowRecord | None:
        with self._lock:
            return self.escrows.get(escrow_id)

    def get_escrow_by_approval_id(self, approval_id: str) -> EscrowRecord | None:
        with self._lock:
            return next((e for e in self.escrows.values() if e.approval_id == approval_id), None)

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
        with self._lock:
            existing = self.get_escrow_by_approval_id(approval_id)
            if existing is not None:
                return CreateEscrowOutcome(escrow=existing, created=False)
            has_open = self.get_open_escrow_for_po(purchase_order_id) is not None
            eval_res = validate_with_open_po(has_open)
            if eval_res.decision != GateDecision.ALLOW:
                raise GateDeniedError(eval_res.reasons, kill_switch_blocked=eval_res.kill_switch_blocked, policy_unavailable=eval_res.policy_unavailable)
            esc_id = new_id("esc")
            rec = EscrowRecord(
                escrow_id=esc_id, tenant_id=tenant_id, purchase_order_id=purchase_order_id,
                vendor_account_id=vendor_account_id, approval_id=approval_id, amount_vnd=amount_vnd,
                status=EscrowStatus.pending, source_invoice_id=source_invoice_id, release_invoice_id=None,
                goods_receipt_id=None, rail_escrow_id=None, failure_code=None, expires_on=expires_on,
                created_at=now, released_at=None, refunded_at=None,
            )
            self.escrows[esc_id] = rec
            self.rail_txs[esc_id] = RailTransactionRecord(
                rail_tx_pk=new_id("rtx"), tenant_id=tenant_id, payment_intent_id=None, escrow_id=esc_id,
                channel="escrow", operation="escrow_hold", idempotency_key=esc_id, rail_ref_id=None,
                status="pending", failure_code=None, request_payload={**request_payload, "idempotency_key": esc_id},
            )
            return CreateEscrowOutcome(escrow=rec, created=True)

    def finalize_escrow_held(self, *, escrow_id: str, rail_escrow_id: str, response_payload: dict[str, Any] | None, now: datetime, trace_id: str | None) -> EscrowRecord:
        with self._lock:
            esc = self.escrows[escrow_id]
            if esc.status != EscrowStatus.pending:
                return esc
            require_escrow_transition(esc.status, EscrowStatus.held)
            updated = replace(esc, status=EscrowStatus.held, rail_escrow_id=rail_escrow_id, failure_code=None)
            self.escrows[escrow_id] = updated
            self.ledger_entries.append({"entry_id": new_id("led"), "tenant_id": esc.tenant_id, "escrow_id": escrow_id, "invoice_id": esc.source_invoice_id, "entry_type": "escrow_held", "amount_vnd": esc.amount_vnd})
            self._emit("escrow.held", now, esc.tenant_id, trace_id, {"escrow_id": escrow_id, "purchase_order_id": esc.purchase_order_id, "source_invoice_id": esc.source_invoice_id})
            return updated

    def finalize_escrow_failed(self, *, escrow_id: str, failure_code: str, response_payload: dict[str, Any] | None, now: datetime, trace_id: str | None) -> EscrowRecord:
        with self._lock:
            esc = self.escrows[escrow_id]
            if esc.status != EscrowStatus.pending:
                return esc
            require_escrow_transition(esc.status, EscrowStatus.failed)
            updated = replace(esc, status=EscrowStatus.failed, failure_code=failure_code)
            self.escrows[escrow_id] = updated
            self.ledger_entries.append({"entry_id": new_id("led"), "tenant_id": esc.tenant_id, "escrow_id": escrow_id, "invoice_id": esc.source_invoice_id, "entry_type": "escrow_failed", "amount_vnd": esc.amount_vnd, "failure_code": failure_code})
            return updated

    def prepare_escrow_release(self, *, escrow_id: str, release_invoice_id: str | None, release_approval_id: str, goods_receipt_id: str, now: datetime, reevaluate: Callable[[EscrowRecord, bool], EvaluationResult]) -> EscrowActionPrepareOutcome:
        with self._lock:
            esc = self.escrows.get(escrow_id)
            if esc is None:
                raise ResourceNotFoundError(f"Escrow '{escrow_id}' not found.")
            if esc.status == EscrowStatus.held and esc.pending_action == "release":
                return EscrowActionPrepareOutcome(escrow=esc, should_call_rail=False)
            if esc.status != EscrowStatus.held or esc.pending_action is not None:
                raise InvalidStateTransitionError(f"Cannot release escrow in status '{esc.status.value}'.", current_status=esc.status.value)
            has_claim = release_invoice_id is not None and release_invoice_id in self.invoice_claims
            eval_res = reevaluate(esc, has_claim)
            if eval_res.decision != GateDecision.ALLOW:
                return EscrowActionPrepareOutcome(escrow=esc, should_call_rail=False, denied_result=eval_res)
            assert release_invoice_id is not None
            self.invoice_claims[release_invoice_id] = ("escrow_release", escrow_id, "claimed")
            updated = replace(esc, pending_action="release", release_invoice_id=release_invoice_id, release_approval_id=release_approval_id, goods_receipt_id=goods_receipt_id, action_started_at=now)
            self.escrows[escrow_id] = updated
            rel_key = f"rel_{escrow_id}"
            self.rail_txs[rel_key] = RailTransactionRecord(
                rail_tx_pk=new_id("rtx"), tenant_id=esc.tenant_id, payment_intent_id=None, escrow_id=escrow_id,
                channel="escrow", operation="escrow_release", idempotency_key=rel_key, rail_ref_id=esc.rail_escrow_id,
                status="pending", failure_code=None, request_payload={"idempotency_key": rel_key},
            )
            return EscrowActionPrepareOutcome(escrow=updated, should_call_rail=True)

    def abort_escrow_release(self, *, escrow_id: str, now: datetime) -> EscrowRecord:
        with self._lock:
            esc = self.escrows[escrow_id]
            self._release_claim_for_owner(escrow_id)
            updated = replace(esc, pending_action=None, release_invoice_id=None, release_approval_id=None, goods_receipt_id=None, action_started_at=None)
            self.escrows[escrow_id] = updated
            return updated

    def finalize_escrow_released(self, *, escrow_id: str, budget_date: date, response_payload: dict[str, Any] | None, now: datetime, trace_id: str | None) -> EscrowRecord:
        with self._lock:
            esc = self.escrows[escrow_id]
            if esc.status != EscrowStatus.held:
                return esc
            require_escrow_transition(esc.status, EscrowStatus.released)
            updated = replace(esc, status=EscrowStatus.released, pending_action=None, released_at=now)
            self.escrows[escrow_id] = updated
            if esc.release_invoice_id:
                self.invoice_claims[esc.release_invoice_id] = ("escrow_release", escrow_id, "settled")
            b = self._budget(esc.tenant_id, budget_date)
            self.budgets[(esc.tenant_id, budget_date)] = replace(b, total_paid_vnd=b.total_paid_vnd + esc.amount_vnd)
            self.ledger_entries.append({"entry_id": new_id("led"), "tenant_id": esc.tenant_id, "escrow_id": escrow_id, "invoice_id": esc.release_invoice_id, "entry_type": "escrow_released", "amount_vnd": esc.amount_vnd})
            self._emit("escrow.released", now, esc.tenant_id, trace_id, {"escrow_id": escrow_id, "release_invoice_id": esc.release_invoice_id, "source_invoice_id": esc.source_invoice_id})
            return updated

    def prepare_escrow_refund(self, *, escrow_id: str, reason: str, now: datetime) -> EscrowActionPrepareOutcome:
        with self._lock:
            esc = self.escrows.get(escrow_id)
            if esc is None:
                raise ResourceNotFoundError(f"Escrow '{escrow_id}' not found.")
            if esc.status == EscrowStatus.held and esc.pending_action == "refund":
                return EscrowActionPrepareOutcome(escrow=esc, should_call_rail=False)
            if esc.status != EscrowStatus.held or esc.pending_action is not None:
                raise InvalidStateTransitionError(f"Cannot refund escrow in status '{esc.status.value}'.", current_status=esc.status.value)
            updated = replace(esc, pending_action="refund", pending_refund_reason=reason, action_started_at=now)
            self.escrows[escrow_id] = updated
            ref_key = f"ref_{escrow_id}"
            self.rail_txs[ref_key] = RailTransactionRecord(
                rail_tx_pk=new_id("rtx"), tenant_id=esc.tenant_id, payment_intent_id=None, escrow_id=escrow_id,
                channel="escrow", operation="escrow_refund", idempotency_key=ref_key, rail_ref_id=esc.rail_escrow_id,
                status="pending", failure_code=None, request_payload={"idempotency_key": ref_key, "reason": reason},
            )
            return EscrowActionPrepareOutcome(escrow=updated, should_call_rail=True)

    def finalize_escrow_refunded(self, *, escrow_id: str, response_payload: dict[str, Any] | None, now: datetime, trace_id: str | None) -> EscrowRecord:
        with self._lock:
            esc = self.escrows[escrow_id]
            if esc.status != EscrowStatus.held:
                return esc
            require_escrow_transition(esc.status, EscrowStatus.refunded)
            reason = esc.pending_refund_reason or "OWNER_CANCELLED"
            updated = replace(esc, status=EscrowStatus.refunded, pending_action=None, pending_refund_reason=None, refunded_at=now)
            self.escrows[escrow_id] = updated
            self.ledger_entries.append({"entry_id": new_id("led"), "tenant_id": esc.tenant_id, "escrow_id": escrow_id, "invoice_id": esc.source_invoice_id, "entry_type": "escrow_refunded", "amount_vnd": esc.amount_vnd})
            self._emit("escrow.refunded", now, esc.tenant_id, trace_id, {"escrow_id": escrow_id, "source_invoice_id": esc.source_invoice_id, "reason": reason})
            return updated

    def list_pending_escrows(self) -> list[tuple[EscrowRecord, RailTransactionRecord | None]]:
        with self._lock:
            return [(e, self.rail_txs.get(e.escrow_id)) for e in self.escrows.values() if e.status == EscrowStatus.pending]

    def list_escrows_with_pending_action(self) -> list[tuple[EscrowRecord, RailTransactionRecord | None]]:
        with self._lock:
            out = []
            for e in self.escrows.values():
                if e.status == EscrowStatus.held and e.pending_action in ("release", "refund"):
                    key = f"rel_{e.escrow_id}" if e.pending_action == "release" else f"ref_{e.escrow_id}"
                    out.append((e, self.rail_txs.get(key)))
            return out

    def mark_escrow_stuck_notified(self, *, escrow_id: str, now: datetime) -> bool:
        with self._lock:
            esc = self.escrows.get(escrow_id)
            if esc is None or esc.stuck_notified_at is not None:
                return False
            self.escrows[escrow_id] = replace(esc, stuck_notified_at=now)
            return True

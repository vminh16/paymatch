"""Payment Gate application use cases (orchestrating domain rules + ports)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from paymatch_contracts.gate import (
    Channel,
    EscrowStatus,
    GateDecision,
)

from gate.domain.channel import resolve_payee_account, select_channel
from gate.domain.hashing import extract_indicators, format_transfer_memo
from gate.domain.models import (
    DailyBudgetSnapshot,
    EscrowRecord,
    EvaluationResult,
    GateDeniedError,
    InvalidStateTransitionError,
    InvoiceSnapshot,
    PaymentIntentRecord,
    PolicyUnavailableError,
    ResourceNotFoundError,
    TenantMismatchError,
    VendorAccountSnapshot,
    VendorSnapshot,
)
from gate.domain.rules import (
    compute_effective_auto_pay_limits,
    evaluate_escrow_hold,
    evaluate_invoice,
    validate_escrow_create,
    validate_escrow_release,
    validate_intent_authorization,
)
from gate.ports.clock import Clock
from gate.ports.ledger_store import CreateIntentOutcome, LedgerStore
from gate.ports.rail import PaymentRail, RailConflictError, RailTimeoutError
from gate.ports.read_store import CoreReadStore


class UpstreamTimeoutError(Exception):
    """Raised when a synchronous rail action (release/refund) times out."""


class PaymentGateService:
    """Application facade for all Payment Gate endpoints."""

    def __init__(
        self,
        *,
        read_store: CoreReadStore,
        ledger_store: LedgerStore,
        rail: PaymentRail,
        clock: Clock,
        authorization_ttl_seconds: int = 15 * 60,
    ) -> None:
        self._read = read_store
        self._ledger = ledger_store
        self._rail = rail
        self._clock = clock
        self._auth_ttl = timedelta(seconds=authorization_ttl_seconds)

    def is_ready(self) -> bool:
        if not (self._read.ping() and self._ledger.ping()):
            return False
        policy = self._read.load_policy_state()
        return policy.available

    def _resolve_vendor_and_accounts(
        self, invoice: InvoiceSnapshot
    ) -> tuple[VendorSnapshot | None, tuple[VendorAccountSnapshot, ...]]:
        vendor: VendorSnapshot | None = None
        if invoice.vendor_id:
            vendor = self._read.get_vendor(invoice.tenant_id, invoice.vendor_id)
        if vendor is None and invoice.seller_tax_id:
            vendor = self._read.get_vendor_by_tax_id(invoice.tenant_id, invoice.seller_tax_id)
        accounts = (
            self._read.list_vendor_accounts(invoice.tenant_id, vendor.vendor_id)
            if vendor is not None
            else ()
        )
        return vendor, accounts

    def _check_tenant_match(self, expected_tenant_id: str, provided_tenant_id: str | None) -> None:
        if provided_tenant_id is not None and provided_tenant_id != expected_tenant_id:
            raise TenantMismatchError(
                f"tenant_id '{provided_tenant_id}' does not match resource tenant '{expected_tenant_id}'."
            )

    def _require_policy(self):
        policy = self._read.load_policy_state()
        if not policy.available or policy.platform_limits is None:
            raise PolicyUnavailableError(
                "Không đọc được cấu hình policy/kill switch; Payment Gate từ chối theo nguyên tắc fail-closed."
            )
        return policy

    # --- Evaluate (zero side effects) ---

    def evaluate_invoice_policy(
        self,
        *,
        invoice_id: str,
        tenant_id: str | None = None,
    ) -> EvaluationResult:
        invoice = self._read.get_invoice(invoice_id)
        if invoice is None:
            raise ResourceNotFoundError(f"Invoice '{invoice_id}' not found.")
        self._check_tenant_match(invoice.tenant_id, tenant_id)

        policy = self._require_policy()
        vendor, accounts = self._resolve_vendor_and_accounts(invoice)
        mandate = self._read.get_latest_mandate(invoice.tenant_id)
        held_escrow = (
            self._ledger.get_open_escrow_for_po(invoice.purchase_order_id)
            if invoice.purchase_order_id
            else None
        )
        if held_escrow is not None and held_escrow.status != EscrowStatus.held:
            held_escrow = None

        channel = select_channel(invoice=invoice, mandate=mandate, held_po_escrow=held_escrow)
        payee = resolve_payee_account(
            vendor=vendor,
            seller_tax_id=invoice.seller_tax_id,
            accounts=accounts,
            channel=channel,
            held_po_escrow=held_escrow,
        )
        indicators = extract_indicators(
            seller_tax_id=invoice.seller_tax_id, vendor=vendor, payee_account=payee
        )
        risk_signals = self._read.check_risk_signals(indicators)
        vendor_suspended = (
            self._read.is_vendor_suspended(invoice.tenant_id, vendor.vendor_id)
            if vendor is not None
            else False
        )
        has_settled = self._ledger.has_settled_ledger_for_invoice(invoice.invoice_id)
        now = self._clock.now()
        daily_budget = self._ledger.get_daily_budget(invoice.tenant_id, self._clock.today_vn())

        return evaluate_invoice(
            invoice=invoice,
            vendor=vendor,
            vendor_accounts=accounts,
            mandate=mandate,
            policy=policy,
            risk_signals=risk_signals,
            indicators=indicators,
            daily_budget=daily_budget,
            vendor_suspended=vendor_suspended,
            has_settled_ledger=has_settled,
            held_po_escrow=held_escrow,
            now=now,
        )

    def evaluate_escrow_policy(
        self,
        *,
        purchase_order_id: str,
        vendor_account_id: str,
        amount_vnd: int,
        tenant_id: str | None = None,
    ) -> EvaluationResult:
        po = self._read.get_purchase_order(purchase_order_id)
        if po is None:
            raise ResourceNotFoundError(f"PurchaseOrder '{purchase_order_id}' not found.")
        self._check_tenant_match(po.tenant_id, tenant_id)

        policy = self._require_policy()
        vendor = self._read.get_vendor(po.tenant_id, po.vendor_id)
        vendor_account = self._read.get_vendor_account(po.tenant_id, vendor_account_id)
        mandate = self._read.get_latest_mandate(po.tenant_id)
        has_open_escrow = self._ledger.get_open_escrow_for_po(po.purchase_order_id) is not None
        indicators = extract_indicators(
            seller_tax_id=vendor.tax_id if vendor else None,
            vendor=vendor,
            payee_account=vendor_account,
        )
        risk_signals = self._read.check_risk_signals(indicators)

        return evaluate_escrow_hold(
            po=po,
            vendor=vendor,
            vendor_account=vendor_account,
            amount_vnd=amount_vnd,
            has_open_escrow=has_open_escrow,
            mandate=mandate,
            policy=policy,
            risk_signals=risk_signals,
            indicators=indicators,
            now=self._clock.now(),
        )

    # --- Budgets ---

    def get_daily_budget_summary(
        self, *, tenant_id: str, budget_date: date
    ) -> dict[str, Any]:
        policy = self._require_policy()
        mandate = self._read.get_latest_mandate(tenant_id)
        _, effective_daily_limit = compute_effective_auto_pay_limits(
            policy=policy, mandate=mandate
        )
        snap = self._ledger.get_daily_budget(tenant_id, budget_date)
        return {
            "date": budget_date,
            "auto_pay_used_vnd": snap.auto_pay_used_vnd,
            "auto_pay_reserved_vnd": snap.auto_pay_reserved_vnd,
            "auto_pay_limit_vnd": effective_daily_limit,
            "total_paid_vnd": snap.total_paid_vnd,
        }

    # --- Payment Intents (Two-Phase) ---

    def _evaluate_intent_with_budget(
        self,
        *,
        invoice: InvoiceSnapshot,
        approval_id: str,
        locked_budget: DailyBudgetSnapshot,
        already_reserved: bool,
    ) -> tuple[EvaluationResult, VendorAccountSnapshot | None]:
        policy = self._require_policy()
        approval = self._read.get_approval(approval_id)
        vendor, accounts = self._resolve_vendor_and_accounts(invoice)
        mandate = self._read.get_latest_mandate(invoice.tenant_id)
        held_escrow = (
            self._ledger.get_open_escrow_for_po(invoice.purchase_order_id)
            if invoice.purchase_order_id
            else None
        )
        if held_escrow is not None and held_escrow.status != EscrowStatus.held:
            held_escrow = None

        channel = select_channel(invoice=invoice, mandate=mandate, held_po_escrow=held_escrow)
        preferred = approval.payee_account_id if approval is not None else None
        payee = resolve_payee_account(
            vendor=vendor,
            seller_tax_id=invoice.seller_tax_id,
            accounts=accounts,
            channel=channel,
            held_po_escrow=held_escrow,
            preferred_account_id=preferred,
        )
        # Also include the approval's account in indicator extraction (in case it was flagged!)
        acc_for_indicators = payee
        if acc_for_indicators is None and approval is not None:
            acc_for_indicators = self._read.get_vendor_account(
                invoice.tenant_id, approval.payee_account_id
            )
        indicators = extract_indicators(
            seller_tax_id=invoice.seller_tax_id,
            vendor=vendor,
            payee_account=acc_for_indicators,
        )
        risk_signals = self._read.check_risk_signals(indicators)
        vendor_suspended = (
            self._read.is_vendor_suspended(invoice.tenant_id, vendor.vendor_id)
            if vendor is not None
            else False
        )
        has_settled = self._ledger.has_settled_ledger_for_invoice(invoice.invoice_id)
        latest_job_id = self._read.get_latest_completed_job_id(
            invoice.tenant_id, invoice.invoice_id
        )
        now = self._clock.now()
        res = validate_intent_authorization(
            invoice=invoice,
            approval=approval,
            latest_completed_job_id=latest_job_id,
            vendor=vendor,
            vendor_accounts=accounts,
            mandate=mandate,
            policy=policy,
            risk_signals=risk_signals,
            indicators=indicators,
            daily_budget=locked_budget,
            vendor_suspended=vendor_suspended,
            has_settled_ledger=has_settled,
            held_po_escrow=held_escrow,
            now=now,
            already_reserved_for_intent=already_reserved,
        )
        return res, payee

    def create_intent(
        self,
        *,
        invoice_id: str,
        approval_id: str,
        tenant_id: str | None = None,
        trace_id: str | None = None,
    ) -> CreateIntentOutcome:
        invoice = self._read.get_invoice(invoice_id)
        if invoice is None:
            raise ResourceNotFoundError(f"Invoice '{invoice_id}' not found.")
        self._check_tenant_match(invoice.tenant_id, tenant_id)

        # Fail closed immediately if policy store is unreadable.
        self._require_policy()

        approval = self._read.get_approval(approval_id)
        if approval is None:
            raise ResourceNotFoundError(f"Approval '{approval_id}' not found.")
        self._check_tenant_match(invoice.tenant_id, approval.tenant_id)

        now = self._clock.now()
        budget_date = self._clock.today_vn()
        expires_at = now + self._auth_ttl
        memo = format_transfer_memo(invoice)

        # Resolve initial payee/channel for intent persistence; actual validation happens under DB lock!
        vendor, accounts = self._resolve_vendor_and_accounts(invoice)
        mandate = self._read.get_latest_mandate(invoice.tenant_id)
        held_escrow = (
            self._ledger.get_open_escrow_for_po(invoice.purchase_order_id)
            if invoice.purchase_order_id
            else None
        )
        if held_escrow is not None and held_escrow.status != EscrowStatus.held:
            held_escrow = None
        channel = select_channel(invoice=invoice, mandate=mandate, held_po_escrow=held_escrow)
        payee = resolve_payee_account(
            vendor=vendor,
            seller_tax_id=invoice.seller_tax_id,
            accounts=accounts,
            channel=channel,
            held_po_escrow=held_escrow,
            preferred_account_id=approval.payee_account_id,
        )
        recorded_payee_id = (
            payee.vendor_account_id if payee is not None else approval.payee_account_id
        )
        amount_vnd = invoice.total_vnd if (invoice.total_vnd is not None and invoice.total_vnd >= 0) else 0

        def _validate_under_lock(locked_budget: DailyBudgetSnapshot) -> EvaluationResult:
            eval_res, _ = self._evaluate_intent_with_budget(
                invoice=invoice,
                approval_id=approval_id,
                locked_budget=locked_budget,
                already_reserved=False,
            )
            return eval_res

        return self._ledger.create_authorized_intent(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.invoice_id,
            purchase_order_id=invoice.purchase_order_id,
            approval_id=approval_id,
            approval_method=approval.method,
            budget_date=budget_date,
            payee_account_id=recorded_payee_id,
            channel=channel.value,
            amount_vnd=amount_vnd,
            intent_hash=approval.intent_hash,
            transfer_memo=memo,
            now=now,
            expires_at=expires_at,
            trace_id=trace_id,
            validate_with_locked_budget=_validate_under_lock,
        )

    def execute_intent(
        self,
        *,
        payment_intent_id: str,
        tenant_id: str | None = None,
        trace_id: str | None = None,
    ) -> PaymentIntentRecord:
        existing = self._ledger.get_intent(payment_intent_id)
        if existing is None:
            raise ResourceNotFoundError(f"PaymentIntent '{payment_intent_id}' not found.")
        self._check_tenant_match(existing.tenant_id, tenant_id)

        # Fail closed before locking/executing if policy unreadable.
        self._require_policy()

        now = self._clock.now()
        resolved_payee_holder: list[VendorAccountSnapshot] = []
        wallet_id_holder: list[str] = []

        def _reevaluate(
            intent: PaymentIntentRecord, locked_budget: DailyBudgetSnapshot
        ) -> EvaluationResult:
            if intent.invoice_id is None:
                raise InvalidStateTransitionError(
                    "PaymentIntent has no invoice_id.", current_status=intent.status.value
                )
            invoice = self._read.get_invoice(intent.invoice_id)
            if invoice is None:
                raise ResourceNotFoundError(f"Invoice '{intent.invoice_id}' not found.")
            eval_res, payee = self._evaluate_intent_with_budget(
                invoice=invoice,
                approval_id=intent.approval_id,
                locked_budget=locked_budget,
                already_reserved=(intent.approval_method == "mandate"),
            )
            if eval_res.decision == GateDecision.ALLOW:
                assert payee is not None
                resolved_payee_holder.clear()
                resolved_payee_holder.append(payee)
                wallet_id = self._read.get_tenant_wallet_id(intent.tenant_id)
                if not wallet_id:
                    raise ResourceNotFoundError(
                        f"Tenant wallet not found for tenant '{intent.tenant_id}'."
                    )
                wallet_id_holder.clear()
                wallet_id_holder.append(wallet_id)
            return eval_res

        def _build_rail_request(intent: PaymentIntentRecord) -> tuple[str, dict[str, Any]]:
            payee = resolved_payee_holder[0]
            wallet_id = wallet_id_holder[0]
            if intent.channel == Channel.bank_transfer:
                assert payee.bank_code and payee.account_number
                return (
                    "transfer",
                    {
                        "idempotency_key": intent.payment_intent_id,
                        "from_wallet_id": wallet_id,
                        "to": {
                            "bank_code": payee.bank_code,
                            "account_number": payee.account_number,
                            "account_name": payee.account_name,
                        },
                        "amount_vnd": intent.amount_vnd,
                        "memo": intent.transfer_memo,
                    },
                )
            if intent.channel == Channel.virtual_card:
                assert payee.merchant_id
                return (
                    "card",
                    {
                        "idempotency_key": intent.payment_intent_id,
                        "from_wallet_id": wallet_id,
                        "merchant_id": payee.merchant_id,
                        "amount_vnd": intent.amount_vnd,
                        "single_use": True,
                    },
                )
            raise InvalidStateTransitionError(
                f"Channel '{intent.channel.value}' cannot be executed via /intents:execute."
            )

        prep = self._ledger.prepare_execute_intent(
            payment_intent_id=payment_intent_id,
            now=now,
            trace_id=trace_id,
            reevaluate=_reevaluate,
            build_rail_request=_build_rail_request,
        )

        if prep.denied_result is not None:
            raise GateDeniedError(
                prep.denied_result.reasons,
                kill_switch_blocked=prep.denied_result.kill_switch_blocked,
                policy_unavailable=prep.denied_result.policy_unavailable,
                payment_intent=prep.intent,
            )

        if not prep.should_call_rail:
            return prep.intent

        assert prep.request_payload is not None
        payload = prep.request_payload
        intent = prep.intent

        try:
            if intent.channel == Channel.bank_transfer:
                to = payload["to"]
                res = self._rail.create_transfer(
                    idempotency_key=payload["idempotency_key"],
                    from_wallet_id=payload["from_wallet_id"],
                    bank_code=to["bank_code"],
                    account_number=to["account_number"],
                    account_name=to["account_name"],
                    amount_vnd=payload["amount_vnd"],
                    memo=payload["memo"],
                )
                done_now = self._clock.now()
                if res.status == "settled":
                    return self._ledger.finalize_intent_settled(
                        payment_intent_id=intent.payment_intent_id,
                        rail_txn_id=res.rail_txn_id or intent.payment_intent_id,
                        settled_at=res.settled_at or done_now,
                        response_payload=res.raw_response,
                        now=done_now,
                        trace_id=trace_id,
                    )
                return self._ledger.finalize_intent_failed(
                    payment_intent_id=intent.payment_intent_id,
                    rail_txn_id=res.rail_txn_id,
                    failure_code=res.failure_code or "RAIL_FAILED",
                    response_payload=res.raw_response,
                    now=done_now,
                    trace_id=trace_id,
                )

            if intent.channel == Channel.virtual_card:
                card_res = self._rail.create_card(
                    idempotency_key=payload["idempotency_key"],
                    from_wallet_id=payload["from_wallet_id"],
                    merchant_id=payload["merchant_id"],
                    amount_vnd=payload["amount_vnd"],
                    single_use=bool(payload.get("single_use", True)),
                )
                done_now = self._clock.now()
                if card_res.status == "captured":
                    return self._ledger.finalize_intent_settled(
                        payment_intent_id=intent.payment_intent_id,
                        rail_txn_id=card_res.card_id or intent.payment_intent_id,
                        settled_at=done_now,
                        response_payload=card_res.raw_response,
                        now=done_now,
                        trace_id=trace_id,
                    )
                if card_res.status == "failed":
                    return self._ledger.finalize_intent_failed(
                        payment_intent_id=intent.payment_intent_id,
                        rail_txn_id=card_res.card_id,
                        failure_code=card_res.failure_code or "CARD_FAILED",
                        response_payload=card_res.raw_response,
                        now=done_now,
                        trace_id=trace_id,
                    )
                # Issued but not yet captured -> keep executing for poller
                return intent

        except RailTimeoutError:
            # NEVER mark failed when outcome is unknown; money may have moved!
            return intent
        except RailConflictError:
            return self._ledger.finalize_intent_failed(
                payment_intent_id=intent.payment_intent_id,
                rail_txn_id=None,
                failure_code="IDEMPOTENCY_CONFLICT",
                response_payload=None,
                now=self._clock.now(),
                trace_id=trace_id,
            )

        return intent

    def cancel_intent(
        self,
        *,
        payment_intent_id: str,
        reason: str,
        tenant_id: str | None = None,
        trace_id: str | None = None,
    ) -> PaymentIntentRecord:
        existing = self._ledger.get_intent(payment_intent_id)
        if existing is None:
            raise ResourceNotFoundError(f"PaymentIntent '{payment_intent_id}' not found.")
        self._check_tenant_match(existing.tenant_id, tenant_id)
        return self._ledger.cancel_authorized_intent(
            payment_intent_id=payment_intent_id,
            reason=reason,
            now=self._clock.now(),
            trace_id=trace_id,
        )

    def get_intent(self, payment_intent_id: str) -> PaymentIntentRecord:
        intent = self._ledger.get_intent(payment_intent_id)
        if intent is None:
            raise ResourceNotFoundError(f"PaymentIntent '{payment_intent_id}' not found.")
        return intent

    def list_intents(
        self,
        *,
        tenant_id: str,
        invoice_id: str | None = None,
        statuses: tuple[str, ...] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[PaymentIntentRecord], str | None]:
        return self._ledger.list_intents(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            statuses=statuses,
            limit=limit,
            cursor=cursor,
        )

    # --- Escrows (F7) ---

    def create_escrow(
        self,
        *,
        approval_id: str,
        expires_on: date,
        tenant_id: str | None = None,
        trace_id: str | None = None,
    ) -> EscrowRecord:
        policy = self._require_policy()
        approval = self._read.get_approval(approval_id)
        if approval is None:
            raise ResourceNotFoundError(f"Approval '{approval_id}' not found.")
        self._check_tenant_match(approval.tenant_id, tenant_id)

        po = (
            self._read.get_purchase_order(approval.purchase_order_id)
            if approval.purchase_order_id
            else None
        )
        if po is not None:
            self._check_tenant_match(po.tenant_id, tenant_id)
        vendor = self._read.get_vendor(po.tenant_id, po.vendor_id) if po is not None else None
        vendor_account = self._read.get_vendor_account(
            approval.tenant_id, approval.payee_account_id
        )
        has_open_escrow = (
            self._ledger.get_open_escrow_for_po(po.purchase_order_id) is not None
            if po is not None
            else False
        )
        mandate = self._read.get_latest_mandate(approval.tenant_id)
        indicators = extract_indicators(
            seller_tax_id=vendor.tax_id if vendor else None,
            vendor=vendor,
            payee_account=vendor_account,
        )
        risk_signals = self._read.check_risk_signals(indicators)
        now = self._clock.now()

        eval_res = validate_escrow_create(
            approval=approval,
            po=po,
            vendor=vendor,
            vendor_account=vendor_account,
            has_open_escrow=has_open_escrow,
            mandate=mandate,
            policy=policy,
            risk_signals=risk_signals,
            indicators=indicators,
            now=now,
        )
        if eval_res.decision != GateDecision.ALLOW:
            raise GateDeniedError(
                eval_res.reasons,
                kill_switch_blocked=eval_res.kill_switch_blocked,
                policy_unavailable=eval_res.policy_unavailable,
            )

        assert po is not None and vendor_account is not None
        assert vendor_account.bank_code and vendor_account.account_number
        wallet_id = self._read.get_tenant_wallet_id(po.tenant_id)
        if not wallet_id:
            raise ResourceNotFoundError(f"Tenant wallet not found for tenant '{po.tenant_id}'.")

        req_payload = {
            "from_wallet_id": wallet_id,
            "to": {
                "bank_code": vendor_account.bank_code,
                "account_number": vendor_account.account_number,
                "account_name": vendor_account.account_name,
            },
            "amount_vnd": approval.amount_vnd,
            "expires_on": expires_on.isoformat(),
        }
        escrow = self._ledger.create_pending_escrow(
            tenant_id=po.tenant_id,
            purchase_order_id=po.purchase_order_id,
            vendor_account_id=vendor_account.vendor_account_id,
            approval_id=approval.approval_id,
            amount_vnd=approval.amount_vnd,
            source_invoice_id=approval.source_invoice_id,
            expires_on=expires_on,
            now=now,
            request_payload=req_payload,
        )

        try:
            hold_res = self._rail.create_escrow(
                idempotency_key=escrow.escrow_id,
                from_wallet_id=wallet_id,
                bank_code=vendor_account.bank_code,
                account_number=vendor_account.account_number,
                account_name=vendor_account.account_name,
                amount_vnd=approval.amount_vnd,
                expires_on=expires_on.isoformat(),
            )
            done_now = self._clock.now()
            if hold_res.status == "held" and hold_res.rail_escrow_id:
                return self._ledger.finalize_escrow_held(
                    escrow_id=escrow.escrow_id,
                    rail_escrow_id=hold_res.rail_escrow_id,
                    response_payload=hold_res.raw_response,
                    now=done_now,
                    trace_id=trace_id,
                )
            return self._ledger.finalize_escrow_failed(
                escrow_id=escrow.escrow_id,
                failure_code=hold_res.failure_code or "ESCROW_HOLD_FAILED",
                response_payload=hold_res.raw_response,
                now=done_now,
                trace_id=trace_id,
            )
        except RailTimeoutError:
            # Stay pending; background poller re-POSTs idempotently.
            return escrow
        except RailConflictError:
            return self._ledger.finalize_escrow_failed(
                escrow_id=escrow.escrow_id,
                failure_code="IDEMPOTENCY_CONFLICT",
                response_payload=None,
                now=self._clock.now(),
                trace_id=trace_id,
            )

    def release_escrow(
        self,
        *,
        escrow_id: str,
        approval_id: str,
        goods_receipt_id: str,
        tenant_id: str | None = None,
        trace_id: str | None = None,
    ) -> EscrowRecord:
        escrow = self._ledger.get_escrow(escrow_id)
        if escrow is None:
            raise ResourceNotFoundError(f"Escrow '{escrow_id}' not found.")
        self._check_tenant_match(escrow.tenant_id, tenant_id)
        if escrow.status != EscrowStatus.held:
            raise InvalidStateTransitionError(
                f"Cannot release escrow in status '{escrow.status.value}'.",
                current_status=escrow.status.value,
            )

        policy = self._require_policy()
        release_approval = self._read.get_approval(approval_id)
        release_invoice = (
            self._read.get_invoice(release_approval.invoice_id)
            if release_approval is not None and release_approval.invoice_id
            else None
        )
        goods_receipt = self._read.get_goods_receipt(goods_receipt_id)
        po = self._read.get_purchase_order(escrow.purchase_order_id)
        vendor = self._read.get_vendor(po.tenant_id, po.vendor_id) if po is not None else None
        vendor_account = self._read.get_vendor_account(escrow.tenant_id, escrow.vendor_account_id)
        latest_job_id = (
            self._read.get_latest_completed_job_id(escrow.tenant_id, release_invoice.invoice_id)
            if release_invoice is not None
            else None
        )
        has_settled = (
            self._ledger.has_settled_ledger_for_invoice(release_invoice.invoice_id)
            if release_invoice is not None
            else False
        )
        indicators = extract_indicators(
            seller_tax_id=release_invoice.seller_tax_id if release_invoice else (vendor.tax_id if vendor else None),
            vendor=vendor,
            payee_account=vendor_account,
        )
        risk_signals = self._read.check_risk_signals(indicators)
        now = self._clock.now()

        eval_res = validate_escrow_release(
            escrow=escrow,
            release_approval=release_approval,
            release_invoice=release_invoice,
            goods_receipt=goods_receipt,
            po=po,
            vendor=vendor,
            vendor_account=vendor_account,
            latest_completed_job_id=latest_job_id,
            has_settled_ledger=has_settled,
            policy=policy,
            risk_signals=risk_signals,
            indicators=indicators,
            now=now,
        )
        if eval_res.decision != GateDecision.ALLOW:
            raise GateDeniedError(
                eval_res.reasons,
                kill_switch_blocked=eval_res.kill_switch_blocked,
                policy_unavailable=eval_res.policy_unavailable,
            )

        assert release_approval is not None and release_invoice is not None
        assert escrow.rail_escrow_id is not None
        try:
            action_res = self._rail.release_escrow(
                rail_escrow_id=escrow.rail_escrow_id,
                idempotency_key=f"rel_{escrow.escrow_id}",
            )
        except RailTimeoutError as exc:
            raise UpstreamTimeoutError(str(exc)) from exc

        if action_res.status != "released":
            raise InvalidStateTransitionError(
                f"Rail rejected escrow release: {action_res.failure_code}",
                current_status=escrow.status.value,
            )

        return self._ledger.finalize_escrow_released(
            escrow_id=escrow.escrow_id,
            release_invoice_id=release_invoice.invoice_id,
            release_approval_id=release_approval.approval_id,
            goods_receipt_id=goods_receipt_id,
            budget_date=self._clock.today_vn(),
            response_payload=action_res.raw_response,
            now=self._clock.now(),
            trace_id=trace_id,
        )

    def refund_escrow(
        self,
        *,
        escrow_id: str,
        reason: str,
        tenant_id: str | None = None,
        trace_id: str | None = None,
    ) -> EscrowRecord:
        escrow = self._ledger.get_escrow(escrow_id)
        if escrow is None:
            raise ResourceNotFoundError(f"Escrow '{escrow_id}' not found.")
        self._check_tenant_match(escrow.tenant_id, tenant_id)
        if escrow.status != EscrowStatus.held:
            raise InvalidStateTransitionError(
                f"Cannot refund escrow in status '{escrow.status.value}'.",
                current_status=escrow.status.value,
            )

        assert escrow.rail_escrow_id is not None
        try:
            action_res = self._rail.refund_escrow(
                rail_escrow_id=escrow.rail_escrow_id,
                idempotency_key=f"ref_{escrow.escrow_id}",
            )
        except RailTimeoutError as exc:
            raise UpstreamTimeoutError(str(exc)) from exc

        if action_res.status != "refunded":
            raise InvalidStateTransitionError(
                f"Rail rejected escrow refund: {action_res.failure_code}",
                current_status=escrow.status.value,
            )

        return self._ledger.finalize_escrow_refunded(
            escrow_id=escrow.escrow_id,
            reason=reason,
            response_payload=action_res.raw_response,
            now=self._clock.now(),
            trace_id=trace_id,
        )

    def get_escrow(self, escrow_id: str) -> EscrowRecord:
        escrow = self._ledger.get_escrow(escrow_id)
        if escrow is None:
            raise ResourceNotFoundError(f"Escrow '{escrow_id}' not found.")
        return escrow

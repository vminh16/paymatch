"""Background reconciliation loop for Payment Gate (docs/05-api/gate-api.md §5).

Safety rules (B1, B2, B3, N1, N2):
  1. Expire `authorized` intents past 15-minute TTL -> `expired` (reason=AUTHORIZATION_TIMEOUT).
  2. Poll `executing` intents:
     - `bank_transfer`: status-only GET /sim/rails/transfers/{payment_intent_id}.
     - `virtual_card`: if `card_id` recorded -> status-only GET /sim/rails/cards/{card_id}.
       Otherwise (re-POST can create the first rail tx!) -> MUST re-run full evaluation
       (policy, kill switch, approval active, hard block, cross alert) BEFORE re-POSTing!
       If evaluation fails -> NEVER replay and NEVER mark denied/failed (the original
       timed-out POST may already have captured funds); keep `executing` with its invoice
       claim and daily budget reservation intact, and emit `payment.stuck` after 24h!
     - NEVER mark `failed` on RailAmbiguousError (403/409/5xx/timeout/bad schema) or 404!
       Keep claim & budget reservation; emit `payment.stuck` once after 24h.
  3. Poll `pending` escrows (re-POST can create first hold!):
     - MUST re-run full escrow creation evaluation BEFORE re-POSTing!
       If evaluation fails -> NEVER replay and NEVER mark `failed` (the original timed-out
       POST may already have held funds at the rail); keep `pending` (preserving open-PO
       uniqueness and approval binding) and alert once after 24h!
     - On RailAmbiguousError -> keep `pending`, alert after 24h.
  4. Poll `held` escrows with `pending_action` ('release' or 'refund'):
     - For 'release': re-run full release evaluation BEFORE re-POSTing `:release`;
       if evaluation fails -> skip replay, keep `pending_action='release'` & invoice claim,
       and alert after 24h!
     - On RailAmbiguousError -> keep claim & pending_action, alert after 24h.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from paymatch_contracts.gate import Channel, GateDecision

from gate.application.service import resolve_vendor_and_accounts
from gate.domain.channel import resolve_payee_account, select_channel
from gate.domain.hashing import extract_indicators
from gate.domain.models import (
    EscrowRecord,
    PaymentIntentRecord,
    PolicyUnavailableError,
)
from gate.domain.rules import (
    validate_escrow_create,
    validate_escrow_release,
    validate_intent_authorization,
)
from gate.ports.clock import Clock
from gate.ports.ledger_store import LedgerStore
from gate.ports.rail import PaymentRail, RailAmbiguousError, RailNotFoundError
from gate.ports.read_store import CoreReadStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PollTickSummary:
    expired_intents: int = 0
    settled_intents: int = 0
    failed_intents: int = 0
    stuck_notified: int = 0
    held_escrows: int = 0
    failed_escrows: int = 0
    released_escrows: int = 0
    refunded_escrows: int = 0


class GateBackgroundPoller:
    def __init__(
        self,
        *,
        read_store: CoreReadStore,
        ledger_store: LedgerStore,
        rail: PaymentRail,
        clock: Clock,
        stuck_threshold_seconds: int = 24 * 60 * 60,
    ) -> None:
        self._read = read_store
        self._ledger = ledger_store
        self._rail = rail
        self._clock = clock
        self._stuck_threshold = timedelta(seconds=stuck_threshold_seconds)

    def _reevaluate_card_before_replay(self, intent: PaymentIntentRecord, now) -> bool:
        """B2 + N10: Re-evaluate full policy/approval/risk before re-POSTing POST /sim/rails/cards."""
        policy = self._read.load_policy_state()
        if not policy.available or policy.platform_limits is None:
            return False
        if intent.invoice_id is None:
            return False
        invoice = self._read.get_invoice(intent.invoice_id)
        approval = self._read.get_approval(intent.approval_id)
        if invoice is None:
            return False
        vendor, accounts = resolve_vendor_and_accounts(self._read, invoice)
        mandate = self._read.get_latest_mandate(invoice.tenant_id)
        channel = select_channel(invoice=invoice, mandate=mandate, held_po_escrow=None)
        payee = resolve_payee_account(
            vendor=vendor,
            seller_tax_id=invoice.seller_tax_id,
            accounts=accounts,
            channel=channel,
            preferred_account_id=approval.payee_account_id if approval else None,
        )
        indicators = extract_indicators(
            seller_tax_id=invoice.seller_tax_id, vendor=vendor, payee_account=payee
        )
        try:
            risk_signals = self._read.check_risk_signals(indicators)
        except PolicyUnavailableError:
            return False
        vendor_suspended = (
            self._read.is_vendor_suspended(invoice.tenant_id, vendor.vendor_id)
            if vendor is not None
            else False
        )
        latest_job_id = self._read.get_latest_completed_job_id(
            invoice.tenant_id, invoice.invoice_id
        )
        budget = self._ledger.get_daily_budget(
            invoice.tenant_id, intent.budget_date or self._clock.today_vn()
        )
        approver_is_owner = True
        if approval is not None and approval.method in ("single", "bulk"):
            approver_is_owner = bool(
                approval.approver_user_id
                and self._read.is_tenant_owner(invoice.tenant_id, approval.approver_user_id)
            )
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
            daily_budget=budget,
            vendor_suspended=vendor_suspended,
            has_settled_ledger=self._ledger.has_settled_ledger_for_invoice(invoice.invoice_id),
            held_po_escrow=None,
            now=now,
            already_reserved_for_intent=(intent.approval_method == "mandate"),
            approver_is_owner=approver_is_owner,
        )
        return res.decision == GateDecision.ALLOW and res.intent_hash == intent.intent_hash

    def _reevaluate_pending_escrow_before_replay(self, escrow: EscrowRecord, now) -> bool:
        """B2: Re-evaluate full policy/approval/risk before re-POSTing POST /sim/rails/escrows."""
        policy = self._read.load_policy_state()
        if not policy.available or policy.platform_limits is None:
            return False
        approval = self._read.get_approval(escrow.approval_id)
        po = self._read.get_purchase_order(escrow.purchase_order_id)
        vendor = self._read.get_vendor(escrow.tenant_id, po.vendor_id) if po is not None else None
        vendor_account = self._read.get_vendor_account(escrow.tenant_id, escrow.vendor_account_id)
        mandate = self._read.get_latest_mandate(escrow.tenant_id)
        indicators = extract_indicators(
            seller_tax_id=vendor.tax_id if vendor else None,
            vendor=vendor,
            payee_account=vendor_account,
        )
        try:
            risk_signals = self._read.check_risk_signals(indicators)
        except PolicyUnavailableError:
            return False
        approver_is_owner = bool(
            approval is not None
            and approval.approver_user_id
            and self._read.is_tenant_owner(escrow.tenant_id, approval.approver_user_id)
        )
        res = validate_escrow_create(
            approval=approval,
            po=po,
            vendor=vendor,
            vendor_account=vendor_account,
            has_open_escrow=False,  # This escrow itself is the open pending escrow
            mandate=mandate,
            policy=policy,
            risk_signals=risk_signals,
            indicators=indicators,
            now=now,
            approver_is_owner=approver_is_owner,
        )
        return res.decision == GateDecision.ALLOW

    def _reevaluate_pending_release_before_replay(self, escrow: EscrowRecord, now) -> bool:
        """B2: Re-evaluate full escrow release rules before re-POSTing :release."""
        if not escrow.release_approval_id or not escrow.goods_receipt_id or not escrow.release_invoice_id:
            return False
        policy = self._read.load_policy_state()
        if not policy.available or policy.platform_limits is None:
            return False
        release_approval = self._read.get_approval(escrow.release_approval_id)
        release_invoice = self._read.get_invoice(escrow.release_invoice_id)
        goods_receipt = self._read.get_goods_receipt(escrow.goods_receipt_id)
        po = self._read.get_purchase_order(escrow.purchase_order_id)
        vendor = self._read.get_vendor(po.tenant_id, po.vendor_id) if po is not None else None
        vendor_account = self._read.get_vendor_account(escrow.tenant_id, escrow.vendor_account_id)
        mandate = self._read.get_latest_mandate(escrow.tenant_id)
        latest_job_id = (
            self._read.get_latest_completed_job_id(escrow.tenant_id, release_invoice.invoice_id)
            if release_invoice is not None
            else None
        )
        indicators = extract_indicators(
            seller_tax_id=(
                release_invoice.seller_tax_id
                if release_invoice
                else (vendor.tax_id if vendor else None)
            ),
            vendor=vendor,
            payee_account=vendor_account,
        )
        try:
            risk_signals = self._read.check_risk_signals(indicators)
        except PolicyUnavailableError:
            return False
        approver_is_owner = bool(
            release_approval is not None
            and release_approval.approver_user_id
            and self._read.is_tenant_owner(escrow.tenant_id, release_approval.approver_user_id)
        )
        res = validate_escrow_release(
            escrow=escrow,
            release_approval=release_approval,
            release_invoice=release_invoice,
            goods_receipt=goods_receipt,
            po=po,
            vendor=vendor,
            vendor_account=vendor_account,
            latest_completed_job_id=latest_job_id,
            has_settled_ledger=self._ledger.has_settled_ledger_for_invoice(escrow.release_invoice_id),
            mandate=mandate,
            policy=policy,
            risk_signals=risk_signals,
            indicators=indicators,
            now=now,
            approver_is_owner=approver_is_owner,
        )
        return res.decision == GateDecision.ALLOW

    def run_once(self) -> PollTickSummary:
        now = self._clock.now()
        expired_count = len(self._ledger.expire_stale_authorized_intents(now=now))
        settled_count = 0
        failed_count = 0
        stuck_count = 0
        held_escrows = 0
        failed_escrows = 0
        released_escrows = 0
        refunded_escrows = 0

        # 2. Reconcile executing intents
        for intent, rail_tx in self._ledger.list_executing_intents():
            try:
                if intent.channel == Channel.bank_transfer:
                    # Status-only GET (cannot create a new transfer).
                    res = self._rail.get_transfer(intent.payment_intent_id)
                    if res.status == "settled":
                        self._ledger.finalize_intent_settled(
                            payment_intent_id=intent.payment_intent_id,
                            rail_txn_id=res.rail_txn_id or intent.payment_intent_id,
                            settled_at=res.settled_at or now,
                            response_payload=res.raw_response,
                            now=now,
                            trace_id=None,
                        )
                        settled_count += 1
                    else:
                        self._ledger.finalize_intent_failed(
                            payment_intent_id=intent.payment_intent_id,
                            rail_txn_id=res.rail_txn_id,
                            failure_code=res.failure_code or "RAIL_FAILED",
                            response_payload=res.raw_response,
                            now=now,
                            trace_id=None,
                        )
                        failed_count += 1
                    continue

                if intent.channel == Channel.virtual_card:
                    card_res = None
                    if rail_tx is not None and rail_tx.rail_ref_id:
                        # Status-only GET when card_id is already known!
                        card_res = self._rail.get_card(rail_tx.rail_ref_id)
                    elif rail_tx is not None and rail_tx.request_payload:
                        # B2 + N1: Re-POST can create the first rail tx -> MUST re-evaluate first.
                        # If re-evaluation fails, skip replay and keep `executing` (with claim &
                        # budget reservation intact) because the initial timed-out POST may already
                        # have captured funds; fall through to the stuck alert check!
                        if not self._reevaluate_card_before_replay(intent, now):
                            logger.warning(
                                "Skipping virtual_card replay for %s after policy/approval re-eval failed; keeping executing.",
                                intent.payment_intent_id,
                            )
                        else:
                            p = rail_tx.request_payload
                            card_res = self._rail.create_card(
                                idempotency_key=p["idempotency_key"],
                                from_wallet_id=p["from_wallet_id"],
                                merchant_id=p["merchant_id"],
                                amount_vnd=int(p["amount_vnd"]),
                                single_use=bool(p.get("single_use", True)),
                            )

                    if card_res is not None:
                        if card_res.status == "captured":
                            self._ledger.finalize_intent_settled(
                                payment_intent_id=intent.payment_intent_id,
                                rail_txn_id=card_res.card_id or intent.payment_intent_id,
                                settled_at=now,
                                response_payload=card_res.raw_response,
                                now=now,
                                trace_id=None,
                            )
                            settled_count += 1
                            continue
                        if card_res.status == "failed":
                            self._ledger.finalize_intent_failed(
                                payment_intent_id=intent.payment_intent_id,
                                rail_txn_id=card_res.card_id,
                                failure_code=card_res.failure_code or "CARD_FAILED",
                                response_payload=card_res.raw_response,
                                now=now,
                                trace_id=None,
                            )
                            failed_count += 1
                            continue
                        if card_res.card_id:
                            self._ledger.record_intent_rail_ref(
                                payment_intent_id=intent.payment_intent_id,
                                rail_ref_id=card_res.card_id,
                                now=now,
                            )

            except (RailAmbiguousError, RailNotFoundError) as exc:
                # B3: NEVER finalize as failed on ambiguous/403/409/5xx/timeout/404!
                logger.warning(
                    "Ambiguous rail status polling intent %s (%s); keeping executing.",
                    intent.payment_intent_id,
                    exc,
                )

            executing_since = intent.executed_at or intent.created_at
            if now - executing_since >= self._stuck_threshold:
                if self._ledger.mark_intent_stuck_notified(
                    payment_intent_id=intent.payment_intent_id, now=now
                ):
                    stuck_count += 1

        # 3. Reconcile pending escrows (B2 + N2: re-evaluate before re-POSTing hold; never fail without rail outcome!)
        for escrow, rail_tx in self._ledger.list_pending_escrows():
            if rail_tx is None or not rail_tx.request_payload:
                continue
            if not self._reevaluate_pending_escrow_before_replay(escrow, now):
                # N2: The first timed-out POST may already have held funds at the rail.
                # Skip replay, keep `pending` (preserving open-PO uniqueness & approval binding),
                # and alert ops once stuck threshold passes.
                logger.warning(
                    "Skipping pending escrow replay for %s after policy/approval re-eval failed; keeping pending.",
                    escrow.escrow_id,
                )
                if now - escrow.created_at >= self._stuck_threshold:
                    if self._ledger.mark_escrow_stuck_notified(escrow_id=escrow.escrow_id, now=now):
                        stuck_count += 1
                continue

            p = rail_tx.request_payload
            to = p.get("to") or {}
            try:
                hold_res = self._rail.create_escrow(
                    idempotency_key=p["idempotency_key"],
                    from_wallet_id=p["from_wallet_id"],
                    bank_code=to["bank_code"],
                    account_number=to["account_number"],
                    account_name=to["account_name"],
                    amount_vnd=int(p["amount_vnd"]),
                    expires_on=str(p["expires_on"]),
                )
                if hold_res.status == "held" and hold_res.rail_escrow_id:
                    self._ledger.finalize_escrow_held(
                        escrow_id=escrow.escrow_id,
                        rail_escrow_id=hold_res.rail_escrow_id,
                        response_payload=hold_res.raw_response,
                        now=now,
                        trace_id=None,
                    )
                    held_escrows += 1
                elif hold_res.status == "failed":
                    self._ledger.finalize_escrow_failed(
                        escrow_id=escrow.escrow_id,
                        failure_code=hold_res.failure_code or "ESCROW_HOLD_FAILED",
                        response_payload=hold_res.raw_response,
                        now=now,
                        trace_id=None,
                    )
                    failed_escrows += 1
            except RailAmbiguousError as exc:
                # B3: Keep pending on ambiguous reply; alert after stuck threshold.
                logger.warning(
                    "Ambiguous rail reply polling pending escrow %s (%s); keeping pending.",
                    escrow.escrow_id,
                    exc,
                )
                if now - escrow.created_at >= self._stuck_threshold:
                    if self._ledger.mark_escrow_stuck_notified(escrow_id=escrow.escrow_id, now=now):
                        stuck_count += 1

        # 4. Reconcile held escrows with in-flight pending_action (B1 + B2 + B3)
        for escrow, rail_tx in self._ledger.list_escrows_with_pending_action():
            if not escrow.rail_escrow_id:
                continue
            if escrow.pending_action == "release":
                if not self._reevaluate_pending_release_before_replay(escrow, now):
                    # B2 + B1: Do NOT re-POST :release when policy/approval fails, and keep the
                    # invoice claim intact because the original timed-out :release may have
                    # already moved funds at the rail. Alert ops once stuck threshold passes.
                    started = escrow.action_started_at or escrow.created_at
                    if now - started >= self._stuck_threshold:
                        if self._ledger.mark_escrow_stuck_notified(
                            escrow_id=escrow.escrow_id, now=now
                        ):
                            stuck_count += 1
                    continue
                try:
                    rel_res = self._rail.release_escrow(
                        rail_escrow_id=escrow.rail_escrow_id,
                        idempotency_key=f"rel_{escrow.escrow_id}",
                    )
                    if rel_res.status == "released":
                        self._ledger.finalize_escrow_released(
                            escrow_id=escrow.escrow_id,
                            budget_date=self._clock.today_vn(),
                            response_payload=rel_res.raw_response,
                            now=now,
                            trace_id=None,
                        )
                        released_escrows += 1
                except RailAmbiguousError as exc:
                    logger.warning(
                        "Ambiguous rail reply polling release for escrow %s (%s); keeping claim.",
                        escrow.escrow_id,
                        exc,
                    )
                    started = escrow.action_started_at or escrow.created_at
                    if now - started >= self._stuck_threshold:
                        if self._ledger.mark_escrow_stuck_notified(
                            escrow_id=escrow.escrow_id, now=now
                        ):
                            stuck_count += 1
            elif escrow.pending_action == "refund":
                try:
                    ref_res = self._rail.refund_escrow(
                        rail_escrow_id=escrow.rail_escrow_id,
                        idempotency_key=f"ref_{escrow.escrow_id}",
                    )
                    if ref_res.status == "refunded":
                        self._ledger.finalize_escrow_refunded(
                            escrow_id=escrow.escrow_id,
                            response_payload=ref_res.raw_response,
                            now=now,
                            trace_id=None,
                        )
                        refunded_escrows += 1
                except RailAmbiguousError as exc:
                    logger.warning(
                        "Ambiguous rail reply polling refund for escrow %s (%s).",
                        escrow.escrow_id,
                        exc,
                    )

        return PollTickSummary(
            expired_intents=expired_count,
            settled_intents=settled_count,
            failed_intents=failed_count,
            stuck_notified=stuck_count,
            held_escrows=held_escrows,
            failed_escrows=failed_escrows,
            released_escrows=released_escrows,
            refunded_escrows=refunded_escrows,
        )

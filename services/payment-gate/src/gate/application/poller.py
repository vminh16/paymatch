"""Background reconciliation loop for Payment Gate (docs/05-api/gate-api.md §5).

Every 10s:
  1. Expire `authorized` intents past 15-minute TTL -> `expired` (reason=AUTHORIZATION_TIMEOUT).
  2. Poll `executing` intents against rail:
     - transfers: GET /sim/rails/transfers/{idempotency_key}
     - cards: GET /sim/rails/cards/{card_id} if known, else idempotent re-POST /sim/rails/cards
     - NEVER mark `failed` on unknown/timeout! After 24h stuck, emit `payment.stuck` once and keep `executing`.
  3. Poll `pending` escrows via idempotent re-POST /sim/rails/escrows with exact saved body.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from paymatch_contracts.gate import Channel

from gate.ports.clock import Clock
from gate.ports.ledger_store import LedgerStore
from gate.ports.rail import PaymentRail, RailConflictError, RailNotFoundError, RailTimeoutError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PollTickSummary:
    expired_intents: int = 0
    settled_intents: int = 0
    failed_intents: int = 0
    stuck_notified: int = 0
    held_escrows: int = 0
    failed_escrows: int = 0


class GateBackgroundPoller:
    def __init__(
        self,
        *,
        ledger_store: LedgerStore,
        rail: PaymentRail,
        clock: Clock,
        stuck_threshold_seconds: int = 24 * 60 * 60,
    ) -> None:
        self._ledger = ledger_store
        self._rail = rail
        self._clock = clock
        self._stuck_threshold = timedelta(seconds=stuck_threshold_seconds)

    def run_once(self) -> PollTickSummary:
        now = self._clock.now()
        expired_count = len(self._ledger.expire_stale_authorized_intents(now=now))
        settled_count = 0
        failed_count = 0
        stuck_count = 0
        held_escrows = 0
        failed_escrows = 0

        # 2. Reconcile executing intents
        for intent, rail_tx in self._ledger.list_executing_intents():
            try:
                if intent.channel == Channel.bank_transfer:
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
                    if rail_tx is not None and rail_tx.rail_ref_id:
                        card_res = self._rail.get_card(rail_tx.rail_ref_id)
                    elif rail_tx is not None and rail_tx.request_payload:
                        p = rail_tx.request_payload
                        card_res = self._rail.create_card(
                            idempotency_key=p["idempotency_key"],
                            from_wallet_id=p["from_wallet_id"],
                            merchant_id=p["merchant_id"],
                            amount_vnd=int(p["amount_vnd"]),
                            single_use=bool(p.get("single_use", True)),
                        )
                    else:
                        continue

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
                    elif card_res.status == "failed":
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

            except RailConflictError:
                logger.error(
                    "Idempotency payload conflict polling intent %s; marking failed.",
                    intent.payment_intent_id,
                )
                self._ledger.finalize_intent_failed(
                    payment_intent_id=intent.payment_intent_id,
                    rail_txn_id=None,
                    failure_code="IDEMPOTENCY_CONFLICT",
                    response_payload=None,
                    now=now,
                    trace_id=None,
                )
                failed_count += 1
                continue
            except (RailTimeoutError, RailNotFoundError):
                # Outcome unknown — NEVER mark failed! Emit payment.stuck after 24h.
                pass

            executing_since = intent.executed_at or intent.created_at
            if now - executing_since >= self._stuck_threshold:
                if self._ledger.mark_intent_stuck_notified(
                    payment_intent_id=intent.payment_intent_id, now=now
                ):
                    stuck_count += 1

        # 3. Reconcile pending escrows via idempotent re-POST with exact saved payload
        for escrow, rail_tx in self._ledger.list_pending_escrows():
            if rail_tx is None or not rail_tx.request_payload:
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
            except RailConflictError:
                logger.error(
                    "Idempotency payload conflict polling escrow %s; marking failed.",
                    escrow.escrow_id,
                )
                self._ledger.finalize_escrow_failed(
                    escrow_id=escrow.escrow_id,
                    failure_code="IDEMPOTENCY_CONFLICT",
                    response_payload=None,
                    now=now,
                    trace_id=None,
                )
                failed_escrows += 1
            except RailTimeoutError:
                # Stay pending until next tick.
                pass

        return PollTickSummary(
            expired_intents=expired_count,
            settled_intents=settled_count,
            failed_intents=failed_count,
            stuck_notified=stuck_count,
            held_escrows=held_escrows,
            failed_escrows=failed_escrows,
        )

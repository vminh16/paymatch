"""Postgres implementation of LedgerStore (sole writer for schema `ledger`)."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from paymatch_contracts.gate import (
    Channel,
    Code as GateReasonCode,
    EscrowStatus,
    GateDecision,
    Layer as GateReasonLayer,
    PaymentIntentStatus,
)

from gate.domain.models import (
    DailyBudgetSnapshot,
    EscrowRecord,
    EvaluationResult,
    GateDeniedError,
    GateReasonItem,
    InvalidStateTransitionError,
    PaymentIntentRecord,
    ResourceNotFoundError,
)
from gate.domain.state_machine import require_escrow_transition, require_intent_transition
from gate.ids import new_id
from gate.ports.ledger_store import (
    CreateIntentOutcome,
    ExecutePrepareOutcome,
    RailTransactionRecord,
)


def _serialize_reasons(reasons: tuple[GateReasonItem, ...]) -> list[dict[str, str]]:
    return [
        {"code": r.code.value, "layer": r.layer.value, "detail": r.detail}
        for r in reasons
    ]


def _parse_reasons(raw: Any) -> tuple[GateReasonItem, ...]:
    if not raw:
        return ()
    return tuple(
        GateReasonItem(
            code=GateReasonCode(item["code"]),
            layer=GateReasonLayer(item["layer"]),
            detail=str(item["detail"]),
        )
        for item in raw
    )


def _row_to_intent(row: dict[str, Any]) -> PaymentIntentRecord:
    return PaymentIntentRecord(
        payment_intent_id=row["payment_intent_id"],
        tenant_id=row["tenant_id"],
        invoice_id=row["invoice_id"],
        purchase_order_id=row["purchase_order_id"],
        intent_hash=row["intent_hash"],
        approval_id=row["approval_id"],
        approval_method=row["approval_method"],
        budget_date=row["budget_date"],
        payee_account_id=row["payee_account_id"],
        channel=Channel(row["channel"]),
        amount_vnd=int(row["amount_vnd"]),
        status=PaymentIntentStatus(row["status"]),
        gate_reasons=_parse_reasons(row["gate_reasons"]),
        rail_txn_id=row["rail_txn_id"],
        failure_code=row["failure_code"],
        transfer_memo=row["transfer_memo"],
        authorized_at=row["authorized_at"],
        executed_at=row["executed_at"],
        settled_at=row["settled_at"],
        expires_at=row["expires_at"],
        created_at=row["created_at"],
        stuck_notified_at=row["stuck_notified_at"],
    )


def _row_to_escrow(row: dict[str, Any]) -> EscrowRecord:
    return EscrowRecord(
        escrow_id=row["escrow_id"],
        tenant_id=row["tenant_id"],
        purchase_order_id=row["purchase_order_id"],
        vendor_account_id=row["vendor_account_id"],
        approval_id=row["approval_id"],
        amount_vnd=int(row["amount_vnd"]),
        status=EscrowStatus(row["status"]),
        source_invoice_id=row["source_invoice_id"],
        release_invoice_id=row["release_invoice_id"],
        goods_receipt_id=row["goods_receipt_id"],
        rail_escrow_id=row["rail_escrow_id"],
        failure_code=row["failure_code"],
        expires_on=row["expires_on"],
        created_at=row["created_at"],
        released_at=row["released_at"],
        refunded_at=row["refunded_at"],
    )


def _row_to_rail_tx(row: dict[str, Any]) -> RailTransactionRecord:
    return RailTransactionRecord(
        rail_tx_pk=row["rail_tx_pk"],
        tenant_id=row["tenant_id"],
        payment_intent_id=row["payment_intent_id"],
        escrow_id=row["escrow_id"],
        channel=row["channel"],
        operation=row["operation"],
        idempotency_key=row["idempotency_key"],
        rail_ref_id=row["rail_ref_id"],
        status=row["status"],
        failure_code=row["failure_code"],
        request_payload=dict(row["request_payload"] or {}),
    )


def _encode_cursor(created_at: datetime, payment_intent_id: str) -> str:
    raw = json.dumps(
        {"created_at": created_at.isoformat(), "payment_intent_id": payment_intent_id}
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    return datetime.fromisoformat(payload["created_at"]), str(payload["payment_intent_id"])


class PostgresLedgerStore:
    """Sole transactional writer for Postgres schema `ledger`."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self._conninfo, row_factory=dict_row, autocommit=False)

    def _insert_outbox(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        *,
        event_type: str,
        occurred_at: datetime,
        tenant_id: str | None,
        trace_id: str | None,
        data: dict[str, Any],
    ) -> None:
        cur.execute(
            """
            INSERT INTO ledger.outbox (
                event_id, type, schema_version, occurred_at, tenant_id, trace_id, data
            ) VALUES (%s, %s, 1, %s, %s, %s, %s);
            """,
            (new_id("evt"), event_type, occurred_at, tenant_id, trace_id, Jsonb(data)),
        )

    def _lock_daily_budget(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        *,
        tenant_id: str,
        budget_date: date,
        now: datetime,
    ) -> DailyBudgetSnapshot:
        """Ensure daily_budgets row exists and acquire row-level FOR UPDATE lock."""
        cur.execute(
            """
            INSERT INTO ledger.daily_budgets (
                tenant_id, budget_date, auto_pay_used_vnd, auto_pay_reserved_vnd, total_paid_vnd, updated_at
            ) VALUES (%s, %s, 0, 0, 0, %s)
            ON CONFLICT (tenant_id, budget_date) DO NOTHING;
            """,
            (tenant_id, budget_date, now),
        )
        cur.execute(
            """
            SELECT budget_date, auto_pay_used_vnd, auto_pay_reserved_vnd, total_paid_vnd
            FROM ledger.daily_budgets
            WHERE tenant_id = %s AND budget_date = %s
            FOR UPDATE;
            """,
            (tenant_id, budget_date),
        )
        row = cur.fetchone()
        assert row is not None
        return DailyBudgetSnapshot(
            budget_date=row["budget_date"],
            auto_pay_used_vnd=int(row["auto_pay_used_vnd"]),
            auto_pay_reserved_vnd=int(row["auto_pay_reserved_vnd"]),
            total_paid_vnd=int(row["total_paid_vnd"]),
        )

    def ping(self) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM ledger.schema_migrations LIMIT 1;")
                conn.rollback()
            return True
        except Exception:
            return False

    def has_settled_ledger_for_invoice(self, invoice_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM ledger.ledger_entries
                    WHERE invoice_id = %s
                      AND entry_type IN ('settled', 'escrow_released')
                    LIMIT 1;
                    """,
                    (invoice_id,),
                )
                return cur.fetchone() is not None

    def get_open_escrow_for_po(self, purchase_order_id: str) -> EscrowRecord | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM ledger.escrows
                    WHERE purchase_order_id = %s
                      AND status IN ('pending', 'held')
                    LIMIT 1;
                    """,
                    (purchase_order_id,),
                )
                row = cur.fetchone()
                return _row_to_escrow(row) if row else None

    def get_daily_budget(self, tenant_id: str, budget_date: date) -> DailyBudgetSnapshot:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT budget_date, auto_pay_used_vnd, auto_pay_reserved_vnd, total_paid_vnd
                    FROM ledger.daily_budgets
                    WHERE tenant_id = %s AND budget_date = %s;
                    """,
                    (tenant_id, budget_date),
                )
                row = cur.fetchone()
                if row is None:
                    return DailyBudgetSnapshot(budget_date=budget_date)
                return DailyBudgetSnapshot(
                    budget_date=row["budget_date"],
                    auto_pay_used_vnd=int(row["auto_pay_used_vnd"]),
                    auto_pay_reserved_vnd=int(row["auto_pay_reserved_vnd"]),
                    total_paid_vnd=int(row["total_paid_vnd"]),
                )

    def get_intent(self, payment_intent_id: str) -> PaymentIntentRecord | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM ledger.payment_intents WHERE payment_intent_id = %s;",
                    (payment_intent_id,),
                )
                row = cur.fetchone()
                return _row_to_intent(row) if row else None

    def list_intents(
        self,
        *,
        tenant_id: str,
        invoice_id: str | None = None,
        statuses: tuple[str, ...] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[PaymentIntentRecord], str | None]:
        clauses = ["tenant_id = %s"]
        params: list[Any] = [tenant_id]
        if invoice_id is not None:
            clauses.append("invoice_id = %s")
            params.append(invoice_id)
        if statuses:
            clauses.append("status = ANY(%s)")
            params.append(list(statuses))
        if cursor:
            c_time, c_id = _decode_cursor(cursor)
            clauses.append("(created_at, payment_intent_id) < (%s, %s)")
            params.extend([c_time, c_id])

        params.append(limit + 1)
        sql = f"""
            SELECT *
            FROM ledger.payment_intents
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC, payment_intent_id DESC
            LIMIT %s;
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = [_row_to_intent(r) for r in page_rows]
        next_cursor = (
            _encode_cursor(items[-1].created_at, items[-1].payment_intent_id)
            if has_more and items
            else None
        )
        return items, next_cursor

    def create_authorized_intent(
        self,
        *,
        tenant_id: str,
        invoice_id: str,
        purchase_order_id: str | None,
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
        validate_with_locked_budget: Callable[[DailyBudgetSnapshot], EvaluationResult],
    ) -> CreateIntentOutcome:
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 1. Idempotency check: if an active or settled intent already exists, return it (200).
                cur.execute(
                    """
                    SELECT *
                    FROM ledger.payment_intents
                    WHERE invoice_id = %s
                      AND status IN ('authorized', 'executing', 'settled')
                    LIMIT 1;
                    """,
                    (invoice_id,),
                )
                existing = cur.fetchone()
                if existing is not None:
                    conn.rollback()
                    return CreateIntentOutcome(intent=_row_to_intent(existing), created=False)

                # 2. Row-lock daily_budgets for (tenant_id, budget_date) BEFORE re-validating daily limit!
                locked_budget = self._lock_daily_budget(
                    cur, tenant_id=tenant_id, budget_date=budget_date, now=now
                )

                # Re-check active intent after lock in case another transaction just inserted.
                cur.execute(
                    """
                    SELECT *
                    FROM ledger.payment_intents
                    WHERE invoice_id = %s
                      AND status IN ('authorized', 'executing', 'settled')
                    LIMIT 1;
                    """,
                    (invoice_id,),
                )
                existing = cur.fetchone()
                if existing is not None:
                    conn.rollback()
                    return CreateIntentOutcome(intent=_row_to_intent(existing), created=False)

                # 3. Validate all rules with the locked budget snapshot.
                eval_result = validate_with_locked_budget(locked_budget)
                if eval_result.decision != GateDecision.ALLOW:
                    intent_id = new_id("pi")
                    reasons_json = _serialize_reasons(eval_result.reasons)
                    cur.execute(
                        """
                        INSERT INTO ledger.payment_intents (
                            payment_intent_id, tenant_id, invoice_id, purchase_order_id,
                            intent_hash, approval_id, approval_method, budget_date,
                            payee_account_id, channel, amount_vnd, status, gate_reasons,
                            transfer_memo, created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, 'denied', %s, %s, %s
                        )
                        RETURNING *;
                        """,
                        (
                            intent_id,
                            tenant_id,
                            invoice_id,
                            purchase_order_id,
                            eval_result.intent_hash,
                            approval_id,
                            approval_method,
                            payee_account_id,
                            channel,
                            amount_vnd,
                            Jsonb(reasons_json),
                            transfer_memo,
                            now,
                        ),
                    )
                    denied_row = cur.fetchone()
                    assert denied_row is not None
                    self._insert_outbox(
                        cur,
                        event_type="payment.denied",
                        occurred_at=now,
                        tenant_id=tenant_id,
                        trace_id=trace_id,
                        data={
                            "payment_intent_id": intent_id,
                            "invoice_id": invoice_id,
                            "gate_reasons": reasons_json,
                        },
                    )
                    conn.commit()
                    raise GateDeniedError(
                        eval_result.reasons,
                        kill_switch_blocked=eval_result.kill_switch_blocked,
                        policy_unavailable=eval_result.policy_unavailable,
                        payment_intent=_row_to_intent(denied_row),
                    )

                # 4. Insert authorized intent + single-use token + budget reservation + outbox.
                intent_id = new_id("pi")
                try:
                    cur.execute(
                        """
                        INSERT INTO ledger.payment_intents (
                            payment_intent_id, tenant_id, invoice_id, purchase_order_id,
                            intent_hash, approval_id, approval_method, budget_date,
                            payee_account_id, channel, amount_vnd, status, gate_reasons,
                            transfer_memo, authorized_at, expires_at, created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'authorized', '[]'::jsonb,
                            %s, %s, %s, %s
                        )
                        RETURNING *;
                        """,
                        (
                            intent_id,
                            tenant_id,
                            invoice_id,
                            purchase_order_id,
                            intent_hash,
                            approval_id,
                            approval_method,
                            budget_date,
                            payee_account_id,
                            channel,
                            amount_vnd,
                            transfer_memo,
                            now,
                            expires_at,
                            now,
                        ),
                    )
                except psycopg.errors.UniqueViolation:
                    conn.rollback()
                    # Another concurrent writer won the partial unique index; return that active intent (200).
                    cur.execute(
                        """
                        SELECT *
                        FROM ledger.payment_intents
                        WHERE invoice_id = %s
                          AND status IN ('authorized', 'executing', 'settled')
                        LIMIT 1;
                        """,
                        (invoice_id,),
                    )
                    winner = cur.fetchone()
                    if winner is not None:
                        return CreateIntentOutcome(intent=_row_to_intent(winner), created=False)
                    raise

                created_row = cur.fetchone()
                assert created_row is not None

                cur.execute(
                    """
                    INSERT INTO ledger.payment_tokens (
                        token_id, payment_intent_id, tenant_id, intent_hash,
                        status, issued_at, expires_at
                    ) VALUES (%s, %s, %s, %s, 'issued', %s, %s);
                    """,
                    (new_id("ptk"), intent_id, tenant_id, intent_hash, now, expires_at),
                )

                if approval_method == "mandate":
                    cur.execute(
                        """
                        UPDATE ledger.daily_budgets
                        SET auto_pay_reserved_vnd = auto_pay_reserved_vnd + %s,
                            updated_at = %s
                        WHERE tenant_id = %s AND budget_date = %s;
                        """,
                        (amount_vnd, now, tenant_id, budget_date),
                    )

                self._insert_outbox(
                    cur,
                    event_type="payment.authorized",
                    occurred_at=now,
                    tenant_id=tenant_id,
                    trace_id=trace_id,
                    data={
                        "payment_intent_id": intent_id,
                        "invoice_id": invoice_id,
                        "amount_vnd": amount_vnd,
                        "channel": channel,
                    },
                )
                conn.commit()
                return CreateIntentOutcome(intent=_row_to_intent(created_row), created=True)

    def record_denied_intent(
        self,
        *,
        tenant_id: str,
        invoice_id: str,
        purchase_order_id: str | None,
        approval_id: str,
        approval_method: str,
        payee_account_id: str,
        channel: str,
        amount_vnd: int,
        intent_hash: str,
        transfer_memo: str,
        reasons: tuple[GateReasonItem, ...],
        now: datetime,
        trace_id: str | None,
    ) -> PaymentIntentRecord:
        intent_id = new_id("pi")
        reasons_json = _serialize_reasons(reasons)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ledger.payment_intents (
                        payment_intent_id, tenant_id, invoice_id, purchase_order_id,
                        intent_hash, approval_id, approval_method, budget_date,
                        payee_account_id, channel, amount_vnd, status, gate_reasons,
                        transfer_memo, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, 'denied', %s, %s, %s
                    )
                    RETURNING *;
                    """,
                    (
                        intent_id,
                        tenant_id,
                        invoice_id,
                        purchase_order_id,
                        intent_hash,
                        approval_id,
                        approval_method,
                        payee_account_id,
                        channel,
                        amount_vnd,
                        Jsonb(reasons_json),
                        transfer_memo,
                        now,
                    ),
                )
                row = cur.fetchone()
                assert row is not None
                self._insert_outbox(
                    cur,
                    event_type="payment.denied",
                    occurred_at=now,
                    tenant_id=tenant_id,
                    trace_id=trace_id,
                    data={
                        "payment_intent_id": intent_id,
                        "invoice_id": invoice_id,
                        "gate_reasons": reasons_json,
                    },
                )
                conn.commit()
                return _row_to_intent(row)

    def prepare_execute_intent(
        self,
        *,
        payment_intent_id: str,
        now: datetime,
        trace_id: str | None,
        reevaluate: Callable[[PaymentIntentRecord, DailyBudgetSnapshot], EvaluationResult],
        build_rail_request: Callable[[PaymentIntentRecord], tuple[str, dict[str, Any]]],
    ) -> ExecutePrepareOutcome:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM ledger.payment_intents
                    WHERE payment_intent_id = %s
                    FOR UPDATE;
                    """,
                    (payment_intent_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    raise ResourceNotFoundError(f"PaymentIntent '{payment_intent_id}' not found.")

                intent = _row_to_intent(row)
                # Idempotent: already executing or settled -> return without calling rail again!
                if intent.status in (PaymentIntentStatus.executing, PaymentIntentStatus.settled):
                    conn.rollback()
                    return ExecutePrepareOutcome(intent=intent, should_call_rail=False)

                if intent.status != PaymentIntentStatus.authorized:
                    conn.rollback()
                    raise InvalidStateTransitionError(
                        f"Cannot execute PaymentIntent in status '{intent.status.value}'.",
                        current_status=intent.status.value,
                    )

                # Check authorization TTL expiration (15 min)
                if intent.expires_at is not None and now > intent.expires_at:
                    cur.execute(
                        """
                        UPDATE ledger.payment_intents
                        SET status = 'expired'
                        WHERE payment_intent_id = %s
                        RETURNING *;
                        """,
                        (payment_intent_id,),
                    )
                    expired_row = cur.fetchone()
                    cur.execute(
                        """
                        UPDATE ledger.payment_tokens
                        SET status = 'expired'
                        WHERE payment_intent_id = %s AND status = 'issued';
                        """,
                        (payment_intent_id,),
                    )
                    if intent.approval_method == "mandate" and intent.budget_date is not None:
                        self._lock_daily_budget(
                            cur, tenant_id=intent.tenant_id, budget_date=intent.budget_date, now=now
                        )
                        cur.execute(
                            """
                            UPDATE ledger.daily_budgets
                            SET auto_pay_reserved_vnd = GREATEST(0, auto_pay_reserved_vnd - %s),
                                updated_at = %s
                            WHERE tenant_id = %s AND budget_date = %s;
                            """,
                            (intent.amount_vnd, now, intent.tenant_id, intent.budget_date),
                        )
                    if intent.invoice_id is not None:
                        self._insert_outbox(
                            cur,
                            event_type="payment.expired",
                            occurred_at=now,
                            tenant_id=intent.tenant_id,
                            trace_id=trace_id,
                            data={
                                "payment_intent_id": payment_intent_id,
                                "invoice_id": intent.invoice_id,
                                "reason": "AUTHORIZATION_TIMEOUT",
                            },
                        )
                    conn.commit()
                    raise InvalidStateTransitionError(
                        "PaymentIntent authorization has expired.",
                        current_status=PaymentIntentStatus.expired.value,
                    )

                # Load daily budget for re-evaluation
                budget_date = intent.budget_date or now.date()
                locked_budget = self._lock_daily_budget(
                    cur, tenant_id=intent.tenant_id, budget_date=budget_date, now=now
                )

                # Re-evaluate ALL rules right before calling rail!
                eval_result = reevaluate(intent, locked_budget)
                if eval_result.decision != GateDecision.ALLOW:
                    require_intent_transition(intent.status, PaymentIntentStatus.denied)
                    reasons_json = _serialize_reasons(eval_result.reasons)
                    cur.execute(
                        """
                        UPDATE ledger.payment_intents
                        SET status = 'denied',
                            gate_reasons = %s
                        WHERE payment_intent_id = %s
                        RETURNING *;
                        """,
                        (Jsonb(reasons_json), payment_intent_id),
                    )
                    denied_row = cur.fetchone()
                    assert denied_row is not None
                    cur.execute(
                        """
                        UPDATE ledger.payment_tokens
                        SET status = 'revoked'
                        WHERE payment_intent_id = %s AND status = 'issued';
                        """,
                        (payment_intent_id,),
                    )
                    if intent.approval_method == "mandate" and intent.budget_date is not None:
                        cur.execute(
                            """
                            UPDATE ledger.daily_budgets
                            SET auto_pay_reserved_vnd = GREATEST(0, auto_pay_reserved_vnd - %s),
                                updated_at = %s
                            WHERE tenant_id = %s AND budget_date = %s;
                            """,
                            (intent.amount_vnd, now, intent.tenant_id, intent.budget_date),
                        )
                    if intent.invoice_id is not None:
                        self._insert_outbox(
                            cur,
                            event_type="payment.denied",
                            occurred_at=now,
                            tenant_id=intent.tenant_id,
                            trace_id=trace_id,
                            data={
                                "payment_intent_id": payment_intent_id,
                                "invoice_id": intent.invoice_id,
                                "gate_reasons": reasons_json,
                            },
                        )
                    conn.commit()
                    return ExecutePrepareOutcome(
                        intent=_row_to_intent(denied_row),
                        should_call_rail=False,
                        denied_result=eval_result,
                    )

                # Consume single-use payment_token atomically!
                cur.execute(
                    """
                    UPDATE ledger.payment_tokens
                    SET status = 'consumed', consumed_at = %s
                    WHERE payment_intent_id = %s AND status = 'issued'
                    RETURNING token_id;
                    """,
                    (now, payment_intent_id),
                )
                if cur.fetchone() is None:
                    conn.rollback()
                    raise InvalidStateTransitionError(
                        "Single-use payment token is no longer available.",
                        current_status=intent.status.value,
                    )

                # Build exact rail request payload and persist in rail_transactions BEFORE calling rail.
                operation, request_payload = build_rail_request(intent)
                require_intent_transition(intent.status, PaymentIntentStatus.executing)
                cur.execute(
                    """
                    UPDATE ledger.payment_intents
                    SET status = 'executing',
                        executed_at = %s
                    WHERE payment_intent_id = %s
                    RETURNING *;
                    """,
                    (now, payment_intent_id),
                )
                exec_row = cur.fetchone()
                assert exec_row is not None

                cur.execute(
                    """
                    INSERT INTO ledger.rail_transactions (
                        rail_tx_pk, tenant_id, payment_intent_id, channel, operation,
                        idempotency_key, status, request_payload, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s)
                    ON CONFLICT (idempotency_key) DO NOTHING;
                    """,
                    (
                        new_id("rtx"),
                        intent.tenant_id,
                        payment_intent_id,
                        intent.channel.value,
                        operation,
                        payment_intent_id,
                        Jsonb(request_payload),
                        now,
                        now,
                    ),
                )
                conn.commit()
                return ExecutePrepareOutcome(
                    intent=_row_to_intent(exec_row),
                    should_call_rail=True,
                    request_payload=request_payload,
                )

    def finalize_intent_settled(
        self,
        *,
        payment_intent_id: str,
        rail_txn_id: str,
        settled_at: datetime,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> PaymentIntentRecord:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM ledger.payment_intents WHERE payment_intent_id = %s FOR UPDATE;",
                    (payment_intent_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise ResourceNotFoundError(f"PaymentIntent '{payment_intent_id}' not found.")
                intent = _row_to_intent(row)
                if intent.status != PaymentIntentStatus.executing:
                    conn.rollback()
                    return intent

                require_intent_transition(intent.status, PaymentIntentStatus.settled)
                cur.execute(
                    """
                    UPDATE ledger.payment_intents
                    SET status = 'settled',
                        rail_txn_id = %s,
                        failure_code = NULL,
                        settled_at = %s
                    WHERE payment_intent_id = %s
                    RETURNING *;
                    """,
                    (rail_txn_id, settled_at, payment_intent_id),
                )
                updated_row = cur.fetchone()
                assert updated_row is not None

                cur.execute(
                    """
                    UPDATE ledger.rail_transactions
                    SET status = 'settled',
                        rail_ref_id = %s,
                        failure_code = NULL,
                        response_payload = %s,
                        updated_at = %s
                    WHERE idempotency_key = %s;
                    """,
                    (
                        rail_txn_id,
                        Jsonb(response_payload) if response_payload is not None else None,
                        now,
                        payment_intent_id,
                    ),
                )

                budget_date = intent.budget_date or settled_at.date()
                self._lock_daily_budget(
                    cur, tenant_id=intent.tenant_id, budget_date=budget_date, now=now
                )
                if intent.approval_method == "mandate":
                    cur.execute(
                        """
                        UPDATE ledger.daily_budgets
                        SET auto_pay_reserved_vnd = GREATEST(0, auto_pay_reserved_vnd - %s),
                            auto_pay_used_vnd = auto_pay_used_vnd + %s,
                            total_paid_vnd = total_paid_vnd + %s,
                            updated_at = %s
                        WHERE tenant_id = %s AND budget_date = %s;
                        """,
                        (
                            intent.amount_vnd,
                            intent.amount_vnd,
                            intent.amount_vnd,
                            now,
                            intent.tenant_id,
                            budget_date,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE ledger.daily_budgets
                        SET total_paid_vnd = total_paid_vnd + %s,
                            updated_at = %s
                        WHERE tenant_id = %s AND budget_date = %s;
                        """,
                        (intent.amount_vnd, now, intent.tenant_id, budget_date),
                    )

                cur.execute(
                    """
                    INSERT INTO ledger.ledger_entries (
                        entry_id, tenant_id, payment_intent_id, invoice_id, purchase_order_id,
                        payee_account_id, channel, entry_type, amount_vnd, rail_txn_id, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'settled', %s, %s, %s);
                    """,
                    (
                        new_id("led"),
                        intent.tenant_id,
                        payment_intent_id,
                        intent.invoice_id,
                        intent.purchase_order_id,
                        intent.payee_account_id,
                        intent.channel.value,
                        intent.amount_vnd,
                        rail_txn_id,
                        now,
                    ),
                )

                if intent.invoice_id is not None:
                    self._insert_outbox(
                        cur,
                        event_type="payment.executed",
                        occurred_at=now,
                        tenant_id=intent.tenant_id,
                        trace_id=trace_id,
                        data={
                            "payment_intent_id": payment_intent_id,
                            "invoice_id": intent.invoice_id,
                            "rail_txn_id": rail_txn_id,
                            "settled_at": settled_at.isoformat(),
                        },
                    )
                conn.commit()
                return _row_to_intent(updated_row)

    def finalize_intent_failed(
        self,
        *,
        payment_intent_id: str,
        rail_txn_id: str | None,
        failure_code: str,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> PaymentIntentRecord:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM ledger.payment_intents WHERE payment_intent_id = %s FOR UPDATE;",
                    (payment_intent_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise ResourceNotFoundError(f"PaymentIntent '{payment_intent_id}' not found.")
                intent = _row_to_intent(row)
                if intent.status != PaymentIntentStatus.executing:
                    conn.rollback()
                    return intent

                require_intent_transition(intent.status, PaymentIntentStatus.failed)
                cur.execute(
                    """
                    UPDATE ledger.payment_intents
                    SET status = 'failed',
                        rail_txn_id = COALESCE(%s, rail_txn_id),
                        failure_code = %s
                    WHERE payment_intent_id = %s
                    RETURNING *;
                    """,
                    (rail_txn_id, failure_code, payment_intent_id),
                )
                updated_row = cur.fetchone()
                assert updated_row is not None

                cur.execute(
                    """
                    UPDATE ledger.rail_transactions
                    SET status = 'failed',
                        rail_ref_id = COALESCE(%s, rail_ref_id),
                        failure_code = %s,
                        response_payload = %s,
                        updated_at = %s
                    WHERE idempotency_key = %s;
                    """,
                    (
                        rail_txn_id,
                        failure_code,
                        Jsonb(response_payload) if response_payload is not None else None,
                        now,
                        payment_intent_id,
                    ),
                )

                if intent.approval_method == "mandate" and intent.budget_date is not None:
                    self._lock_daily_budget(
                        cur, tenant_id=intent.tenant_id, budget_date=intent.budget_date, now=now
                    )
                    cur.execute(
                        """
                        UPDATE ledger.daily_budgets
                        SET auto_pay_reserved_vnd = GREATEST(0, auto_pay_reserved_vnd - %s),
                            updated_at = %s
                        WHERE tenant_id = %s AND budget_date = %s;
                        """,
                        (intent.amount_vnd, now, intent.tenant_id, intent.budget_date),
                    )

                cur.execute(
                    """
                    INSERT INTO ledger.ledger_entries (
                        entry_id, tenant_id, payment_intent_id, invoice_id, purchase_order_id,
                        payee_account_id, channel, entry_type, amount_vnd, rail_txn_id,
                        failure_code, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'failed', %s, %s, %s, %s);
                    """,
                    (
                        new_id("led"),
                        intent.tenant_id,
                        payment_intent_id,
                        intent.invoice_id,
                        intent.purchase_order_id,
                        intent.payee_account_id,
                        intent.channel.value,
                        intent.amount_vnd,
                        rail_txn_id,
                        failure_code,
                        now,
                    ),
                )

                if intent.invoice_id is not None:
                    self._insert_outbox(
                        cur,
                        event_type="payment.failed",
                        occurred_at=now,
                        tenant_id=intent.tenant_id,
                        trace_id=trace_id,
                        data={
                            "payment_intent_id": payment_intent_id,
                            "invoice_id": intent.invoice_id,
                            "failure_code": failure_code,
                        },
                    )
                conn.commit()
                return _row_to_intent(updated_row)

    def cancel_authorized_intent(
        self,
        *,
        payment_intent_id: str,
        reason: str,
        now: datetime,
        trace_id: str | None,
    ) -> PaymentIntentRecord:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM ledger.payment_intents WHERE payment_intent_id = %s FOR UPDATE;",
                    (payment_intent_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    raise ResourceNotFoundError(f"PaymentIntent '{payment_intent_id}' not found.")
                intent = _row_to_intent(row)
                if intent.status != PaymentIntentStatus.authorized:
                    conn.rollback()
                    raise InvalidStateTransitionError(
                        f"Cannot cancel PaymentIntent when status is '{intent.status.value}'.",
                        current_status=intent.status.value,
                    )

                require_intent_transition(intent.status, PaymentIntentStatus.expired)
                cur.execute(
                    """
                    UPDATE ledger.payment_intents
                    SET status = 'expired'
                    WHERE payment_intent_id = %s
                    RETURNING *;
                    """,
                    (payment_intent_id,),
                )
                updated_row = cur.fetchone()
                assert updated_row is not None

                cur.execute(
                    """
                    UPDATE ledger.payment_tokens
                    SET status = 'revoked'
                    WHERE payment_intent_id = %s AND status = 'issued';
                    """,
                    (payment_intent_id,),
                )

                if intent.approval_method == "mandate" and intent.budget_date is not None:
                    self._lock_daily_budget(
                        cur, tenant_id=intent.tenant_id, budget_date=intent.budget_date, now=now
                    )
                    cur.execute(
                        """
                        UPDATE ledger.daily_budgets
                        SET auto_pay_reserved_vnd = GREATEST(0, auto_pay_reserved_vnd - %s),
                            updated_at = %s
                        WHERE tenant_id = %s AND budget_date = %s;
                        """,
                        (intent.amount_vnd, now, intent.tenant_id, intent.budget_date),
                    )

                if intent.invoice_id is not None:
                    self._insert_outbox(
                        cur,
                        event_type="payment.expired",
                        occurred_at=now,
                        tenant_id=intent.tenant_id,
                        trace_id=trace_id,
                        data={
                            "payment_intent_id": payment_intent_id,
                            "invoice_id": intent.invoice_id,
                            "reason": reason,
                        },
                    )
                conn.commit()
                return _row_to_intent(updated_row)

    def expire_stale_authorized_intents(self, *, now: datetime) -> list[PaymentIntentRecord]:
        expired: list[PaymentIntentRecord] = []
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM ledger.payment_intents
                    WHERE status = 'authorized'
                      AND expires_at IS NOT NULL
                      AND expires_at <= %s
                    FOR UPDATE SKIP LOCKED;
                    """,
                    (now,),
                )
                rows = cur.fetchall()
                for row in rows:
                    intent = _row_to_intent(row)
                    cur.execute(
                        """
                        UPDATE ledger.payment_intents
                        SET status = 'expired'
                        WHERE payment_intent_id = %s
                        RETURNING *;
                        """,
                        (intent.payment_intent_id,),
                    )
                    updated_row = cur.fetchone()
                    assert updated_row is not None
                    cur.execute(
                        """
                        UPDATE ledger.payment_tokens
                        SET status = 'expired'
                        WHERE payment_intent_id = %s AND status = 'issued';
                        """,
                        (intent.payment_intent_id,),
                    )
                    if intent.approval_method == "mandate" and intent.budget_date is not None:
                        self._lock_daily_budget(
                            cur, tenant_id=intent.tenant_id, budget_date=intent.budget_date, now=now
                        )
                        cur.execute(
                            """
                            UPDATE ledger.daily_budgets
                            SET auto_pay_reserved_vnd = GREATEST(0, auto_pay_reserved_vnd - %s),
                                updated_at = %s
                            WHERE tenant_id = %s AND budget_date = %s;
                            """,
                            (intent.amount_vnd, now, intent.tenant_id, intent.budget_date),
                        )
                    if intent.invoice_id is not None:
                        self._insert_outbox(
                            cur,
                            event_type="payment.expired",
                            occurred_at=now,
                            tenant_id=intent.tenant_id,
                            trace_id=None,
                            data={
                                "payment_intent_id": intent.payment_intent_id,
                                "invoice_id": intent.invoice_id,
                                "reason": "AUTHORIZATION_TIMEOUT",
                            },
                        )
                    expired.append(_row_to_intent(updated_row))
                conn.commit()
        return expired

    def list_executing_intents(
        self,
    ) -> list[tuple[PaymentIntentRecord, RailTransactionRecord | None]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM ledger.payment_intents
                    WHERE status = 'executing'
                    ORDER BY executed_at ASC NULLS LAST;
                    """
                )
                intent_rows = cur.fetchall()
                results: list[tuple[PaymentIntentRecord, RailTransactionRecord | None]] = []
                for irow in intent_rows:
                    intent = _row_to_intent(irow)
                    cur.execute(
                        """
                        SELECT *
                        FROM ledger.rail_transactions
                        WHERE payment_intent_id = %s
                        ORDER BY created_at DESC
                        LIMIT 1;
                        """,
                        (intent.payment_intent_id,),
                    )
                    rrow = cur.fetchone()
                    results.append((intent, _row_to_rail_tx(rrow) if rrow else None))
                return results

    def mark_intent_stuck_notified(self, *, payment_intent_id: str, now: datetime) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM ledger.payment_intents
                    WHERE payment_intent_id = %s
                    FOR UPDATE;
                    """,
                    (payment_intent_id,),
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    return False
                intent = _row_to_intent(row)
                if intent.status != PaymentIntentStatus.executing or intent.stuck_notified_at is not None:
                    conn.rollback()
                    return False
                cur.execute(
                    """
                    UPDATE ledger.payment_intents
                    SET stuck_notified_at = %s
                    WHERE payment_intent_id = %s;
                    """,
                    (now, payment_intent_id),
                )
                if intent.invoice_id is not None:
                    executing_since = intent.executed_at or intent.created_at
                    self._insert_outbox(
                        cur,
                        event_type="payment.stuck",
                        occurred_at=now,
                        tenant_id=intent.tenant_id,
                        trace_id=None,
                        data={
                            "payment_intent_id": payment_intent_id,
                            "invoice_id": intent.invoice_id,
                            "executing_since": executing_since.isoformat(),
                        },
                    )
                conn.commit()
                return True

    # --- Escrows ---

    def get_escrow(self, escrow_id: str) -> EscrowRecord | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM ledger.escrows WHERE escrow_id = %s;", (escrow_id,))
                row = cur.fetchone()
                return _row_to_escrow(row) if row else None

    def create_pending_escrow(
        self,
        *,
        tenant_id: str,
        purchase_order_id: str,
        vendor_account_id: str,
        approval_id: str,
        amount_vnd: int,
        source_invoice_id: str | None,
        expires_on: date,
        now: datetime,
        request_payload: dict[str, Any],
    ) -> EscrowRecord:
        escrow_id = new_id("esc")
        full_payload = {**request_payload, "idempotency_key": escrow_id}
        with self._connect() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO ledger.escrows (
                            escrow_id, tenant_id, purchase_order_id, vendor_account_id,
                            approval_id, amount_vnd, status, source_invoice_id,
                            expires_on, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s)
                        RETURNING *;
                        """,
                        (
                            escrow_id,
                            tenant_id,
                            purchase_order_id,
                            vendor_account_id,
                            approval_id,
                            amount_vnd,
                            source_invoice_id,
                            expires_on,
                            now,
                        ),
                    )
                except psycopg.errors.UniqueViolation as exc:
                    conn.rollback()
                    raise GateDeniedError(
                        (
                            GateReasonItem(
                                code=GateReasonCode.ALREADY_PAID,
                                layer=GateReasonLayer.hard_rule,
                                detail="Mỗi đơn đặt hàng (PO) chỉ được có tối đa một escrow đang mở.",
                            ),
                        )
                    ) from exc
                row = cur.fetchone()
                assert row is not None
                cur.execute(
                    """
                    INSERT INTO ledger.rail_transactions (
                        rail_tx_pk, tenant_id, escrow_id, channel, operation,
                        idempotency_key, status, request_payload, created_at, updated_at
                    ) VALUES (%s, %s, %s, 'escrow', 'escrow_hold', %s, 'pending', %s, %s, %s);
                    """,
                    (
                        new_id("rtx"),
                        tenant_id,
                        escrow_id,
                        escrow_id,
                        Jsonb(full_payload),
                        now,
                        now,
                    ),
                )
                conn.commit()
                return _row_to_escrow(row)

    def finalize_escrow_held(
        self,
        *,
        escrow_id: str,
        rail_escrow_id: str,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> EscrowRecord:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM ledger.escrows WHERE escrow_id = %s FOR UPDATE;",
                    (escrow_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise ResourceNotFoundError(f"Escrow '{escrow_id}' not found.")
                escrow = _row_to_escrow(row)
                if escrow.status != EscrowStatus.pending:
                    conn.rollback()
                    return escrow

                require_escrow_transition(escrow.status, EscrowStatus.held)
                cur.execute(
                    """
                    UPDATE ledger.escrows
                    SET status = 'held',
                        rail_escrow_id = %s
                    WHERE escrow_id = %s
                    RETURNING *;
                    """,
                    (rail_escrow_id, escrow_id),
                )
                updated_row = cur.fetchone()
                assert updated_row is not None

                cur.execute(
                    """
                    UPDATE ledger.rail_transactions
                    SET status = 'held',
                        rail_ref_id = %s,
                        response_payload = %s,
                        updated_at = %s
                    WHERE idempotency_key = %s;
                    """,
                    (
                        rail_escrow_id,
                        Jsonb(response_payload) if response_payload is not None else None,
                        now,
                        escrow_id,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO ledger.ledger_entries (
                        entry_id, tenant_id, escrow_id, invoice_id, purchase_order_id,
                        payee_account_id, channel, entry_type, amount_vnd, rail_txn_id, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'escrow', 'escrow_held', %s, %s, %s);
                    """,
                    (
                        new_id("led"),
                        escrow.tenant_id,
                        escrow_id,
                        escrow.source_invoice_id,
                        escrow.purchase_order_id,
                        escrow.vendor_account_id,
                        escrow.amount_vnd,
                        rail_escrow_id,
                        now,
                    ),
                )
                self._insert_outbox(
                    cur,
                    event_type="escrow.held",
                    occurred_at=now,
                    tenant_id=escrow.tenant_id,
                    trace_id=trace_id,
                    data={
                        "escrow_id": escrow_id,
                        "purchase_order_id": escrow.purchase_order_id,
                        "source_invoice_id": escrow.source_invoice_id,
                    },
                )
                conn.commit()
                return _row_to_escrow(updated_row)

    def finalize_escrow_failed(
        self,
        *,
        escrow_id: str,
        failure_code: str,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> EscrowRecord:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM ledger.escrows WHERE escrow_id = %s FOR UPDATE;",
                    (escrow_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise ResourceNotFoundError(f"Escrow '{escrow_id}' not found.")
                escrow = _row_to_escrow(row)
                if escrow.status != EscrowStatus.pending:
                    conn.rollback()
                    return escrow

                require_escrow_transition(escrow.status, EscrowStatus.failed)
                cur.execute(
                    """
                    UPDATE ledger.escrows
                    SET status = 'failed',
                        failure_code = %s
                    WHERE escrow_id = %s
                    RETURNING *;
                    """,
                    (failure_code, escrow_id),
                )
                updated_row = cur.fetchone()
                assert updated_row is not None

                cur.execute(
                    """
                    UPDATE ledger.rail_transactions
                    SET status = 'failed',
                        failure_code = %s,
                        response_payload = %s,
                        updated_at = %s
                    WHERE idempotency_key = %s;
                    """,
                    (
                        failure_code,
                        Jsonb(response_payload) if response_payload is not None else None,
                        now,
                        escrow_id,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO ledger.ledger_entries (
                        entry_id, tenant_id, escrow_id, invoice_id, purchase_order_id,
                        payee_account_id, channel, entry_type, amount_vnd, failure_code, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'escrow', 'escrow_failed', %s, %s, %s);
                    """,
                    (
                        new_id("led"),
                        escrow.tenant_id,
                        escrow_id,
                        escrow.source_invoice_id,
                        escrow.purchase_order_id,
                        escrow.vendor_account_id,
                        escrow.amount_vnd,
                        failure_code,
                        now,
                    ),
                )
                self._insert_outbox(
                    cur,
                    event_type="escrow.failed",
                    occurred_at=now,
                    tenant_id=escrow.tenant_id,
                    trace_id=trace_id,
                    data={
                        "escrow_id": escrow_id,
                        "failure_code": failure_code,
                        "source_invoice_id": escrow.source_invoice_id,
                    },
                )
                conn.commit()
                return _row_to_escrow(updated_row)

    def finalize_escrow_released(
        self,
        *,
        escrow_id: str,
        release_invoice_id: str,
        release_approval_id: str,
        goods_receipt_id: str,
        budget_date: date,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> EscrowRecord:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM ledger.escrows WHERE escrow_id = %s FOR UPDATE;",
                    (escrow_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise ResourceNotFoundError(f"Escrow '{escrow_id}' not found.")
                escrow = _row_to_escrow(row)
                require_escrow_transition(escrow.status, EscrowStatus.released)

                cur.execute(
                    """
                    UPDATE ledger.escrows
                    SET status = 'released',
                        release_invoice_id = %s,
                        release_approval_id = %s,
                        goods_receipt_id = %s,
                        released_at = %s
                    WHERE escrow_id = %s
                    RETURNING *;
                    """,
                    (release_invoice_id, release_approval_id, goods_receipt_id, now, escrow_id),
                )
                updated_row = cur.fetchone()
                assert updated_row is not None

                cur.execute(
                    """
                    INSERT INTO ledger.rail_transactions (
                        rail_tx_pk, tenant_id, escrow_id, channel, operation,
                        idempotency_key, rail_ref_id, status, request_payload, response_payload,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, 'escrow', 'escrow_release', %s, %s, 'released', %s, %s, %s, %s)
                    ON CONFLICT (idempotency_key) DO UPDATE
                    SET status = 'released', response_payload = EXCLUDED.response_payload, updated_at = EXCLUDED.updated_at;
                    """,
                    (
                        new_id("rtx"),
                        escrow.tenant_id,
                        escrow_id,
                        f"rel_{escrow_id}",
                        escrow.rail_escrow_id,
                        Jsonb({"idempotency_key": f"rel_{escrow_id}"}),
                        Jsonb(response_payload) if response_payload is not None else None,
                        now,
                        now,
                    ),
                )

                self._lock_daily_budget(
                    cur, tenant_id=escrow.tenant_id, budget_date=budget_date, now=now
                )
                cur.execute(
                    """
                    UPDATE ledger.daily_budgets
                    SET total_paid_vnd = total_paid_vnd + %s,
                        updated_at = %s
                    WHERE tenant_id = %s AND budget_date = %s;
                    """,
                    (escrow.amount_vnd, now, escrow.tenant_id, budget_date),
                )

                cur.execute(
                    """
                    INSERT INTO ledger.ledger_entries (
                        entry_id, tenant_id, escrow_id, invoice_id, purchase_order_id,
                        payee_account_id, channel, entry_type, amount_vnd, rail_txn_id, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'escrow', 'escrow_released', %s, %s, %s);
                    """,
                    (
                        new_id("led"),
                        escrow.tenant_id,
                        escrow_id,
                        release_invoice_id,
                        escrow.purchase_order_id,
                        escrow.vendor_account_id,
                        escrow.amount_vnd,
                        escrow.rail_escrow_id,
                        now,
                    ),
                )

                self._insert_outbox(
                    cur,
                    event_type="escrow.released",
                    occurred_at=now,
                    tenant_id=escrow.tenant_id,
                    trace_id=trace_id,
                    data={
                        "escrow_id": escrow_id,
                        "release_invoice_id": release_invoice_id,
                        "source_invoice_id": escrow.source_invoice_id,
                    },
                )
                conn.commit()
                return _row_to_escrow(updated_row)

    def finalize_escrow_refunded(
        self,
        *,
        escrow_id: str,
        reason: str,
        response_payload: dict[str, Any] | None,
        now: datetime,
        trace_id: str | None,
    ) -> EscrowRecord:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM ledger.escrows WHERE escrow_id = %s FOR UPDATE;",
                    (escrow_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise ResourceNotFoundError(f"Escrow '{escrow_id}' not found.")
                escrow = _row_to_escrow(row)
                require_escrow_transition(escrow.status, EscrowStatus.refunded)

                cur.execute(
                    """
                    UPDATE ledger.escrows
                    SET status = 'refunded',
                        refunded_at = %s
                    WHERE escrow_id = %s
                    RETURNING *;
                    """,
                    (now, escrow_id),
                )
                updated_row = cur.fetchone()
                assert updated_row is not None

                cur.execute(
                    """
                    INSERT INTO ledger.rail_transactions (
                        rail_tx_pk, tenant_id, escrow_id, channel, operation,
                        idempotency_key, rail_ref_id, status, request_payload, response_payload,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, 'escrow', 'escrow_refund', %s, %s, 'refunded', %s, %s, %s, %s)
                    ON CONFLICT (idempotency_key) DO UPDATE
                    SET status = 'refunded', response_payload = EXCLUDED.response_payload, updated_at = EXCLUDED.updated_at;
                    """,
                    (
                        new_id("rtx"),
                        escrow.tenant_id,
                        escrow_id,
                        f"ref_{escrow_id}",
                        escrow.rail_escrow_id,
                        Jsonb({"idempotency_key": f"ref_{escrow_id}"}),
                        Jsonb(response_payload) if response_payload is not None else None,
                        now,
                        now,
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO ledger.ledger_entries (
                        entry_id, tenant_id, escrow_id, invoice_id, purchase_order_id,
                        payee_account_id, channel, entry_type, amount_vnd, rail_txn_id, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'escrow', 'escrow_refunded', %s, %s, %s);
                    """,
                    (
                        new_id("led"),
                        escrow.tenant_id,
                        escrow_id,
                        escrow.source_invoice_id,
                        escrow.purchase_order_id,
                        escrow.vendor_account_id,
                        escrow.amount_vnd,
                        escrow.rail_escrow_id,
                        now,
                    ),
                )

                self._insert_outbox(
                    cur,
                    event_type="escrow.refunded",
                    occurred_at=now,
                    tenant_id=escrow.tenant_id,
                    trace_id=trace_id,
                    data={
                        "escrow_id": escrow_id,
                        "source_invoice_id": escrow.source_invoice_id,
                        "reason": reason,
                    },
                )
                conn.commit()
                return _row_to_escrow(updated_row)

    def list_pending_escrows(self) -> list[tuple[EscrowRecord, RailTransactionRecord | None]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM ledger.escrows
                    WHERE status = 'pending'
                    ORDER BY created_at ASC;
                    """
                )
                esc_rows = cur.fetchall()
                results: list[tuple[EscrowRecord, RailTransactionRecord | None]] = []
                for erow in esc_rows:
                    escrow = _row_to_escrow(erow)
                    cur.execute(
                        """
                        SELECT *
                        FROM ledger.rail_transactions
                        WHERE escrow_id = %s AND operation = 'escrow_hold'
                        ORDER BY created_at DESC
                        LIMIT 1;
                        """,
                        (escrow.escrow_id,),
                    )
                    rrow = cur.fetchone()
                    results.append((escrow, _row_to_rail_tx(rrow) if rrow else None))
                return results

"""Background worker process (core-worker): sim-world polling, core.outbox + ledger.outbox dispatch, F1/F2/F3 handlers, and scheduled payments."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from core.ingest.adapters.sim_world_sources import SimWorldInvoiceSourceAdapter
from core.ingest.application.poller import InvoiceSourcePort, poll_sources_once
from core.persistence.db import Database
from core.persistence.outbox import fetch_unacknowledged_events, record_receipt
from core.risk.domain.aggregation import (
    FRAUD_INDICATOR_REASON_CODES,
    QT03_REASON_CODES,
    determine_post_investigation_status,
    max_severity,
    normalize_reason_codes,
)
from core.shared.clock import Clock, SimWorldClock, SystemClock
from core.shared.config import CoreSettings
from core.shared.hashing import intent_hash_invoice
from core.shared.ids import new_id
from core.tools.adapters.http_gate import HttpGateAdapter
from core.tools.application.executor import _collect_invoice_indicator_pairs
from core.tools.ports import GateClientPort, UpstreamToolError

logger = logging.getLogger("core.worker")


def _ensure_qt03_suspension(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    vendor_id: str | None,
    reason_codes: list[str],
    source_invoice_id: str,
    now: datetime,
) -> None:
    """Persist an active QT-03 auto-pay suspension for (tenant, vendor) when any QT-03 code fires (I3)."""
    qt03_hits = [c for c in reason_codes if c in QT03_REASON_CODES]
    if not qt03_hits or not vendor_id:
        return
    active_susp = conn.execute(
        """
        SELECT suspension_id FROM core.auto_pay_suspensions
        WHERE tenant_id = %s AND vendor_id = %s AND lifted_at IS NULL
        LIMIT 1
        """,
        (tenant_id, vendor_id),
    ).fetchone()
    if active_susp is None:
        conn.execute(
            """
            INSERT INTO core.auto_pay_suspensions (
                suspension_id, tenant_id, vendor_id, reason_codes, source_invoice_id, suspended_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (new_id("aps"), tenant_id, vendor_id, qt03_hits, source_invoice_id, now),
        )


def _parse_gate_ts(val: Any) -> datetime | None:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return datetime.fromisoformat(val.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _upsert_payment_intent_link(
    conn: psycopg.Connection,
    *,
    payment_intent_id: str,
    tenant_id: str,
    invoice_id: str,
    approval_id: str,
    gate_created_at: datetime | None,
    now: datetime,
) -> None:
    """Upsert Gate-authoritative payment_intent -> approval link, overriding any stale local entry (N2)."""
    conn.execute(
        """
        INSERT INTO core.payment_intent_links (
            payment_intent_id, tenant_id, invoice_id, approval_id, created_at, gate_created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (payment_intent_id) DO UPDATE
        SET approval_id = EXCLUDED.approval_id,
            gate_created_at = COALESCE(EXCLUDED.gate_created_at, core.payment_intent_links.gate_created_at)
        WHERE core.payment_intent_links.tenant_id = EXCLUDED.tenant_id
          AND core.payment_intent_links.invoice_id = EXCLUDED.invoice_id
        """,
        (payment_intent_id, tenant_id, invoice_id, approval_id, now, gate_created_at),
    )


def _resolve_intent_association(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    invoice_id: str,
    payment_intent_id: str | None,
    event_data: dict[str, Any],
    event_occurred_at: datetime | None,
    gate_client: GateClientPort | None,
    now: datetime,
) -> tuple[str | None, datetime | None]:
    """Resolve Gate-authoritative (approval_id, gate_created_at) for a payment_intent generation (B3, N2).

    Order of authoritative sources:
    1. Explicit approval_id on the ledger event payload.
    2. Gate's own ledger.payment_intents table (inside a savepoint; strictly validates tenant_id & invoice_id).
    3. Gate HTTP API GET /gate/intents/{id} (strictly validates intent_id, tenant_id, invoice_id, approval_id).
    4. Local core.payment_intent_links cache (only if Gate/ledger did not return a record).

    Whenever Gate/ledger/event provides a valid association, upserts core.payment_intent_links so Gate is
    always authoritative even when a stale local link exists. Returns (None, None) when unresolved or mismatched.
    """
    explicit_apv = event_data.get("approval_id")
    if isinstance(explicit_apv, str) and explicit_apv.strip():
        apv_id = explicit_apv.strip()
        gate_ts = _parse_gate_ts(
            event_data.get("intent_created_at") or event_data.get("created_at") or event_occurred_at
        )
        if payment_intent_id:
            _upsert_payment_intent_link(
                conn,
                payment_intent_id=payment_intent_id,
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                approval_id=apv_id,
                gate_created_at=gate_ts,
                now=now,
            )
        return apv_id, gate_ts

    if not payment_intent_id:
        return None, None

    # 2. Gate's ledger.payment_intents (isolated in a savepoint so SQL errors never abort outer tx)
    try:
        with conn.transaction():
            reg = conn.execute("SELECT to_regclass('ledger.payment_intents') AS reg").fetchone()
            if reg is not None and reg["reg"] is not None:
                row = conn.execute(
                    """
                    SELECT approval_id, invoice_id, tenant_id, created_at
                    FROM ledger.payment_intents
                    WHERE payment_intent_id = %s
                    """,
                    (payment_intent_id,),
                ).fetchone()
                if row is not None:
                    row_apv = row.get("approval_id")
                    if (
                        row.get("tenant_id") != tenant_id
                        or row.get("invoice_id") != invoice_id
                        or not isinstance(row_apv, str)
                        or not row_apv.strip()
                    ):
                        return None, None
                    gate_ts = _parse_gate_ts(row.get("created_at") or event_occurred_at)
                    _upsert_payment_intent_link(
                        conn,
                        payment_intent_id=payment_intent_id,
                        tenant_id=tenant_id,
                        invoice_id=invoice_id,
                        approval_id=row_apv.strip(),
                        gate_created_at=gate_ts,
                        now=now,
                    )
                    return row_apv.strip(), gate_ts
    except (psycopg.errors.UndefinedTable, psycopg.errors.InsufficientPrivilege):
        pass

    # 3. Gate HTTP API GET /gate/intents/{payment_intent_id} (strict validation of intent, tenant, invoice, approval)
    if gate_client is not None:
        get_intent_fn = getattr(gate_client, "get_intent", None)
        if callable(get_intent_fn):
            try:
                pi_obj = get_intent_fn(payment_intent_id=payment_intent_id)
                if pi_obj is not None:
                    if not isinstance(pi_obj, dict):
                        return None, None
                    pi_resp_id = pi_obj.get("payment_intent_id")
                    pi_resp_inv = pi_obj.get("invoice_id")
                    pi_resp_tid = pi_obj.get("tenant_id")
                    pi_resp_apv = pi_obj.get("approval_id")
                    if (
                        pi_resp_id != payment_intent_id
                        or pi_resp_inv != invoice_id
                        or (pi_resp_tid is not None and pi_resp_tid != tenant_id)
                        or not isinstance(pi_resp_apv, str)
                        or not pi_resp_apv.strip()
                    ):
                        logger.warning(
                            "Rejecting mismatched/incomplete Gate intent %s response: %s",
                            payment_intent_id,
                            pi_obj,
                        )
                        return None, None
                    gate_ts = _parse_gate_ts(pi_obj.get("created_at") or event_occurred_at)
                    _upsert_payment_intent_link(
                        conn,
                        payment_intent_id=payment_intent_id,
                        tenant_id=tenant_id,
                        invoice_id=invoice_id,
                        approval_id=pi_resp_apv.strip(),
                        gate_created_at=gate_ts,
                        now=now,
                    )
                    return pi_resp_apv.strip(), gate_ts
            except UpstreamToolError:
                logger.warning(
                    "Gate GET /intents/%s unavailable while correlating ledger event",
                    payment_intent_id,
                )

    # 4. Local link cache (only when neither ledger.payment_intents nor Gate HTTP returned a record)
    link = conn.execute(
        """
        SELECT approval_id, gate_created_at FROM core.payment_intent_links
        WHERE payment_intent_id = %s AND tenant_id = %s AND invoice_id = %s
        """,
        (payment_intent_id, tenant_id, invoice_id),
    ).fetchone()
    if link is not None:
        gate_ts = _parse_gate_ts(link.get("gate_created_at") or event_occurred_at)
        return str(link["approval_id"]), gate_ts
    return None, None


def _is_superseded_by_newer_gate_intent(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    invoice_id: str,
    approval_id: str,
    payment_intent_id: str,
    gate_created_at: datetime | None,
) -> bool:
    """Rank same-approval intents strictly by Gate created_at (never local ULID/cache order) (N2)."""
    # 1. Prefer Gate's ledger.payment_intents if readable
    try:
        with conn.transaction():
            reg = conn.execute("SELECT to_regclass('ledger.payment_intents') AS reg").fetchone()
            if reg is not None and reg["reg"] is not None:
                latest = conn.execute(
                    """
                    SELECT payment_intent_id, created_at FROM ledger.payment_intents
                    WHERE tenant_id = %s AND invoice_id = %s AND approval_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (tenant_id, invoice_id, approval_id),
                ).fetchone()
                if latest is not None and latest["payment_intent_id"] != payment_intent_id:
                    latest_ts = _parse_gate_ts(latest.get("created_at"))
                    if latest_ts is not None and (gate_created_at is None or latest_ts > gate_created_at):
                        return True
                return False
    except (psycopg.errors.UndefinedTable, psycopg.errors.InsufficientPrivilege):
        pass

    # 2. Fallback to core.payment_intent_links ranked strictly by Gate's gate_created_at
    if gate_created_at is None:
        return False
    latest_link = conn.execute(
        """
        SELECT payment_intent_id, gate_created_at FROM core.payment_intent_links
        WHERE tenant_id = %s AND invoice_id = %s AND approval_id = %s
          AND gate_created_at IS NOT NULL
        ORDER BY gate_created_at DESC
        LIMIT 1
        """,
        (tenant_id, invoice_id, approval_id),
    ).fetchone()
    if latest_link is None or latest_link["payment_intent_id"] == payment_intent_id:
        return False
    latest_ts = _parse_gate_ts(latest_link.get("gate_created_at"))
    return latest_ts is not None and latest_ts > gate_created_at


def _resolve_channel_and_payee(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    inv: dict[str, Any],
    mandate: dict[str, Any] | None,
) -> tuple[str, str | None]:
    channel = "bank_transfer"
    if mandate:
        for rule in mandate.get("channel_rules") or []:
            if rule.get("invoice_type") == inv["invoice_type"]:
                channel = rule.get("channel", "bank_transfer")
                break
    if not inv.get("vendor_id"):
        return channel, None

    if channel == "virtual_card":
        va = conn.execute(
            """
            SELECT vendor_account_id FROM core.vendor_accounts
            WHERE tenant_id = %s AND vendor_id = %s AND kind = 'card_merchant' AND status = 'verified'
            LIMIT 1
            """,
            (tenant_id, inv["vendor_id"]),
        ).fetchone()
        if va:
            return channel, va["vendor_account_id"]

    va = conn.execute(
        """
        SELECT vendor_account_id FROM core.vendor_accounts
        WHERE tenant_id = %s AND vendor_id = %s AND kind = 'bank_account' AND status = 'verified'
        LIMIT 1
        """,
        (tenant_id, inv["vendor_id"]),
    ).fetchone()
    return channel, (va["vendor_account_id"] if va else None)


def _handle_job_completed(
    conn: psycopg.Connection,
    *,
    event: dict[str, Any],
    now: datetime,
) -> None:
    data = event["data"]
    if data.get("task_type") != "investigate_invoice":
        return
    invoice_id = data.get("invoice_id")
    job_id = data.get("job_id")
    tid = event["tenant_id"]
    if not invoice_id or not tid:
        return

    inv = conn.execute(
        """
        SELECT i.*, d.sha256 AS doc_sha256
        FROM core.invoices i
        JOIN core.invoice_documents d ON d.tenant_id = i.tenant_id AND d.document_id = i.document_id
        WHERE i.tenant_id = %s AND i.invoice_id = %s
        FOR UPDATE OF i
        """,
        (tid, invoice_id),
    ).fetchone()
    if inv is None:
        return

    reason_codes = list(data.get("reason_codes") or inv.get("reason_codes") or [])

    # 1. QT-03 auto-pay suspension if any QT-03 code appeared
    _ensure_qt03_suspension(
        conn,
        tenant_id=tid,
        vendor_id=inv.get("vendor_id"),
        reason_codes=reason_codes,
        source_invoice_id=invoice_id,
        now=now,
    )

    # 2. F2 mandate auto-pay approval when invoice is auto_pay_eligible — revalidate under lock (I3, Nit 2)
    if inv["status"] == "auto_pay_eligible":
        latest_job = conn.execute(
            """
            SELECT job_id FROM core.jobs
            WHERE tenant_id = %s AND invoice_id = %s AND status = 'completed'
            ORDER BY completed_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            (tid, invoice_id),
        ).fetchone()
        job_is_current = (
            latest_job is not None and job_id is not None and latest_job["job_id"] == job_id
        )
        if not job_is_current:
            return

        mandate = conn.execute(
            "SELECT * FROM core.mandates WHERE tenant_id = %s ORDER BY version DESC LIMIT 1",
            (tid,),
        ).fetchone()
        pol = conn.execute(
            "SELECT value FROM control.policies WHERE kind = 'platform_limits' AND status = 'active' LIMIT 1"
        ).fetchone()
        # Nit 2: missing platform_limits policy -> not eligible for auto-pay (0 ceiling)
        platform_per_inv = (
            int((pol["value"] or {}).get("auto_pay_per_invoice_vnd", 0)) if pol is not None else 0
        )
        is_suspended = False
        if inv.get("vendor_id"):
            susp = conn.execute(
                """
                SELECT 1 FROM core.auto_pay_suspensions
                WHERE tenant_id = %s AND vendor_id = %s AND lifted_at IS NULL
                LIMIT 1
                """,
                (tid, inv["vendor_id"]),
            ).fetchone()
            is_suspended = susp is not None

        rechecked_status = determine_post_investigation_status(
            final_severity=inv.get("severity") or "yellow",
            vendor_id=inv.get("vendor_id"),
            total_vnd=inv.get("total_vnd"),
            mandate=mandate,
            platform_per_invoice_vnd=platform_per_inv,
            is_vendor_suspended=is_suspended,
            now_vn=now,
        )
        if inv.get("verification_required") or rechecked_status != "auto_pay_eligible":
            # Eligibility changed since investigation completed (e.g. QT-03 suspension or policy removed): demote
            conn.execute(
                """
                UPDATE core.invoices
                SET status = 'pending_approval', version = version + 1, updated_at = %s
                WHERE tenant_id = %s AND invoice_id = %s AND status = 'auto_pay_eligible'
                """,
                (now, tid, invoice_id),
            )
        elif mandate and mandate["mode"] == "auto_pay" and inv.get("total_vnd") is not None:
            channel, payee_id = _resolve_channel_and_payee(conn, tenant_id=tid, inv=inv, mandate=mandate)
            if payee_id is not None:
                ih = intent_hash_invoice(
                    invoice_id=invoice_id,
                    document_sha256=inv["doc_sha256"],
                    payee_account_id=payee_id,
                    amount_vnd=int(inv["total_vnd"]),
                    channel=channel,
                )
                approval_id = new_id("apv")
                updated = conn.execute(
                    """
                    UPDATE core.invoices
                    SET status = 'approved', version = version + 1, updated_at = %s
                    WHERE tenant_id = %s AND invoice_id = %s AND status = 'auto_pay_eligible'
                      AND version = %s
                    RETURNING status
                    """,
                    (now, tid, invoice_id, inv["version"]),
                ).fetchone()
                if updated is not None:
                    conn.execute(
                        """
                        INSERT INTO core.approvals (
                            approval_id, tenant_id, invoice_id, job_id, status,
                            amount_vnd, payee_account_id, channel, intent_hash,
                            approver_user_id, method, mandate_version, created_at
                        )
                        VALUES (%s, %s, %s, %s, 'active', %s, %s, %s, %s, NULL, 'mandate', %s, %s)
                        """,
                        (
                            approval_id,
                            tid,
                            invoice_id,
                            job_id,
                            int(inv["total_vnd"]),
                            payee_id,
                            channel,
                            ih,
                            mandate["version"],
                            now,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                        VALUES (%s, 'approval.created', 1, %s, %s, %s, %s)
                        """,
                        (
                            new_id("evt"),
                            now,
                            tid,
                            event.get("trace_id"),
                            Jsonb(
                                {
                                    "approval_id": approval_id,
                                    "invoice_id": invoice_id,
                                    "purchase_order_id": None,
                                    "method": "mandate",
                                    "reason": None,
                                }
                            ),
                        ),
                    )
                    sc_evt_id = new_id("evt")
                    sc_data = {
                        "invoice_id": invoice_id,
                        "from": "auto_pay_eligible",
                        "to": "approved",
                        "severity": inv["severity"],
                    }
                    conn.execute(
                        """
                        INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                        VALUES (%s, 'invoice.status_changed', 1, %s, %s, %s, %s)
                        """,
                        (sc_evt_id, now, tid, event.get("trace_id"), Jsonb(sc_data)),
                    )
                    conn.execute(
                        """
                        INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
                        VALUES (%s, 'tenant', %s, %s, %s, 'invoice.status_changed', %s, %s)
                        """,
                        (sc_evt_id, tid, tid, inv.get("store_id"), Jsonb(sc_data), now),
                    )

    # 3. F3: Fraud findings -> emit indicator.flagged (network-wide, opaque source_ref, NO invoice details!)
    fraud_hits = [c for c in reason_codes if c in FRAUD_INDICATOR_REASON_CODES]
    if fraud_hits:
        pairs = _collect_invoice_indicator_pairs(conn, inv)
        ind_items = [{"kind": k, "value_hash": v} for k, v in pairs]
        if ind_items:
            opaque = "srf_" + hashlib.sha256(f"{tid}:{invoice_id}".encode("utf-8")).hexdigest()[:16]
            conn.execute(
                """
                INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                VALUES (%s, 'indicator.flagged', 1, %s, NULL, %s, %s)
                """,
                (
                    new_id("evt"),
                    now,
                    event.get("trace_id"),
                    Jsonb(
                        {
                            "indicators": ind_items,
                            "reason_codes": fraud_hits,
                            "source": "finding",
                            "source_ref": opaque,
                        }
                    ),
                ),
            )


def _handle_invoice_status_changed(
    conn: psycopg.Connection,
    *,
    event: dict[str, Any],
    now: datetime,
) -> None:
    data = event["data"]
    if data.get("to") != "approved":
        return
    tid = event["tenant_id"]
    invoice_id = data["invoice_id"]
    inv = conn.execute(
        "SELECT invoice_id, store_id, status, severity, due_on, scheduled_for FROM core.invoices WHERE tenant_id = %s AND invoice_id = %s",
        (tid, invoice_id),
    ).fetchone()
    if inv is None or inv["status"] != "approved":
        return

    sched_date = inv["scheduled_for"]
    if sched_date is None:
        # I5: derive treasury proposed_pay_on ONLY from the latest completed job's final attempt
        latest_job = conn.execute(
            """
            SELECT job_id, attempt FROM core.jobs
            WHERE tenant_id = %s AND invoice_id = %s AND status = 'completed'
            ORDER BY completed_at DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            (tid, invoice_id),
        ).fetchone()
        tf = None
        if latest_job is not None:
            tf = conn.execute(
                """
                SELECT proposed_pay_on FROM core.findings
                WHERE tenant_id = %s AND invoice_id = %s
                  AND job_id = %s AND attempt = %s
                  AND bot_id = 'treasury' AND superseded = FALSE AND proposed_pay_on IS NOT NULL
                ORDER BY created_at DESC LIMIT 1
                """,
                (tid, invoice_id, latest_job["job_id"], int(latest_job["attempt"])),
            ).fetchone()
        if tf and tf["proposed_pay_on"]:
            sched_date = tf["proposed_pay_on"]
        elif inv["due_on"]:
            sched_date = inv["due_on"]
        else:
            sched_date = now.date()

    updated = conn.execute(
        """
        UPDATE core.invoices
        SET status = 'scheduled', scheduled_for = %s, version = version + 1, updated_at = %s
        WHERE tenant_id = %s AND invoice_id = %s AND status = 'approved'
        RETURNING status
        """,
        (sched_date, now, tid, invoice_id),
    ).fetchone()
    if updated is not None:
        sc_evt_id = new_id("evt")
        sc_data = {
            "invoice_id": invoice_id,
            "from": "approved",
            "to": "scheduled",
            "severity": inv["severity"],
        }
        conn.execute(
            """
            INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
            VALUES (%s, 'invoice.status_changed', 1, %s, %s, %s, %s)
            """,
            (sc_evt_id, now, tid, event.get("trace_id"), Jsonb(sc_data)),
        )
        conn.execute(
            """
            INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
            VALUES (%s, 'tenant', %s, %s, %s, 'invoice.status_changed', %s, %s)
            """,
            (sc_evt_id, tid, tid, inv.get("store_id"), Jsonb(sc_data), now),
        )


def _handle_indicator_flagged(
    conn: psycopg.Connection,
    *,
    event: dict[str, Any],
    now: datetime,
) -> None:
    data = event["data"]
    ind_ids: list[str] = []
    for ind in data.get("indicators", []):
        row = conn.execute(
            """
            INSERT INTO risk.indicators (indicator_id, kind, value_hash, first_seen_at, flags_count)
            VALUES (%s, %s, %s, %s, 1)
            ON CONFLICT (kind, value_hash) DO UPDATE SET flags_count = risk.indicators.flags_count + 1
            RETURNING indicator_id
            """,
            (new_id("ind"), ind["kind"], ind["value_hash"], now),
        ).fetchone()
        ind_ids.append(row["indicator_id"])

    if not ind_ids:
        return

    # Merge into existing open alert sharing any indicator, or create new alert
    existing = conn.execute(
        """
        SELECT alert_id, indicator_ids, reason_codes, source_refs, source_tenant_count
        FROM risk.alerts
        WHERE status = 'open' AND indicator_ids && %s::text[]
        ORDER BY created_at DESC LIMIT 1
        """,
        (ind_ids,),
    ).fetchone()
    src_ref = data.get("source_ref", "")
    rc_new = list(data.get("reason_codes", []))
    if existing:
        merged_inds = list(dict.fromkeys([*existing["indicator_ids"], *ind_ids]))
        merged_rcs = list(dict.fromkeys([*existing["reason_codes"], *rc_new]))
        refs = list(existing["source_refs"] or [])
        tenant_cnt = int(existing["source_tenant_count"])
        if src_ref and src_ref not in refs:
            refs.append(src_ref)
            tenant_cnt += 1
        conn.execute(
            """
            UPDATE risk.alerts
            SET indicator_ids = %s, reason_codes = %s, source_refs = %s, source_tenant_count = %s
            WHERE alert_id = %s
            """,
            (merged_inds, merged_rcs, refs, tenant_cnt, existing["alert_id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO risk.alerts (
                alert_id, indicator_ids, reason_codes, source, source_refs, source_tenant_count, status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, 1, 'open', %s)
            """,
            (
                new_id("alr"),
                ind_ids,
                rc_new,
                data.get("source", "finding"),
                [src_ref] if src_ref else [],
                now,
            ),
        )


def _handle_cross_alert_published(
    conn: psycopg.Connection,
    *,
    event: dict[str, Any],
    gate_client: GateClientPort,
    now: datetime,
) -> None:
    """F3/D8/B2: Re-evaluate unpaid invoices matching cross-alert indicators under invoice-first FOR UPDATE locks."""
    data = event["data"]
    cross_alert_id = data["cross_alert_id"]
    target_pairs = {(i["kind"], i["value_hash"]) for i in data.get("indicators", [])}
    if not target_pairs:
        return

    # Deterministic order (tenant_id, invoice_id) prevents lock-order inversion deadlocks
    candidate_ids = conn.execute(
        """
        SELECT tenant_id, invoice_id FROM core.invoices
        WHERE status IN ('pending_approval', 'auto_pay_eligible', 'approved', 'scheduled')
        ORDER BY tenant_id ASC, invoice_id ASC
        """
    ).fetchall()

    eligible_statuses = {"pending_approval", "auto_pay_eligible", "approved", "scheduled"}
    affected_count = 0
    for cand in candidate_ids:
        tid = cand["tenant_id"]
        invoice_id = cand["invoice_id"]

        # B2: Shared invoice-first lock order (matches merchant_api.approve_invoice)
        inv = conn.execute(
            """
            SELECT * FROM core.invoices
            WHERE tenant_id = %s AND invoice_id = %s
            FOR UPDATE
            """,
            (tid, invoice_id),
        ).fetchone()
        if inv is None or inv["status"] not in eligible_statuses:
            continue

        inv_pairs = set(_collect_invoice_indicator_pairs(conn, inv))
        if not (inv_pairs & target_pairs):
            continue

        affected_count += 1
        old_status = inv["status"]
        old_version = int(inv["version"])

        # Cancel any authorized payment intent in Gate if invoice is currently approved/scheduled (read under lock)
        if old_status in {"approved", "scheduled"}:
            try:
                intents = gate_client.list_intents(
                    tenant_id=tid, invoice_id=invoice_id, status="authorized"
                )
                for it in intents:
                    gate_client.cancel_intent(
                        payment_intent_id=it["payment_intent_id"], reason="CROSS_ALERT"
                    )
            except UpstreamToolError:
                logger.warning("Failed to cancel Gate intent for %s during cross_alert", invoice_id)

        # Add system Finding CROSS_ALERT_HIT (yellow) and record QT-03 vendor auto-pay suspension (I3)
        _ensure_qt03_suspension(
            conn,
            tenant_id=tid,
            vendor_id=inv.get("vendor_id"),
            reason_codes=["CROSS_ALERT_HIT"],
            source_invoice_id=invoice_id,
            now=now,
        )
        conn.execute(
            """
            INSERT INTO core.findings (
                finding_id, tenant_id, job_id, invoice_id, attempt, bot_id,
                bot_version, skill_version, prompt_hash, severity, severity_reported,
                reason_codes, reason, evidence, provenance, created_at
            )
            VALUES (
                %s, %s, NULL, %s, 0, 'system',
                1, 1, 'cross-alert-reval', 'yellow', 'yellow',
                ARRAY['CROSS_ALERT_HIT'], %s, '[]'::jsonb, 'trusted', %s
            )
            """,
            (
                new_id("fnd"),
                tid,
                invoice_id,
                Jsonb(
                    {
                        "text": f"Hóa đơn khớp cảnh báo chéo {cross_alert_id} trên mạng lưới MoMo; bắt buộc xác minh gọi lại.",
                        "provenance": "untrusted",
                        "source": "bot_reason",
                    }
                ),
                now,
            ),
        )

        # Supersede any active approval -> NEW_SYSTEM_FINDING (serialized under invoice FOR UPDATE lock)
        sup_rows = conn.execute(
            """
            UPDATE core.approvals
            SET status = 'superseded', superseded_at = %s, superseded_reason = 'NEW_SYSTEM_FINDING'
            WHERE tenant_id = %s AND invoice_id = %s AND status = 'active'
            RETURNING approval_id, purchase_order_id, method
            """,
            (now, tid, invoice_id),
        ).fetchall()
        for apv in sup_rows:
            conn.execute(
                """
                INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                VALUES (%s, 'approval.superseded', 1, %s, %s, %s, %s)
                """,
                (
                    new_id("evt"),
                    now,
                    tid,
                    event.get("trace_id"),
                    Jsonb(
                        {
                            "approval_id": apv["approval_id"],
                            "invoice_id": invoice_id,
                            "purchase_order_id": apv["purchase_order_id"],
                            "method": apv["method"],
                            "reason": "NEW_SYSTEM_FINDING",
                        }
                    ),
                ),
            )

        # Monotone severity & CAS -> pending_approval with verification_required=True
        new_codes = normalize_reason_codes([*(inv.get("reason_codes") or []), "CROSS_ALERT_HIT"])
        new_sev = max_severity(inv.get("severity") or "green", "yellow")
        updated = conn.execute(
            """
            UPDATE core.invoices
            SET status = 'pending_approval',
                severity = %s,
                reason_codes = %s,
                verification_required = TRUE,
                scheduled_for = NULL,
                version = version + 1,
                updated_at = %s
            WHERE tenant_id = %s AND invoice_id = %s AND status = %s AND version = %s
            RETURNING status
            """,
            (new_sev, new_codes, now, tid, invoice_id, old_status, old_version),
        ).fetchone()
        if updated is None:
            raise RuntimeError(
                f"Lost invoice CAS under FOR UPDATE lock for {invoice_id} (expected status={old_status}, version={old_version})"
            )

        if old_status != "pending_approval":
            sc_evt_id = new_id("evt")
            sc_data = {
                "invoice_id": invoice_id,
                "from": old_status,
                "to": "pending_approval",
                "severity": new_sev,
            }
            conn.execute(
                """
                INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                VALUES (%s, 'invoice.status_changed', 1, %s, %s, %s, %s)
                """,
                (sc_evt_id, now, tid, event.get("trace_id"), Jsonb(sc_data)),
            )
            conn.execute(
                """
                INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
                VALUES (%s, 'tenant', %s, %s, %s, 'invoice.status_changed', %s, %s)
                """,
                (sc_evt_id, tid, tid, inv.get("store_id"), Jsonb(sc_data), now),
            )

        # Notify owners/accountants of the affected tenant (trusted fixed template)
        users = conn.execute(
            "SELECT user_id FROM core.users WHERE tenant_id = %s AND role IN ('owner', 'accountant')",
            (tid,),
        ).fetchall()
        user_ids = [u["user_id"] for u in users]
        ntf_id = new_id("ntf")
        conn.execute(
            """
            INSERT INTO core.notifications (
                notification_id, tenant_id, user_ids, kind, invoice_ids, title, body, created_at
            )
            VALUES (%s, %s, %s, 'cross_alert_affected', %s, %s, %s, %s)
            """,
            (
                ntf_id,
                tid,
                user_ids,
                [invoice_id],
                "Cập nhật cảnh báo chéo từ mạng lưới MoMo",
                "Một chỉ báo trên hóa đơn chờ xử lý đã được đưa vào cảnh báo chéo. Yêu cầu xác minh gọi lại qua SĐT lưu sẵn trước khi duyệt.",
                now,
            ),
        )
        ntf_evt_id = new_id("evt")
        conn.execute(
            """
            INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
            VALUES (%s, 'notification.created', 1, %s, %s, %s, %s)
            """,
            (
                ntf_evt_id,
                now,
                tid,
                event.get("trace_id"),
                Jsonb({"notification_id": ntf_id, "kind": "cross_alert_affected", "user_ids": user_ids}),
            ),
        )
        conn.execute(
            """
            INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
            VALUES (%s, 'tenant', %s, %s, %s, 'notification.created', %s, %s)
            """,
            (
                ntf_evt_id,
                tid,
                tid,
                inv.get("store_id"),
                Jsonb({"notification_id": ntf_id, "kind": "cross_alert_affected"}),
                now,
            ),
        )

    conn.execute(
        "UPDATE risk.cross_alerts SET affected_invoice_count = affected_invoice_count + %s WHERE cross_alert_id = %s",
        (affected_count, cross_alert_id),
    )


def process_core_outbox_once(
    conn: psycopg.Connection,
    gate_client: GateClientPort,
    *,
    clock: Clock | None = None,
    batch_size: int = 100,
) -> int:
    """Process unacknowledged events in core.outbox using core.outbox_receipts (B2)."""
    clk = clock or SystemClock()
    now = clk.now()

    rows = fetch_unacknowledged_events(
        conn,
        source="core.outbox",
        table="core.outbox",
        batch_size=batch_size,
    )

    processed = 0
    for ev in rows:
        with conn.transaction():
            if record_receipt(conn, source="core.outbox", event_id=ev["event_id"]):
                ev_type = ev["type"]
                if ev_type == "job.completed":
                    _handle_job_completed(conn, event=ev, now=now)
                elif ev_type == "invoice.status_changed":
                    _handle_invoice_status_changed(conn, event=ev, now=now)
                elif ev_type == "indicator.flagged":
                    _handle_indicator_flagged(conn, event=ev, now=now)
                elif ev_type == "cross_alert.published":
                    _handle_cross_alert_published(conn, event=ev, gate_client=gate_client, now=now)
                processed += 1
    return processed


def _ledger_outbox_exists(conn: psycopg.Connection) -> bool:
    row = conn.execute("SELECT to_regclass('ledger.outbox') AS reg").fetchone()
    return row is not None and row["reg"] is not None


def _emit_payment_sse(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    store_id: str | None,
    invoice_id: str,
    payment_intent_id: str,
    pi_status: str,
    now: datetime,
) -> None:
    conn.execute(
        """
        INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
        VALUES (%s, 'tenant', %s, %s, %s, 'payment.updated', %s, %s)
        """,
        (
            new_id("evt"),
            tenant_id,
            tenant_id,
            store_id,
            Jsonb(
                {
                    "invoice_id": invoice_id,
                    "payment_intent_id": payment_intent_id,
                    "status": pi_status,
                }
            ),
            now,
        ),
    )


def _notify_payment_issue(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    store_id: str | None,
    invoice_id: str,
    now: datetime,
    trace_id: str | None,
) -> None:
    users = conn.execute(
        "SELECT user_id FROM core.users WHERE tenant_id = %s AND role IN ('owner', 'accountant')",
        (tenant_id,),
    ).fetchall()
    user_ids = [u["user_id"] for u in users]
    ntf_id = new_id("ntf")
    conn.execute(
        """
        INSERT INTO core.notifications (
            notification_id, tenant_id, user_ids, kind, invoice_ids, title, body, created_at
        )
        VALUES (%s, %s, %s, 'payment_failed', %s, %s, %s, %s)
        """,
        (
            ntf_id,
            tenant_id,
            user_ids,
            [invoice_id],
            "Thanh toán hóa đơn không thành công",
            "Lệnh thanh toán cho hóa đơn đã thất bại hoặc bị từ chối. Vui lòng kiểm tra và duyệt lại nếu cần.",
            now,
        ),
    )
    evt_id = new_id("evt")
    conn.execute(
        """
        INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
        VALUES (%s, 'notification.created', 1, %s, %s, %s, %s)
        """,
        (
            evt_id,
            now,
            tenant_id,
            trace_id,
            Jsonb({"notification_id": ntf_id, "kind": "payment_failed", "user_ids": user_ids}),
        ),
    )
    conn.execute(
        """
        INSERT INTO core.sse_events (event_id, stream_type, stream_key, tenant_id, store_id, event_type, data, created_at)
        VALUES (%s, 'tenant', %s, %s, %s, 'notification.created', %s, %s)
        """,
        (
            evt_id,
            tenant_id,
            tenant_id,
            store_id,
            Jsonb({"notification_id": ntf_id, "kind": "payment_failed"}),
            now,
        ),
    )


def process_ledger_outbox_once(
    conn: psycopg.Connection,
    *,
    gate_client: GateClientPort | None = None,
    clock: Clock | None = None,
    batch_size: int = 100,
) -> int:
    """Read ledger.outbox (read-only!) using core.outbox_receipts (B2, B3, B4, N1, N2, N9).

    - B4: Isolated via savepoint when ledger.outbox does not exist or is unreadable by worker.
    - N1: Processes events per payment_intent_id in seq order; deferring an earlier event defers all later
          events for that same intent (no receipt) while continuing to process other intents.
    - N9: Scans pages with after_seq so deferred events never starve healthy intents up to batch_size.
    - B3/N2: Gate is authoritative for approval linkage & intent created_at ranking.
    """
    try:
        with conn.transaction():
            if not _ledger_outbox_exists(conn):
                return 0
    except (psycopg.errors.UndefinedTable, psycopg.errors.InsufficientPrivilege) as exc:
        logger.warning("Skipping ledger.outbox (table absent or unreadable by worker): %s", exc)
        return 0

    clk = clock or SystemClock()
    now = clk.now()

    invoice_payment_events = {
        "payment.authorized",
        "payment.executed",
        "payment.failed",
        "payment.denied",
        "payment.expired",
    }

    processed = 0
    after_seq = 0
    deferred_intents: set[str] = set()
    max_pages = 20

    for _ in range(max_pages):
        if processed >= batch_size:
            break
        try:
            with conn.transaction():
                rows = fetch_unacknowledged_events(
                    conn,
                    source="ledger.outbox",
                    table="ledger.outbox",
                    batch_size=batch_size,
                    after_seq=after_seq,
                )
        except (psycopg.errors.UndefinedTable, psycopg.errors.InsufficientPrivilege) as exc:
            logger.warning("Skipping ledger.outbox (table absent or unreadable by worker): %s", exc)
            return processed

        if not rows:
            break

        for ev in rows:
            after_seq = int(ev["seq"])
            if processed >= batch_size:
                break

            ev_type = ev["type"]
            data = ev["data"] or {}
            tid = ev["tenant_id"]
            inv_id = data.get("invoice_id")
            pi_id = data.get("payment_intent_id")

            # N1: If an earlier event for this payment_intent_id was deferred in this tick,
            # defer every later event for the same intent so ordering is never violated!
            if pi_id and pi_id in deferred_intents:
                continue

            with conn.transaction():
                if tid and inv_id and ev_type in invoice_payment_events:
                    inv = conn.execute(
                        """
                        SELECT invoice_id, store_id, status, severity
                        FROM core.invoices
                        WHERE tenant_id = %s AND invoice_id = %s
                        FOR UPDATE
                        """,
                        (tid, inv_id),
                    ).fetchone()
                    if inv is not None:
                        bound_apv_id, bound_gate_ts = _resolve_intent_association(
                            conn,
                            tenant_id=tid,
                            invoice_id=inv_id,
                            payment_intent_id=pi_id,
                            event_data=data,
                            event_occurred_at=_parse_gate_ts(ev.get("occurred_at")),
                            gate_client=gate_client,
                            now=now,
                        )
                        # B3/N1: Unknown or mismatched approval linkage -> defer this intent & all later events for it
                        if bound_apv_id is None:
                            if pi_id:
                                deferred_intents.add(str(pi_id))
                            logger.warning(
                                "Deferring %s event %s for invoice %s: unresolved approval_id for payment_intent %s",
                                ev_type,
                                ev["event_id"],
                                inv_id,
                                pi_id,
                            )
                            continue

                        if not record_receipt(conn, source="ledger.outbox", event_id=ev["event_id"]):
                            continue

                        active_apv = conn.execute(
                            """
                            SELECT approval_id, job_id, purchase_order_id, method
                            FROM core.approvals
                            WHERE tenant_id = %s AND invoice_id = %s AND status = 'active'
                            LIMIT 1
                            """,
                            (tid, inv_id),
                        ).fetchone()
                        generation_matches = (
                            active_apv is not None and active_apv["approval_id"] == bound_apv_id
                        )
                        # N2: Fence older intent on the SAME approval strictly by Gate created_at
                        if generation_matches and pi_id and _is_superseded_by_newer_gate_intent(
                            conn,
                            tenant_id=tid,
                            invoice_id=inv_id,
                            approval_id=bound_apv_id,
                            payment_intent_id=str(pi_id),
                            gate_created_at=bound_gate_ts,
                        ):
                            generation_matches = False

                        if ev_type == "payment.authorized":
                            if generation_matches:
                                upd = conn.execute(
                                    """
                                    UPDATE core.invoices
                                    SET status = 'paying', version = version + 1, updated_at = %s
                                    WHERE tenant_id = %s AND invoice_id = %s AND status = 'scheduled'
                                    RETURNING status
                                    """,
                                    (now, tid, inv_id),
                                ).fetchone()
                                if upd and pi_id:
                                    _emit_payment_sse(
                                        conn,
                                        tenant_id=tid,
                                        store_id=inv["store_id"],
                                        invoice_id=inv_id,
                                        payment_intent_id=pi_id,
                                        pi_status="authorized",
                                        now=now,
                                    )

                        elif ev_type == "payment.executed":
                            if generation_matches:
                                upd = conn.execute(
                                    """
                                    UPDATE core.invoices
                                    SET status = 'paid', version = version + 1, updated_at = %s
                                    WHERE tenant_id = %s AND invoice_id = %s AND status = 'paying'
                                    RETURNING status
                                    """,
                                    (now, tid, inv_id),
                                ).fetchone()
                                if upd:
                                    conn.execute(
                                        """
                                        UPDATE core.approvals
                                        SET status = 'consumed'
                                        WHERE tenant_id = %s AND approval_id = %s AND status = 'active'
                                        """,
                                        (tid, bound_apv_id),
                                    )
                                    if pi_id:
                                        _emit_payment_sse(
                                            conn,
                                            tenant_id=tid,
                                            store_id=inv["store_id"],
                                            invoice_id=inv_id,
                                            payment_intent_id=pi_id,
                                            pi_status="settled",
                                            now=now,
                                        )

                        elif ev_type == "payment.failed":
                            if generation_matches:
                                upd1 = conn.execute(
                                    """
                                    UPDATE core.invoices
                                    SET status = 'payment_failed', version = version + 1, updated_at = %s
                                    WHERE tenant_id = %s AND invoice_id = %s AND status = 'paying'
                                    RETURNING status
                                    """,
                                    (now, tid, inv_id),
                                ).fetchone()
                                if upd1:
                                    conn.execute(
                                        """
                                        UPDATE core.invoices
                                        SET status = 'pending_approval', scheduled_for = NULL, version = version + 1, updated_at = %s
                                        WHERE tenant_id = %s AND invoice_id = %s AND status = 'payment_failed'
                                        """,
                                        (now, tid, inv_id),
                                    )
                                    sup_rows = conn.execute(
                                        """
                                        UPDATE core.approvals
                                        SET status = 'superseded', superseded_at = %s, superseded_reason = 'PAYMENT_FAILED'
                                        WHERE tenant_id = %s AND approval_id = %s AND status = 'active'
                                        RETURNING approval_id, purchase_order_id, method
                                        """,
                                        (now, tid, bound_apv_id),
                                    ).fetchall()
                                    for apv in sup_rows:
                                        conn.execute(
                                            """
                                            INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                                            VALUES (%s, 'approval.superseded', 1, %s, %s, %s, %s)
                                            """,
                                            (
                                                new_id("evt"),
                                                now,
                                                tid,
                                                ev.get("trace_id"),
                                                Jsonb(
                                                    {
                                                        "approval_id": apv["approval_id"],
                                                        "invoice_id": inv_id,
                                                        "purchase_order_id": apv["purchase_order_id"],
                                                        "method": apv["method"],
                                                        "reason": "PAYMENT_FAILED",
                                                    }
                                                ),
                                            ),
                                        )
                                    _notify_payment_issue(
                                        conn,
                                        tenant_id=tid,
                                        store_id=inv["store_id"],
                                        invoice_id=inv_id,
                                        now=now,
                                        trace_id=ev.get("trace_id"),
                                    )
                                    if pi_id:
                                        _emit_payment_sse(
                                            conn,
                                            tenant_id=tid,
                                            store_id=inv["store_id"],
                                            invoice_id=inv_id,
                                            payment_intent_id=pi_id,
                                            pi_status="failed",
                                            now=now,
                                        )

                        elif ev_type == "payment.denied":
                            if generation_matches:
                                reasons = data.get("gate_reasons") or []
                                reason_codes_gate = {
                                    (r.get("code") if isinstance(r, dict) else str(r)) for r in reasons
                                }
                                target_st = (
                                    "blocked"
                                    if (reason_codes_gate & {"BLOCKED_INVOICE", "OFFICIAL_FRAUD_LIST"})
                                    else "pending_approval"
                                )
                                upd = conn.execute(
                                    """
                                    UPDATE core.invoices
                                    SET status = %s, scheduled_for = NULL, version = version + 1, updated_at = %s
                                    WHERE tenant_id = %s AND invoice_id = %s AND status IN ('scheduled', 'paying')
                                    RETURNING status
                                    """,
                                    (target_st, now, tid, inv_id),
                                ).fetchone()
                                if upd:
                                    sup_rows = conn.execute(
                                        """
                                        UPDATE core.approvals
                                        SET status = 'superseded', superseded_at = %s, superseded_reason = 'PAYMENT_DENIED'
                                        WHERE tenant_id = %s AND approval_id = %s AND status = 'active'
                                        RETURNING approval_id, purchase_order_id, method
                                        """,
                                        (now, tid, bound_apv_id),
                                    ).fetchall()
                                    for apv in sup_rows:
                                        conn.execute(
                                            """
                                            INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
                                            VALUES (%s, 'approval.superseded', 1, %s, %s, %s, %s)
                                            """,
                                            (
                                                new_id("evt"),
                                                now,
                                                tid,
                                                ev.get("trace_id"),
                                                Jsonb(
                                                    {
                                                        "approval_id": apv["approval_id"],
                                                        "invoice_id": inv_id,
                                                        "purchase_order_id": apv["purchase_order_id"],
                                                        "method": apv["method"],
                                                        "reason": "PAYMENT_DENIED",
                                                    }
                                                ),
                                            ),
                                        )
                                    _notify_payment_issue(
                                        conn,
                                        tenant_id=tid,
                                        store_id=inv["store_id"],
                                        invoice_id=inv_id,
                                        now=now,
                                        trace_id=ev.get("trace_id"),
                                    )
                                    if pi_id:
                                        _emit_payment_sse(
                                            conn,
                                            tenant_id=tid,
                                            store_id=inv["store_id"],
                                            invoice_id=inv_id,
                                            payment_intent_id=pi_id,
                                            pi_status="denied",
                                            now=now,
                                        )

                        elif ev_type == "payment.expired":
                            apv_belongs = generation_matches
                            if not apv_belongs and active_apv is None:
                                owned = conn.execute(
                                    """
                                    SELECT 1 FROM core.approvals
                                    WHERE tenant_id = %s AND invoice_id = %s AND approval_id = %s
                                    """,
                                    (tid, inv_id, bound_apv_id),
                                ).fetchone()
                                apv_belongs = owned is not None

                            if data.get("reason") == "AUTHORIZATION_TIMEOUT" and apv_belongs:
                                latest_job = conn.execute(
                                    """
                                    SELECT job_id FROM core.jobs
                                    WHERE tenant_id = %s AND invoice_id = %s AND status = 'completed'
                                    ORDER BY completed_at DESC NULLS LAST, created_at DESC
                                    LIMIT 1
                                    """,
                                    (tid, inv_id),
                                ).fetchone()
                                apv_still_valid = (
                                    active_apv is not None
                                    and active_apv["approval_id"] == bound_apv_id
                                    and latest_job is not None
                                    and active_apv["job_id"] is not None
                                    and active_apv["job_id"] == latest_job["job_id"]
                                )
                                if apv_still_valid:
                                    conn.execute(
                                        """
                                        UPDATE core.invoices
                                        SET status = 'scheduled', version = version + 1, updated_at = %s
                                        WHERE tenant_id = %s AND invoice_id = %s AND status = 'paying'
                                        """,
                                        (now, tid, inv_id),
                                    )
                                else:
                                    upd = conn.execute(
                                        """
                                        UPDATE core.invoices
                                        SET status = 'pending_approval', scheduled_for = NULL, version = version + 1, updated_at = %s
                                        WHERE tenant_id = %s AND invoice_id = %s AND status = 'paying'
                                        RETURNING status
                                        """,
                                        (now, tid, inv_id),
                                    ).fetchone()
                                    if upd and active_apv is not None:
                                        conn.execute(
                                            """
                                            UPDATE core.approvals
                                            SET status = 'superseded', superseded_at = %s, superseded_reason = 'NEW_JOB'
                                            WHERE approval_id = %s AND status = 'active'
                                            """,
                                            (now, active_apv["approval_id"]),
                                        )
                            if pi_id and apv_belongs:
                                _emit_payment_sse(
                                    conn,
                                    tenant_id=tid,
                                    store_id=inv["store_id"],
                                    invoice_id=inv_id,
                                    payment_intent_id=pi_id,
                                    pi_status="expired",
                                    now=now,
                                )
                    else:
                        if not record_receipt(conn, source="ledger.outbox", event_id=ev["event_id"]):
                            continue
                else:
                    if not record_receipt(conn, source="ledger.outbox", event_id=ev["event_id"]):
                        continue
                processed += 1

        if len(rows) < batch_size:
            break
    return processed


def execute_scheduled_payments_once(
    conn: psycopg.Connection,
    gate_client: GateClientPort,
    *,
    clock: Clock | None = None,
) -> list[dict[str, Any]]:
    """Find due scheduled invoices with active non-escrow approval and call Gate /intents + :execute (B3, N2)."""
    clk = clock or SystemClock()
    today: date = clk.today()
    due_rows = conn.execute(
        """
        SELECT i.invoice_id, i.tenant_id, a.approval_id
        FROM core.invoices i
        JOIN core.approvals a
          ON a.invoice_id = i.invoice_id AND a.tenant_id = i.tenant_id AND a.status = 'active'
        WHERE i.status = 'scheduled'
          AND i.scheduled_for IS NOT NULL
          AND i.scheduled_for <= %s
          AND a.channel != 'escrow'
        ORDER BY i.scheduled_for ASC, i.invoice_id ASC
        LIMIT 50
        """,
        (today,),
    ).fetchall()

    results: list[dict[str, Any]] = []
    for row in due_rows:
        try:
            raw_resp = gate_client.create_intent(
                invoice_id=row["invoice_id"], approval_id=row["approval_id"]
            )
            # B3: handle BOTH flat PaymentIntent (200/201) AND 422 Problem with nested `payment_intent`
            pi_obj = (
                raw_resp["payment_intent"]
                if isinstance(raw_resp.get("payment_intent"), dict)
                else raw_resp
            )
            pi_id = pi_obj.get("payment_intent_id")
            gate_apv_id = pi_obj.get("approval_id")
            gate_inv_id = pi_obj.get("invoice_id")
            gate_tid = pi_obj.get("tenant_id")
            # B3 rest: missing approval/invoice or tenant/invoice mismatch counts as unresolved (never fall back to requested ID!)
            if (
                not isinstance(pi_id, str)
                or not pi_id.strip()
                or not isinstance(gate_apv_id, str)
                or not gate_apv_id.strip()
                or gate_inv_id != row["invoice_id"]
                or (gate_tid is not None and gate_tid != row["tenant_id"])
            ):
                logger.warning(
                    "Ignoring incomplete/mismatched Gate create_intent response for invoice %s: %s",
                    row["invoice_id"],
                    raw_resp,
                )
                continue

            gate_ts = _parse_gate_ts(pi_obj.get("created_at"))
            with conn.transaction():
                _upsert_payment_intent_link(
                    conn,
                    payment_intent_id=pi_id.strip(),
                    tenant_id=row["tenant_id"],
                    invoice_id=row["invoice_id"],
                    approval_id=gate_apv_id.strip(),
                    gate_created_at=gate_ts,
                    now=clk.now(),
                )
            if pi_obj.get("status") == "authorized" and gate_apv_id.strip() == row["approval_id"]:
                exec_res = gate_client.execute_intent(payment_intent_id=pi_id.strip())
                results.append(exec_res)
            else:
                results.append(raw_resp)
        except UpstreamToolError as exc:
            logger.warning("Gate error executing scheduled invoice %s: %s", row["invoice_id"], exc.detail)
    return results


def run_worker_tick(
    db: Database,
    *,
    source_port: InvoiceSourcePort | None,
    gate_client: GateClientPort,
    clock: Clock | None = None,
    max_invoice_bytes: int = 5 * 1024 * 1024,
    max_xml_elements: int = 10_000,
    default_due_days: int = 7,
) -> dict[str, int]:
    """Run one complete tick of core-worker (poller, core.outbox, ledger.outbox, scheduled payments, preview prune)."""
    clk = clock or SystemClock()
    ingested_count = 0
    core_events = 0
    ledger_events = 0
    scheduled_runs = 0

    with db.connect() as conn:
        if source_port is not None:
            try:
                ingested = poll_sources_once(
                    conn,
                    source_port,
                    clock=clk,
                    max_invoice_bytes=max_invoice_bytes,
                    max_xml_elements=max_xml_elements,
                    default_due_days=default_due_days,
                )
                ingested_count = sum(1 for r in ingested if not r.already_existed)
            except Exception:
                logger.warning("poll_sources_once failed; continuing outbox dispatch", exc_info=True)
        core_events = process_core_outbox_once(conn, gate_client, clock=clk)
        # Second pass in same tick so chained events (job.completed -> approved -> scheduled) settle promptly
        core_events += process_core_outbox_once(conn, gate_client, clock=clk)
        ledger_events = process_ledger_outbox_once(conn, gate_client=gate_client, clock=clk)
        scheduled_runs = len(execute_scheduled_payments_once(conn, gate_client, clock=clk))
        # Nit 1: prune expired approval_previews
        try:
            with conn.transaction():
                conn.execute(
                    "DELETE FROM core.approval_previews WHERE expires_at < clock_timestamp()"
                )
        except psycopg.Error:
            logger.warning("Failed to prune expired approval_previews", exc_info=True)

    return {
        "ingested": ingested_count,
        "core_events": core_events,
        "ledger_events": ledger_events,
        "scheduled_runs": scheduled_runs,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = CoreSettings.from_env()
    db = Database(cfg.database_url)
    source_port = SimWorldInvoiceSourceAdapter(
        cfg.sim_url,
        cfg.sim_core_service_key,
        max_invoice_bytes=cfg.max_invoice_bytes,
    )
    gate_client = HttpGateAdapter(cfg.gate_url, cfg.gate_core_service_key)
    clk: Clock = (
        SimWorldClock(cfg.sim_url, cfg.sim_core_service_key) if cfg.demo_mode else SystemClock()
    )
    logger.info("Starting core-worker loop (interval=%.1fs)", cfg.worker_poll_interval_s)
    while True:
        try:
            stats = run_worker_tick(
                db,
                source_port=source_port,
                gate_client=gate_client,
                clock=clk,
                max_invoice_bytes=cfg.max_invoice_bytes,
                max_xml_elements=cfg.max_xml_elements,
                default_due_days=cfg.default_due_days,
            )
            if any(stats.values()):
                logger.info("core-worker tick: %s", stats)
        except Exception:
            logger.exception("core-worker tick error")
        time.sleep(cfg.worker_poll_interval_s)


if __name__ == "__main__":
    main()

"""Tests for core-worker loops: F1/F2 auto-pay + scheduling + Gate + ledger.outbox, QT-03, F3 cross-alert after approval, stale approval superseded."""

from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from core.entrypoints.internal_api import create_internal_app
from core.entrypoints.worker import (
    execute_scheduled_payments_once,
    process_core_outbox_once,
    process_ledger_outbox_once,
    run_worker_tick,
)
from core.ingest.application.ingest_invoice import IngestCommand, ingest_invoice
from core.persistence.db import Database
from core.risk.application.cross_alerts import publish_cross_alert
from core.shared.clock import FixedClock
from core.shared.config import CoreSettings
from core.shared.hashing import hash_tax_id_indicator, intent_hash_invoice
from core.shared.ids import new_id
from core.tools.ports import GateEvaluation

VN_TZ = timezone(timedelta(hours=7))
DEMO_DATA_DIR = pathlib.Path(__file__).resolve().parents[3] / "services" / "sim-world" / "data" / "demo"

TENANT_A = "ten_01M88D3C06B97Y4G0S9W8BVKNG"
TENANT_B = "ten_01M88AXX2KPMD46VQQTDDH040J"
AGENT_KEY = "worker-test-key"


class RecordingGate:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, str]] = []  # (pi_id, invoice_id, approval_id)
        self.executed: list[str] = []
        self.cancelled: list[tuple[str, str]] = []
        self.authorized_by_invoice: dict[str, list[dict[str, Any]]] = {}

    def evaluate_invoice(self, *, invoice_id: str, tenant_id: str) -> GateEvaluation:
        return GateEvaluation(
            decision="ALLOW",
            allowed_methods=["single"],
            verification_required=False,
            intent_hash="a" * 64,
            payee_account_id="vac_01M885170DEVTBBKXKDK90DBAS",
            amount_vnd=26500000,
            channel="bank_transfer",
            reasons=[],
            evaluated_at="2026-11-26T09:00:00+07:00",
        )

    def get_daily_budget(self, *, tenant_id: str, date_str: str) -> dict[str, Any]:
        return {
            "date": date_str,
            "auto_pay_used_vnd": 0,
            "auto_pay_reserved_vnd": 0,
            "auto_pay_limit_vnd": 50_000_000,
            "total_paid_vnd": 0,
        }

    def create_intent(self, *, invoice_id: str, approval_id: str) -> dict[str, Any]:
        pi_id = new_id("pi")
        self.created.append((pi_id, invoice_id, approval_id))
        rec = {"payment_intent_id": pi_id, "invoice_id": invoice_id, "status": "authorized"}
        self.authorized_by_invoice.setdefault(invoice_id, []).append(rec)
        return rec

    def execute_intent(self, *, payment_intent_id: str) -> dict[str, Any]:
        self.executed.append(payment_intent_id)
        return {"payment_intent_id": payment_intent_id, "status": "settled"}

    def cancel_intent(self, *, payment_intent_id: str, reason: str) -> dict[str, Any]:
        self.cancelled.append((payment_intent_id, reason))
        return {"payment_intent_id": payment_intent_id, "status": "expired"}

    def list_intents(self, *, tenant_id: str, invoice_id: str | None = None, status: str | None = None):
        if invoice_id:
            return list(self.authorized_by_invoice.get(invoice_id, []))
        return []


class DummySim:
    def lookup_einvoice_portal(self, *, seller_tax_id: str, symbol: str, number: str):
        return {
            "found": True,
            "invoice_status_code": 1,
            "invoice_status_label": "Mới",
            "processing_status_code": 5,
            "processing_status_label": "Đã cấp mã",
            "illegal_flag": False,
            "tax_authority_code": "00BACF19B7832F6A604EAD35C7D18858E5",
            "total_vnd": 26500000,
            "related_invoice": None,
        }

    def lookup_taxpayer(self, *, tax_id: str):
        return {
            "tax_id": tax_id,
            "name": "CÔNG TY MẪU",
            "status_code": "00",
            "status_label": "Đang hoạt động",
            "status_reason_code": "02",
            "address": "TP.HCM",
        }

    def lookup_tax_risk_list(self, *, tax_id: str):
        return {"listed": False, "list_name": None, "listed_on": None}

    def check_simo_indicator(self, *, kind: str, value_hash: str):
        return {"listed": False, "list_ref": None}

    def get_wallet_balance(self, *, wallet_id: str):
        return {"wallet_id": wallet_id, "balance_vnd": 350_000_000, "as_of": "2026-11-26T09:00:00+07:00"}

    def get_inbox_messages(self, **kw):
        return []

    def get_chat_threads(self, **kw):
        return []

    def get_chat_messages(self, **kw):
        return []

    def get_momo_revenue(self, **kw):
        return {"revenue_vnd": 300_000_000, "transaction_count": 4000}

    def reset_scenario(self, **kw):
        return {"loaded_at": "2026-11-26T08:00:00+07:00", "counts": {}}


def _ensure_ledger_outbox(db: Database) -> None:
    """Create a simulated ledger.outbox matching the shared Event envelope for worker tests."""
    with db.connect() as conn:
        with conn.transaction():
            conn.execute("CREATE SCHEMA IF NOT EXISTS ledger")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger.outbox (
                    seq BIGSERIAL,
                    event_id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    schema_version INT NOT NULL DEFAULT 1,
                    occurred_at TIMESTAMPTZ NOT NULL,
                    tenant_id TEXT NULL,
                    trace_id TEXT NULL,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            conn.execute("TRUNCATE TABLE ledger.outbox RESTART IDENTITY")
            conn.execute("GRANT USAGE ON SCHEMA ledger TO worker")
            conn.execute("GRANT SELECT ON ledger.outbox TO worker")


@pytest.mark.db
def test_f2_autopay_scheduling_gate_and_ledger_outbox_to_paid(
    seeded_db: Database, fixed_clock: FixedClock
) -> None:
    """F2: green coffee 26.5M -> auto_pay_eligible -> worker mandate approval -> scheduled -> Gate execute -> ledger.outbox -> paid."""
    _ensure_ledger_outbox(seeded_db)
    coffee_xml = (DEMO_DATA_DIR / "inbox/attachments/1C26TTN_00001425.xml").read_bytes()
    with seeded_db.connect() as conn:
        res = ingest_invoice(
            conn,
            IngestCommand(
                tenant_id=TENANT_A,
                raw_bytes=coffee_xml,
                filename="1C26TTN_00001425.xml",
                content_type="application/xml",
                source="email",
                due_on_hint=fixed_clock.today(),
            ),
            clock=fixed_clock,
        )
    inv_id, job_id = res.invoice_id, res.job_id
    assert job_id is not None

    gate = RecordingGate()
    cfg = CoreSettings(database_url=seeded_db.dsn, internal_agent_service_key=AGENT_KEY)
    iapp = create_internal_app(cfg, db=seeded_db, sim_world=DummySim(), gate_client=gate, clock=fixed_clock)
    ic = TestClient(iapp)
    hdr = {"X-Service-Key": AGENT_KEY}

    # Run all required bots -> OK, treasury proposes today
    claimed = ic.post("/internal/jobs:claim", json={"worker_id": "w1"}, headers=hdr).json()
    sess = ic.post(
        f"/internal/jobs/{job_id}/session",
        json={"worker_id": "w1", "attempt": claimed["attempt"]},
        headers=hdr,
    ).json()
    for b in sess["bots"]:
        bhdr = {"Authorization": f"Bearer {b['capability_token']}"}
        for pf in b["prefetch"]:
            inp = {"tax_id": "0999010001"} if pf in {"tax_id_lookup", "tax_risk_list"} else {}
            r = ic.post(f"/internal/tools/{pf}:invoke", json={"input": inp}, headers=bhdr)
            assert r.status_code == 200
        ic.post(
            f"/internal/jobs/{job_id}/findings",
            json={
                "bot_id": b["bot_id"],
                "bot_version": b["bot_version"],
                "skill_version": 1,
                "prompt_hash": "sha256:ok",
                "severity_reported": "green",
                "reason_codes": ["OK"],
                "reason": "Khớp toàn bộ",
                "evidence": [],
                "provenance": "trusted",
                "proposed_pay_on": fixed_clock.today().isoformat() if b["bot_id"] == "treasury" else None,
            },
            headers=bhdr,
        )
    comp = ic.post(
        f"/internal/jobs/{job_id}:complete",
        json={
            "worker_id": "w1",
            "attempt": 1,
            "result": {"brief": {"lines": ["Khớp hợp đồng."], "cited_evidence": [], "model": "m", "prompt_hash": "p"}},
        },
        headers=hdr,
    )
    assert comp.status_code == 200
    assert comp.json()["invoice_status"] == "auto_pay_eligible"

    # Worker tick: creates mandate approval -> approved -> scheduled -> executes via Gate
    stats = run_worker_tick(seeded_db, source_port=None, gate_client=gate, clock=fixed_clock)
    assert stats["scheduled_runs"] == 1
    assert len(gate.created) == 1
    assert len(gate.executed) == 1
    pi_id = gate.created[0][0]

    # Simulate Gate writing payment.authorized & payment.executed to ledger.outbox
    with seeded_db.connect() as conn:
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO ledger.outbox (event_id, type, occurred_at, tenant_id, data)
                VALUES (%s, 'payment.authorized', %s, %s, %s),
                       (%s, 'payment.executed', %s, %s, %s)
                """,
                (
                    new_id("evt"),
                    fixed_clock.now(),
                    TENANT_A,
                    Jsonb({"payment_intent_id": pi_id, "invoice_id": inv_id, "amount_vnd": 26500000, "channel": "bank_transfer"}),
                    new_id("evt"),
                    fixed_clock.now(),
                    TENANT_A,
                    Jsonb({"payment_intent_id": pi_id, "invoice_id": inv_id, "rail_txn_id": "rtx_1", "settled_at": fixed_clock.now().isoformat()}),
                ),
            )

    run_worker_tick(seeded_db, source_port=None, gate_client=gate, clock=fixed_clock)
    with seeded_db.connect() as conn:
        inv = conn.execute("SELECT status FROM core.invoices WHERE invoice_id = %s", (inv_id,)).fetchone()
        apv = conn.execute("SELECT status, method FROM core.approvals WHERE invoice_id = %s", (inv_id,)).fetchone()
    assert inv["status"] == "paid"
    assert apv["status"] == "consumed"
    assert apv["method"] == "mandate"


@pytest.mark.db
def test_invariant_cross_alert_after_approval_re_evaluates_and_supersedes(
    seeded_db: Database, fixed_clock: FixedClock
) -> None:
    """Invariant (repo-and-testing.md §4): scheduled invoice + cross_alert.published -> pending_approval,
    CROSS_ALERT_HIT added, verification_required=True, old approval superseded, Gate intent cancelled, notification created.
    """
    syrup_xml = (DEMO_DATA_DIR / "inbox/attachments/1C26TAC_00000088.xml").read_bytes()
    with seeded_db.connect() as conn:
        res = ingest_invoice(
            conn,
            IngestCommand(
                tenant_id=TENANT_B,
                raw_bytes=syrup_xml,
                filename="syrup_b.xml",
                content_type="application/xml",
                source="email",
            ),
            clock=fixed_clock,
        )
        inv_b = res.invoice_id
        # Put Tenant B's invoice into `scheduled` with an active approval + authorized Gate intent
        va_b = conn.execute(
            "SELECT vendor_account_id FROM core.vendor_accounts WHERE tenant_id = %s LIMIT 1",
            (TENANT_B,),
        ).fetchone()["vendor_account_id"]
        apv_id = new_id("apv")
        with conn.transaction():
            conn.execute(
                """
                UPDATE core.invoices
                SET status = 'scheduled', severity = 'green', reason_codes = ARRAY['OK'],
                    scheduled_for = '2026-11-28', updated_at = %s
                WHERE invoice_id = %s
                """,
                (fixed_clock.now(), inv_b),
            )
            conn.execute(
                """
                INSERT INTO core.approvals (
                    approval_id, tenant_id, invoice_id, status, amount_vnd,
                    payee_account_id, channel, intent_hash, method, created_at
                )
                VALUES (%s, %s, %s, 'active', 8800000, %s, 'bank_transfer', %s, 'single', %s)
                """,
                (apv_id, TENANT_B, inv_b, va_b, "b" * 64, fixed_clock.now()),
            )

    gate = RecordingGate()
    pi_id = new_id("pi")
    gate.authorized_by_invoice[inv_b] = [{"payment_intent_id": pi_id, "invoice_id": inv_b, "status": "authorized"}]

    # MoMo specialist publishes cross alert on syrup seller MST 0999090001
    with seeded_db.connect() as conn:
        publish_cross_alert(
            conn,
            indicators=[{"kind": "tax_id", "value_hash": hash_tax_id_indicator("0999090001")}],
            reason_codes=["PERSONAL_ACCOUNT", "HIDDEN_INSTRUCTION"],
            published_by="stf_01",
            clock=fixed_clock,
        )
        process_core_outbox_once(conn, gate, clock=fixed_clock)

        inv_after = conn.execute(
            "SELECT status, severity, reason_codes, verification_required FROM core.invoices WHERE invoice_id = %s",
            (inv_b,),
        ).fetchone()
        apv_after = conn.execute(
            "SELECT status, superseded_reason FROM core.approvals WHERE approval_id = %s",
            (apv_id,),
        ).fetchone()
        ntfs = conn.execute(
            "SELECT kind, invoice_ids FROM core.notifications WHERE tenant_id = %s AND kind = 'cross_alert_affected'",
            (TENANT_B,),
        ).fetchall()

    assert inv_after["status"] == "pending_approval"
    assert inv_after["severity"] == "yellow"
    assert "CROSS_ALERT_HIT" in inv_after["reason_codes"]
    assert inv_after["verification_required"] is True
    assert apv_after["status"] == "superseded"
    assert apv_after["superseded_reason"] == "NEW_SYSTEM_FINDING"
    assert (pi_id, "CROSS_ALERT") in gate.cancelled
    assert len(ntfs) == 1 and inv_b in ntfs[0]["invoice_ids"]


@pytest.mark.db
def test_invariant_stale_approval_superseded_on_payment_failed_and_qt03_suspension(
    seeded_db: Database, fixed_clock: FixedClock
) -> None:
    """Invariant: payment.failed from ledger.outbox supersedes active approval (PAYMENT_FAILED) and moves invoice back to pending_approval; QT-03 suspends vendor."""
    _ensure_ledger_outbox(seeded_db)
    cups_xml = (DEMO_DATA_DIR / "inbox/attachments/1C26TNX_00000744.xml").read_bytes()
    with seeded_db.connect() as conn:
        res = ingest_invoice(
            conn,
            IngestCommand(
                tenant_id=TENANT_A,
                raw_bytes=cups_xml,
                filename="cups.xml",
                content_type="application/xml",
                source="email",
            ),
            clock=fixed_clock,
        )
        inv_id = res.invoice_id
        va = conn.execute(
            "SELECT vendor_account_id FROM core.vendor_accounts WHERE tenant_id = %s LIMIT 1",
            (TENANT_A,),
        ).fetchone()["vendor_account_id"]
        apv_id = new_id("apv")
        with conn.transaction():
            # Emit job.completed with QT-03 reason code
            conn.execute(
                """
                INSERT INTO core.outbox (event_id, type, occurred_at, tenant_id, data)
                VALUES (%s, 'job.completed', %s, %s, %s)
                """,
                (
                    new_id("evt"),
                    fixed_clock.now(),
                    TENANT_A,
                    Jsonb(
                        {
                            "job_id": res.job_id,
                            "task_type": "investigate_invoice",
                            "invoice_id": inv_id,
                            "final_severity": "yellow",
                            "reason_codes": ["PACK_SIZE_CHANGED", "PRICE_ABOVE_CONTRACT"],
                        }
                    ),
                ),
            )
            # Simulate invoice in paying with active approval and a payment.failed event in ledger.outbox
            conn.execute(
                "UPDATE core.invoices SET status = 'paying' WHERE invoice_id = %s", (inv_id,)
            )
            conn.execute(
                """
                INSERT INTO core.approvals (
                    approval_id, tenant_id, invoice_id, status, amount_vnd,
                    payee_account_id, channel, intent_hash, method, created_at
                )
                VALUES (%s, %s, %s, 'active', 22400000, %s, 'bank_transfer', %s, 'single', %s)
                """,
                (apv_id, TENANT_A, inv_id, va, "c" * 64, fixed_clock.now()),
            )
            conn.execute(
                """
                INSERT INTO ledger.outbox (event_id, type, occurred_at, tenant_id, data)
                VALUES (%s, 'payment.failed', %s, %s, %s)
                """,
                (
                    new_id("evt"),
                    fixed_clock.now(),
                    TENANT_A,
                    Jsonb({"payment_intent_id": new_id("pi"), "invoice_id": inv_id, "failure_code": "INSUFFICIENT_FUNDS"}),
                ),
            )

        process_core_outbox_once(conn, RecordingGate(), clock=fixed_clock)
        process_ledger_outbox_once(conn, clock=fixed_clock)

        inv_row = conn.execute("SELECT status, vendor_id FROM core.invoices WHERE invoice_id = %s", (inv_id,)).fetchone()
        apv_row = conn.execute("SELECT status, superseded_reason FROM core.approvals WHERE approval_id = %s", (apv_id,)).fetchone()
        susp = conn.execute(
            "SELECT reason_codes FROM core.auto_pay_suspensions WHERE tenant_id = %s AND vendor_id = %s AND lifted_at IS NULL",
            (TENANT_A, inv_row["vendor_id"]),
        ).fetchone()

    assert inv_row["status"] == "pending_approval"
    assert apv_row["status"] == "superseded"
    assert apv_row["superseded_reason"] == "PAYMENT_FAILED"
    assert susp is not None
    assert "PACK_SIZE_CHANGED" in susp["reason_codes"]


@pytest.mark.db
def test_i6_payment_expired_authorization_timeout_reuses_active_approval_else_pending(
    seeded_db: Database, fixed_clock: FixedClock
) -> None:
    """Contract I6: payment.expired AUTHORIZATION_TIMEOUT -> scheduled if approval still active & valid; else pending_approval."""
    _ensure_ledger_outbox(seeded_db)
    xml_1 = (DEMO_DATA_DIR / "inbox/attachments/1C26TTN_00001425.xml").read_bytes()
    xml_2 = (DEMO_DATA_DIR / "inbox/attachments/1C26TNX_00000744.xml").read_bytes()

    with seeded_db.connect() as conn:
        r1 = ingest_invoice(
            conn,
            IngestCommand(
                tenant_id=TENANT_A,
                raw_bytes=xml_1,
                filename="1.xml",
                content_type="application/xml",
                source="email",
            ),
            clock=fixed_clock,
        )
        r2 = ingest_invoice(
            conn,
            IngestCommand(
                tenant_id=TENANT_A,
                raw_bytes=xml_2,
                filename="2.xml",
                content_type="application/xml",
                source="email",
            ),
            clock=fixed_clock,
        )
        va = conn.execute(
            "SELECT vendor_account_id FROM core.vendor_accounts WHERE tenant_id = %s LIMIT 1",
            (TENANT_A,),
        ).fetchone()["vendor_account_id"]

        with conn.transaction():
            # Invoice 1: paying + still-active valid approval bound to completed job -> should return to scheduled
            conn.execute(
                "UPDATE core.jobs SET status = 'completed', completed_at = %s WHERE job_id = %s",
                (fixed_clock.now(), r1.job_id),
            )
            conn.execute("UPDATE core.invoices SET status = 'paying' WHERE invoice_id = %s", (r1.invoice_id,))
            conn.execute(
                """
                INSERT INTO core.approvals (
                    approval_id, tenant_id, invoice_id, job_id, status, amount_vnd,
                    payee_account_id, channel, intent_hash, method, created_at
                )
                VALUES (%s, %s, %s, %s, 'active', 26500000, %s, 'bank_transfer', %s, 'single', %s)
                """,
                (new_id("apv"), TENANT_A, r1.invoice_id, r1.job_id, va, "d" * 64, fixed_clock.now()),
            )
            # Invoice 2: paying + NO active approval -> should return to pending_approval
            conn.execute("UPDATE core.invoices SET status = 'paying' WHERE invoice_id = %s", (r2.invoice_id,))

            conn.execute(
                """
                INSERT INTO ledger.outbox (event_id, type, occurred_at, tenant_id, data)
                VALUES (%s, 'payment.expired', %s, %s, %s),
                       (%s, 'payment.expired', %s, %s, %s)
                """,
                (
                    new_id("evt"),
                    fixed_clock.now(),
                    TENANT_A,
                    Jsonb({"payment_intent_id": new_id("pi"), "invoice_id": r1.invoice_id, "reason": "AUTHORIZATION_TIMEOUT"}),
                    new_id("evt"),
                    fixed_clock.now(),
                    TENANT_A,
                    Jsonb({"payment_intent_id": new_id("pi"), "invoice_id": r2.invoice_id, "reason": "AUTHORIZATION_TIMEOUT"}),
                ),
            )

        process_ledger_outbox_once(conn, clock=fixed_clock)
        st1 = conn.execute("SELECT status FROM core.invoices WHERE invoice_id = %s", (r1.invoice_id,)).fetchone()["status"]
        st2 = conn.execute("SELECT status FROM core.invoices WHERE invoice_id = %s", (r2.invoice_id,)).fetchone()["status"]

    assert st1 == "scheduled"
    assert st2 == "pending_approval"


@pytest.mark.db
def test_b2_outbox_receipts_picks_up_late_committed_lower_seq(
    seeded_db: Database, worker_db: Database, fixed_clock: FixedClock
) -> None:
    """B2: two independent connections commit outbox seq N+1 before seq N; receipt table picks up both with zero skips."""
    _ensure_ledger_outbox(seeded_db)
    hash_early = hash_tax_id_indicator("0399000001")
    hash_late = hash_tax_id_indicator("0399000002")
    evt_n = new_id("evt")
    evt_n1 = new_id("evt")

    # Connection 1 opens tx and allocates lower seq N (uncommitted)
    with seeded_db.connect() as conn1, seeded_db.connect() as conn2:
        conn1.execute(
            """
            INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, data)
            VALUES (%s, 'indicator.flagged', 1, %s, NULL, %s)
            """,
            (
                evt_n,
                fixed_clock.now(),
                Jsonb(
                    {
                        "indicators": [{"kind": "tax_id", "value_hash": hash_early}],
                        "reason_codes": ["OFFICIAL_FRAUD_LIST"],
                        "source": "finding",
                        "source_ref": "srf_early",
                    }
                ),
            ),
        )
        # Connection 2 inserts higher seq N+1 and commits FIRST
        conn2.execute(
            """
            INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, data)
            VALUES (%s, 'indicator.flagged', 1, %s, NULL, %s)
            """,
            (
                evt_n1,
                fixed_clock.now(),
                Jsonb(
                    {
                        "indicators": [{"kind": "tax_id", "value_hash": hash_late}],
                        "reason_codes": ["OFFICIAL_FRAUD_LIST"],
                        "source": "finding",
                        "source_ref": "srf_late",
                    }
                ),
            ),
        )
        conn2.commit()

        # Worker (non-superuser role!) polls while conn1 is still uncommitted -> processes N+1
        with worker_db.connect() as wconn:
            n_first = process_core_outbox_once(wconn, RecordingGate(), clock=fixed_clock)
        assert n_first == 1

        # Now conn1 commits lower seq N
        conn1.commit()

    # Next worker poll MUST pick up seq N (receipt table prevents seq cursor skip)
    with worker_db.connect() as wconn:
        n_second = process_core_outbox_once(wconn, RecordingGate(), clock=fixed_clock)
        hashes = {
            r["value_hash"]
            for r in wconn.execute("SELECT value_hash FROM risk.indicators").fetchall()
        }
    assert n_second == 1
    assert hash_early in hashes
    assert hash_late in hashes


@pytest.mark.db
def test_i3_cross_alert_creates_qt03_suspension_and_blocks_second_invoice_autopay(
    seeded_db: Database, worker_db: Database, fixed_clock: FixedClock
) -> None:
    """I3 & Nit 2: cross_alert creates QT-03 suspension for vendor; second auto_pay_eligible invoice is revalidated and demoted."""
    xml_1 = (DEMO_DATA_DIR / "inbox/attachments/1C26TTN_00001425.xml").read_bytes()
    xml_2 = (DEMO_DATA_DIR / "inbox/attachments/1C26TTN_00001430.xml").read_bytes()

    with seeded_db.connect() as conn:
        r1 = ingest_invoice(
            conn,
            IngestCommand(tenant_id=TENANT_A, raw_bytes=xml_1, filename="c1.xml", content_type="application/xml", source="email"),
            clock=fixed_clock,
        )
        r2 = ingest_invoice(
            conn,
            IngestCommand(tenant_id=TENANT_A, raw_bytes=xml_2, filename="c2.xml", content_type="application/xml", source="email"),
            clock=fixed_clock,
        )
        inv1_row = conn.execute("SELECT vendor_id, seller_tax_id FROM core.invoices WHERE invoice_id = %s", (r1.invoice_id,)).fetchone()
        with conn.transaction():
            conn.execute(
                "UPDATE core.invoices SET status = 'pending_approval', severity = 'green' WHERE invoice_id = %s",
                (r1.invoice_id,),
            )
            conn.execute(
                "UPDATE core.invoices SET status = 'auto_pay_eligible', severity = 'green' WHERE invoice_id = %s",
                (r2.invoice_id,),
            )
            conn.execute(
                "UPDATE core.jobs SET status = 'completed', completed_at = %s WHERE job_id = %s",
                (fixed_clock.now(), r2.job_id),
            )
        # Publish cross_alert matching inv1's vendor tax_id -> should create QT-03 suspension!
        publish_cross_alert(
            conn,
            indicators=[{"kind": "tax_id", "value_hash": hash_tax_id_indicator(inv1_row["seller_tax_id"])}],
            reason_codes=["PERSONAL_ACCOUNT"],
            published_by="stf_01",
            clock=fixed_clock,
        )

    with worker_db.connect() as wconn:
        process_core_outbox_once(wconn, RecordingGate(), clock=fixed_clock)
        susp = wconn.execute(
            "SELECT reason_codes FROM core.auto_pay_suspensions WHERE tenant_id = %s AND vendor_id = %s AND lifted_at IS NULL",
            (TENANT_A, inv1_row["vendor_id"]),
        ).fetchone()
    assert susp is not None
    assert "CROSS_ALERT_HIT" in susp["reason_codes"]

    # Now emit job.completed for invoice 2 (same vendor, still marked auto_pay_eligible before suspension)
    with seeded_db.connect() as conn:
        with conn.transaction():
            conn.execute(
                "UPDATE core.invoices SET status = 'auto_pay_eligible', severity = 'green', verification_required = FALSE WHERE invoice_id = %s",
                (r2.invoice_id,),
            )
            conn.execute(
                """
                INSERT INTO core.outbox (event_id, type, occurred_at, tenant_id, data)
                VALUES (%s, 'job.completed', %s, %s, %s)
                """,
                (
                    new_id("evt"),
                    fixed_clock.now(),
                    TENANT_A,
                    Jsonb({"job_id": r2.job_id, "task_type": "investigate_invoice", "invoice_id": r2.invoice_id, "final_severity": "green", "reason_codes": ["OK"]}),
                ),
            )

    with worker_db.connect() as wconn:
        process_core_outbox_once(wconn, RecordingGate(), clock=fixed_clock)
        inv2_after = wconn.execute("SELECT status FROM core.invoices WHERE invoice_id = %s", (r2.invoice_id,)).fetchone()
        apvs = wconn.execute("SELECT approval_id FROM core.approvals WHERE invoice_id = %s", (r2.invoice_id,)).fetchall()
    assert inv2_after["status"] == "pending_approval"
    assert apvs == []


@pytest.mark.db
def test_i4_late_payment_events_do_not_invalidate_newer_approval(
    seeded_db: Database, worker_db: Database, fixed_clock: FixedClock
) -> None:
    """I4: late payment.failed/denied for an older intent generation MUST NOT supersede a newer active approval."""
    _ensure_ledger_outbox(seeded_db)
    xml_1 = (DEMO_DATA_DIR / "inbox/attachments/1C26TTN_00001425.xml").read_bytes()
    with seeded_db.connect() as conn:
        r1 = ingest_invoice(
            conn,
            IngestCommand(tenant_id=TENANT_A, raw_bytes=xml_1, filename="gen.xml", content_type="application/xml", source="email"),
            clock=fixed_clock,
        )
        va = conn.execute(
            "SELECT vendor_account_id FROM core.vendor_accounts WHERE tenant_id = %s LIMIT 1",
            (TENANT_A,),
        ).fetchone()["vendor_account_id"]
        apv_old = new_id("apv")
        apv_new = new_id("apv")
        pi_old = new_id("pi")
        with conn.transaction():
            conn.execute(
                "UPDATE core.invoices SET status = 'scheduled', scheduled_for = '2026-11-28' WHERE invoice_id = %s",
                (r1.invoice_id,),
            )
            conn.execute(
                """
                INSERT INTO core.approvals (
                    approval_id, tenant_id, invoice_id, job_id, status, amount_vnd,
                    payee_account_id, channel, intent_hash, method, created_at
                )
                VALUES
                    (%s, %s, %s, %s, 'superseded', 26500000, %s, 'bank_transfer', %s, 'single', %s),
                    (%s, %s, %s, %s, 'active', 26500000, %s, 'bank_transfer', %s, 'single', %s)
                """,
                (
                    apv_old, TENANT_A, r1.invoice_id, r1.job_id, va, "e" * 64, fixed_clock.now(),
                    apv_new, TENANT_A, r1.invoice_id, r1.job_id, va, "f" * 64, fixed_clock.now(),
                ),
            )
            conn.execute(
                """
                INSERT INTO core.payment_intent_links (payment_intent_id, tenant_id, invoice_id, approval_id, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (pi_old, TENANT_A, r1.invoice_id, apv_old, fixed_clock.now()),
            )
            # Late payment.failed and payment.denied for OLD pi_old arrive!
            conn.execute(
                """
                INSERT INTO ledger.outbox (event_id, type, occurred_at, tenant_id, data)
                VALUES (%s, 'payment.failed', %s, %s, %s),
                       (%s, 'payment.denied', %s, %s, %s)
                """,
                (
                    new_id("evt"), fixed_clock.now(), TENANT_A,
                    Jsonb({"payment_intent_id": pi_old, "invoice_id": r1.invoice_id, "failure_code": "TIMEOUT"}),
                    new_id("evt"), fixed_clock.now(), TENANT_A,
                    Jsonb({"payment_intent_id": pi_old, "invoice_id": r1.invoice_id, "gate_reasons": [{"code": "OVER_LIMIT"}]}),
                ),
            )

    with worker_db.connect() as wconn:
        process_ledger_outbox_once(wconn, clock=fixed_clock)
        inv = wconn.execute("SELECT status FROM core.invoices WHERE invoice_id = %s", (r1.invoice_id,)).fetchone()
        apv = wconn.execute("SELECT status FROM core.approvals WHERE approval_id = %s", (apv_new,)).fetchone()
    assert inv["status"] == "scheduled"
    assert apv["status"] == "active"


@pytest.mark.db
def test_i8_poller_checkpoints_terminal_page_and_isolates_failures(
    seeded_db: Database, worker_db: Database, fixed_clock: FixedClock
) -> None:
    """I8: terminal page (next_cursor=None) checkpoints last message_id/bill_id; per-tenant errors are isolated."""
    from core.ingest.application.poller import InboxAttachment, InboxMessage, poll_sources_once

    xml_bytes = (DEMO_DATA_DIR / "inbox/attachments/1C26TTN_00001425.xml").read_bytes()

    with worker_db.connect() as wconn:
        mbs = [
            r["mailbox"]
            for r in wconn.execute("SELECT mailbox FROM core.tenants ORDER BY tenant_id").fetchall()
        ]
    failing_mailbox, ok_mailbox = mbs[0], mbs[1]

    class StubSource:
        def __init__(self) -> None:
            self.inbox_calls: list[tuple[str, str | None]] = []
            self.bills_calls: list[tuple[str, str | None]] = []

        def list_inbox_messages(self, mailbox: str, after: str | None = None):
            self.inbox_calls.append((mailbox, after))
            if mailbox == failing_mailbox:
                raise RuntimeError("simulated upstream 503 on one tenant mailbox")
            if after == "msg_term_01":
                return [], None
            return [
                InboxMessage(
                    message_id="msg_term_01",
                    from_address="billing@vendor.test",
                    subject="Hoa don",
                    body_text="Gui hoa don",
                    received_at=fixed_clock.now(),
                    attachments=(
                        InboxAttachment(
                            attachment_id="att_1",
                            filename="1C26TTN_00001425.xml",
                            content_type="application/xml",
                            raw_bytes=xml_bytes,
                        ),
                    ),
                )
            ], None  # terminal page: next_cursor is None!

        def list_bills(self, wallet_id: str, after: str | None = None):
            self.bills_calls.append((wallet_id, after))
            return [], None

        def fetch_bill_document(self, bill_id: str) -> bytes | None:
            return None

    src = StubSource()
    with worker_db.connect() as wconn:
        res1 = poll_sources_once(wconn, src, clock=fixed_clock)
        res2 = poll_sources_once(wconn, src, clock=fixed_clock)

    assert len(res1) == 1
    assert res2 == []
    # Second call for ok_mailbox received after='msg_term_01' (checkpointed on terminal page!)
    ok_calls = [after for mb, after in src.inbox_calls if mb == ok_mailbox]
    assert ok_calls == [None, "msg_term_01"]

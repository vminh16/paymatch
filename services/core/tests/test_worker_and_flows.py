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
            # Invoice 1: paying + still-active valid approval -> should return to scheduled
            conn.execute("UPDATE core.invoices SET status = 'paying' WHERE invoice_id = %s", (r1.invoice_id,))
            conn.execute(
                """
                INSERT INTO core.approvals (
                    approval_id, tenant_id, invoice_id, status, amount_vnd,
                    payee_account_id, channel, intent_hash, method, created_at
                )
                VALUES (%s, %s, %s, 'active', 26500000, %s, 'bank_transfer', %s, 'single', %s)
                """,
                (new_id("apv"), TENANT_A, r1.invoice_id, va, "d" * 64, fixed_clock.now()),
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

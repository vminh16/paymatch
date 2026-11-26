"""Postgres 16 DB tests for Payment Gate safety invariants (testcontainers, @pytest.mark.db).

Mirrors the documented read-only core/control/risk schema contract from
`gate/adapters/postgres/read_store.py` and runs Gate's real `ledger` migrations.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from testcontainers.postgres import PostgresContainer

from gate.adapters.fakes import FakeClock, FakePaymentRail
from gate.adapters.http import create_app
from gate.adapters.postgres import PostgresCoreReadStore, PostgresLedgerStore, apply_migrations
from gate.config import Settings
from gate.domain.hashing import (
    compute_escrow_intent_hash,
    compute_invoice_intent_hash,
    hash_tax_id_indicator,
)
from gate.domain.models import GateDeniedError
from gate.ports.rail import RailTransferResult

from gate_fixtures import (
    ACC_COFFEE,
    ACC_SYRUP_ESCROW,
    APV_01,
    APV_02,
    APV_ESC_CREATE,
    APV_ESC_RELEASE,
    DOC_SHA_COFFEE,
    DOC_SHA_SYRUP,
    GRN_01,
    INV_COFFEE,
    INV_COFFEE_2,
    INV_SYRUP,
    JOB_01,
    NOW_VN,
    PO_01,
    SERVICE_KEYS,
    STORE_01,
    TENANT_A,
    USER_OWNER,
    VENDOR_COFFEE,
    VENDOR_SYRUP,
    WALLET_A,
    validate_outbox_event_against_contract,
)

# Mirrors the documented read-only cross-schema tables owned by `core`.
CORE_CONTROL_RISK_FIXTURE_DDL = """
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS control;
CREATE SCHEMA IF NOT EXISTS risk;

CREATE TABLE core.tenants (
    tenant_id TEXT PRIMARY KEY,
    wallet_id TEXT NOT NULL
);

CREATE TABLE core.vendors (
    vendor_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    tax_id TEXT NOT NULL,
    phone_on_file TEXT NULL,
    status TEXT NOT NULL
);

CREATE TABLE core.vendor_accounts (
    vendor_account_id TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    bank_code TEXT NULL,
    bank_name TEXT NULL,
    account_number TEXT NULL,
    merchant_id TEXT NULL,
    account_name TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE core.mandates (
    mandate_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    version INT NOT NULL,
    mode TEXT NOT NULL,
    limits JSONB NOT NULL,
    auto_pay_vendor_ids JSONB NOT NULL,
    channel_rules JSONB NOT NULL,
    bulk_approvable JSONB NOT NULL,
    auto_pay_window JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE core.auto_pay_suspensions (
    tenant_id TEXT NOT NULL,
    vendor_id TEXT NOT NULL,
    lifted_at TIMESTAMPTZ NULL
);

CREATE TABLE core.invoices (
    invoice_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    store_id TEXT NULL,
    vendor_id TEXT NULL,
    purchase_order_id TEXT NULL,
    seller_tax_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    number TEXT NOT NULL,
    invoice_type TEXT NOT NULL,
    total_vnd BIGINT NULL,
    status TEXT NOT NULL,
    severity TEXT NULL,
    reason_codes TEXT[] NOT NULL DEFAULT '{}',
    document_sha256 TEXT NOT NULL
);

CREATE TABLE core.jobs (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    invoice_id TEXT NULL,
    status TEXT NOT NULL,
    completed_at TIMESTAMPTZ NULL
);

CREATE TABLE core.approvals (
    approval_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    invoice_id TEXT NULL,
    purchase_order_id TEXT NULL,
    source_invoice_id TEXT NULL,
    job_id TEXT NULL,
    status TEXT NOT NULL,
    method TEXT NOT NULL,
    amount_vnd BIGINT NOT NULL,
    payee_account_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    approver_user_id TEXT NULL,
    mandate_version INT NULL,
    bulk_batch_id TEXT NULL,
    verification JSONB NULL
);

CREATE TABLE core.purchase_orders (
    purchase_order_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    vendor_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    total_vnd BIGINT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE core.goods_receipts (
    goods_receipt_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    purchase_order_id TEXT NOT NULL,
    store_id TEXT NOT NULL
);

CREATE TABLE control.policies (
    policy_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('platform_limits', 'kill_switch')),
    scope TEXT NULL,
    target_id TEXT NULL,
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    engaged_by TEXT NULL,
    released_by TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE risk.indicators (
    indicator_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    value_hash TEXT NOT NULL
);

CREATE TABLE risk.hard_blocks (
    hard_block_id TEXT PRIMARY KEY,
    indicator_kind TEXT NOT NULL,
    value_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE risk.cross_alerts (
    cross_alert_id TEXT PRIMARY KEY,
    indicator_kind TEXT NOT NULL,
    value_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@pytest.fixture(scope="module")
def pg_conninfo():
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(CORE_CONTROL_RISK_FIXTURE_DDL)
        applied = apply_migrations(url)
        assert "001_init_ledger.sql" in applied
        # Idempotent re-run applies nothing new
        assert apply_migrations(url) == []
        yield url


@pytest.fixture()
def db_env(pg_conninfo: str):
    """Reset all tables and seed baseline tenant/vendor/mandate/platform_limits before each test."""
    with psycopg.connect(pg_conninfo, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE
                    ledger.outbox,
                    ledger.rail_transactions,
                    ledger.daily_budgets,
                    ledger.ledger_entries,
                    ledger.payment_tokens,
                    ledger.payment_intents,
                    ledger.escrows,
                    core.goods_receipts,
                    core.purchase_orders,
                    core.approvals,
                    core.jobs,
                    core.invoices,
                    core.auto_pay_suspensions,
                    core.mandates,
                    core.vendor_accounts,
                    core.vendors,
                    core.tenants,
                    control.policies,
                    risk.indicators,
                    risk.hard_blocks,
                    risk.cross_alerts
                RESTART IDENTITY CASCADE;
                """
            )
            cur.execute(
                "INSERT INTO core.tenants (tenant_id, wallet_id) VALUES (%s, %s);",
                (TENANT_A, WALLET_A),
            )
            cur.execute(
                """
                INSERT INTO core.vendors (vendor_id, tenant_id, name, tax_id, phone_on_file, status)
                VALUES
                    (%s, %s, 'CÔNG TY TNHH CÀ PHÊ RANG MỘC TÂY NGUYÊN', '0999010001', '0280001001', 'active'),
                    (%s, %s, 'CÔNG TY TNHH THƯƠNG MẠI NGÂN HÀ MẪU', '0999090001', '0280009001', 'active');
                """,
                (VENDOR_COFFEE, TENANT_A, VENDOR_SYRUP, TENANT_A),
            )
            cur.execute(
                """
                INSERT INTO core.vendor_accounts (
                    vendor_account_id, vendor_id, tenant_id, kind,
                    bank_code, bank_name, account_number, merchant_id, account_name, status
                ) VALUES
                    (%s, %s, %s, 'bank_account', 'VNMB01', 'Ngân hàng Mẫu Á Châu', '990010000001', NULL, 'CONG TY TNHH CA PHE RANG MOC TAY NGUYEN', 'verified'),
                    (%s, %s, %s, 'bank_account', 'VNMB02', 'Ngân hàng Mẫu Nam Việt', '990090000002', NULL, 'CONG TY TNHH THUONG MAI NGAN HA MAU', 'escrow_only');
                """,
                (ACC_COFFEE, VENDOR_COFFEE, TENANT_A, ACC_SYRUP_ESCROW, VENDOR_SYRUP, TENANT_A),
            )
            cur.execute(
                """
                INSERT INTO core.mandates (
                    mandate_id, tenant_id, version, mode, limits,
                    auto_pay_vendor_ids, channel_rules, bulk_approvable, auto_pay_window
                ) VALUES (
                    'man_01M88C0Z95W938KHTM1EWXVCHQ', %s, 1, 'auto_pay',
                    %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
                );
                """,
                (
                    TENANT_A,
                    json.dumps({"per_invoice_vnd": 30_000_000, "per_day_vnd": 50_000_000}),
                    json.dumps([VENDOR_COFFEE]),
                    json.dumps([{"invoice_type": "software", "channel": "virtual_card"}]),
                    json.dumps([{"reason_codes": ["NON_XML_SOURCE"], "max_amount_vnd": 2_000_000}]),
                    json.dumps({"start": "07:00", "end": "22:00"}),
                ),
            )
            cur.execute(
                """
                INSERT INTO control.policies (policy_id, kind, scope, target_id, value, status)
                VALUES (
                    'pol_platform_limits_v1', 'platform_limits', NULL, NULL,
                    %s::jsonb, 'active'
                );
                """,
                (json.dumps({"auto_pay_per_invoice_vnd": 30_000_000, "auto_pay_per_day_vnd": 50_000_000}),),
            )
            conn.commit()

    rail = FakePaymentRail()
    clock = FakeClock(NOW_VN)
    rail.now_fn = clock.now
    read_store = PostgresCoreReadStore(pg_conninfo)
    ledger_store = PostgresLedgerStore(pg_conninfo)
    settings = Settings(
        port=8100,
        database_url=pg_conninfo,
        sim_url="http://sim-world.test/sim",
        sim_gate_service_key="sim-gate-key",
        demo_mode=False,
        merchant_api_service_key=SERVICE_KEYS["merchant-api"],
        core_worker_service_key=SERVICE_KEYS["core-worker"],
        internal_api_service_key=SERVICE_KEYS["internal-api"],
        console_api_service_key=SERVICE_KEYS["console-api"],
        enable_background_poller=False,
    )
    app = create_app(
        settings=settings,
        read_store=read_store,
        ledger_store=ledger_store,
        rail=rail,
        clock=clock,
    )
    client = TestClient(app)
    return pg_conninfo, client, app.state.service, rail, clock


def _seed_invoice_and_approval(
    conninfo: str,
    *,
    invoice_id: str,
    approval_id: str,
    amount_vnd: int,
    method: str = "mandate",
    status: str = "scheduled",
    severity: str = "green",
    vendor_id: str = VENDOR_COFFEE,
    seller_tax_id: str = "0999010001",
    payee_account_id: str = ACC_COFFEE,
    channel: str = "bank_transfer",
    purchase_order_id: str | None = None,
    doc_sha: str = DOC_SHA_COFFEE,
    number: str = "00001425",
) -> str:
    ih = compute_invoice_intent_hash(
        invoice_id=invoice_id,
        document_sha256=doc_sha,
        payee_account_id=payee_account_id,
        amount_vnd=amount_vnd,
        channel=channel,
    )
    with psycopg.connect(conninfo, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.invoices (
                    invoice_id, tenant_id, store_id, vendor_id, purchase_order_id,
                    seller_tax_id, symbol, number, invoice_type, total_vnd,
                    status, severity, reason_codes, document_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, '1C26TTN', %s, 'goods', %s, %s, %s, ARRAY['OK'], %s);
                """,
                (
                    invoice_id,
                    TENANT_A,
                    STORE_01,
                    vendor_id,
                    purchase_order_id,
                    seller_tax_id,
                    number,
                    amount_vnd,
                    status,
                    severity,
                    doc_sha,
                ),
            )
            cur.execute(
                """
                INSERT INTO core.jobs (job_id, tenant_id, task_type, invoice_id, status, completed_at)
                VALUES (%s, %s, 'investigate_invoice', %s, 'completed', now())
                ON CONFLICT (job_id) DO NOTHING;
                """,
                (f"job_{invoice_id[4:]}", TENANT_A, invoice_id),
            )
            cur.execute(
                """
                INSERT INTO core.approvals (
                    approval_id, tenant_id, invoice_id, job_id, status, method,
                    amount_vnd, payee_account_id, channel, intent_hash, approver_user_id, mandate_version
                ) VALUES (%s, %s, %s, %s, 'active', %s, %s, %s, %s, %s, %s, 1);
                """,
                (
                    approval_id,
                    TENANT_A,
                    invoice_id,
                    f"job_{invoice_id[4:]}",
                    method,
                    amount_vnd,
                    payee_account_id,
                    channel,
                    ih,
                    None if method == "mandate" else USER_OWNER,
                ),
            )
            conn.commit()
    return ih


@pytest.mark.db
def test_db_invariant_11_parallel_executes_same_invoice_produce_exactly_one_ledger_row(db_env):
    """Invariant #11: two parallel executes of the same invoice -> 1 rail call & 1 ledger row."""
    conninfo, _, service, rail, _ = db_env
    _seed_invoice_and_approval(
        conninfo,
        invoice_id=INV_COFFEE,
        approval_id=APV_01,
        amount_vnd=26_500_000,
    )

    outcome = service.create_intent(invoice_id=INV_COFFEE, approval_id=APV_01)
    assert outcome.created is True
    pi_id = outcome.intent.payment_intent_id

    # Synchronize two threads to hit execute_intent at the exact same instant
    barrier = threading.Barrier(2)

    def worker() -> str:
        barrier.wait()
        res = service.execute_intent(payment_intent_id=pi_id)
        return res.status.value

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(worker)
        f2 = pool.submit(worker)
        statuses = {f1.result(), f2.result()}

    # One executes -> settled; the concurrent one sees executing/settled and skips rail!
    assert statuses <= {"executing", "settled"}
    assert "settled" in statuses
    assert len(rail.transfer_calls) == 1

    with psycopg.connect(conninfo, row_factory=dict_row) as conn:
        entries = conn.execute(
            "SELECT * FROM ledger.ledger_entries WHERE invoice_id = %s;", (INV_COFFEE,)
        ).fetchall()
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "settled"

        outbox_rows = conn.execute(
            "SELECT * FROM ledger.outbox ORDER BY seq ASC;"
        ).fetchall()
        assert [r["type"] for r in outbox_rows] == ["payment.authorized", "payment.executed"]
        for r in outbox_rows:
            validate_outbox_event_against_contract(r)

        # Verify ledger.ledger_entries is truly append-only at DB level
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("DELETE FROM ledger.ledger_entries;")


@pytest.mark.db
def test_db_invariant_parallel_daily_limit_two_30m_autopays_only_one_succeeds(db_env):
    """Two 30tr auto-pays on the same day in parallel (50tr daily limit) -> ONLY ONE allowed."""
    conninfo, _, service, rail, _ = db_env
    _seed_invoice_and_approval(
        conninfo,
        invoice_id=INV_COFFEE,
        approval_id=APV_01,
        amount_vnd=30_000_000,
        number="00001425",
    )
    _seed_invoice_and_approval(
        conninfo,
        invoice_id=INV_COFFEE_2,
        approval_id=APV_02,
        amount_vnd=30_000_000,
        number="00001426",
    )

    barrier = threading.Barrier(2)

    def attempt(inv_id: str, apv_id: str) -> tuple[str, object]:
        barrier.wait()
        try:
            out = service.create_intent(invoice_id=inv_id, approval_id=apv_id)
            settled = service.execute_intent(payment_intent_id=out.intent.payment_intent_id)
            return ("ok", settled.status.value)
        except GateDeniedError as err:
            return ("denied", [r.code.value for r in err.reasons])

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(attempt, INV_COFFEE, APV_01)
        f2 = pool.submit(attempt, INV_COFFEE_2, APV_02)
        results = [f1.result(), f2.result()]

    oks = [r for r in results if r[0] == "ok"]
    denieds = [r for r in results if r[0] == "denied"]
    assert len(oks) == 1, f"Expected exactly 1 success, got {results}"
    assert len(denieds) == 1, f"Expected exactly 1 denial, got {results}"
    assert "ABOVE_DAILY_LIMIT" in denieds[0][1]
    assert len(rail.transfer_calls) == 1

    with psycopg.connect(conninfo, row_factory=dict_row) as conn:
        budget = conn.execute(
            "SELECT * FROM ledger.daily_budgets WHERE tenant_id = %s AND budget_date = %s;",
            (TENANT_A, NOW_VN.date()),
        ).fetchone()
        assert budget is not None
        assert budget["auto_pay_used_vnd"] == 30_000_000
        assert budget["auto_pay_reserved_vnd"] == 0


@pytest.mark.db
def test_db_invariant_fail_closed_when_policy_missing_and_cross_alert_at_execute(db_env):
    """Invariant #10 fail-closed + D8 cross alert published before :execute -> DENY."""
    conninfo, client, _, rail, _ = db_env
    _seed_invoice_and_approval(
        conninfo,
        invoice_id=INV_COFFEE,
        approval_id=APV_01,
        amount_vnd=26_500_000,
    )

    # Phase 1 authorizes cleanly
    r1 = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r1.status_code == 201
    pi_id = r1.json()["payment_intent_id"]

    # Delete platform_limits -> fail-closed 503 at :execute (rail never called!)
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("DELETE FROM control.policies WHERE kind = 'platform_limits';")

    r_fc = client.post(
        f"/gate/intents/{pi_id}:execute",
        json={},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_fc.status_code == 503
    assert len(rail.transfer_calls) == 0

    # Restore platform_limits, then publish a cross alert -> :execute denies with 422 GATE_DENIED
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO control.policies (policy_id, kind, scope, target_id, value, status)
            VALUES ('pol_platform_limits_v1', 'platform_limits', NULL, NULL, %s::jsonb, 'active');
            """,
            (json.dumps({"auto_pay_per_invoice_vnd": 30_000_000, "auto_pay_per_day_vnd": 50_000_000}),),
        )
        conn.execute(
            """
            INSERT INTO risk.cross_alerts (cross_alert_id, indicator_kind, value_hash, status)
            VALUES ('cxa_01', 'tax_id', %s, 'published');
            """,
            (hash_tax_id_indicator("0999010001"),),
        )

    r_ca = client.post(
        f"/gate/intents/{pi_id}:execute",
        json={},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_ca.status_code == 422
    assert any(gr["code"] == "CROSS_ALERT_UNVERIFIED" for gr in r_ca.json()["gate_reasons"])
    assert len(rail.transfer_calls) == 0


@pytest.mark.db
def test_db_escrow_unique_open_po_and_release_with_grn(db_env):
    """At most one open escrow per PO (partial unique index) + release writes ledger & outbox."""
    conninfo, client, _, rail, _ = db_env

    with psycopg.connect(conninfo, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.purchase_orders (purchase_order_id, tenant_id, vendor_id, store_id, total_vnd, status)
                VALUES (%s, %s, %s, %s, 8800000, 'open');
                """,
                (PO_01, TENANT_A, VENDOR_SYRUP, STORE_01),
            )
            cur.execute(
                """
                INSERT INTO core.goods_receipts (goods_receipt_id, tenant_id, purchase_order_id, store_id)
                VALUES (%s, %s, %s, %s);
                """,
                (GRN_01, TENANT_A, PO_01, STORE_01),
            )
            esc_ih = compute_escrow_intent_hash(
                purchase_order_id=PO_01,
                payee_account_id=ACC_SYRUP_ESCROW,
                amount_vnd=8_800_000,
            )
            cur.execute(
                """
                INSERT INTO core.approvals (
                    approval_id, tenant_id, invoice_id, purchase_order_id, source_invoice_id,
                    job_id, status, method, amount_vnd, payee_account_id, channel, intent_hash, approver_user_id
                ) VALUES (%s, %s, NULL, %s, %s, NULL, 'active', 'single', 8800000, %s, 'escrow', %s, %s);
                """,
                (APV_ESC_CREATE, TENANT_A, PO_01, INV_SYRUP, ACC_SYRUP_ESCROW, esc_ih, USER_OWNER),
            )
            conn.commit()

    # Create first escrow -> 201 held
    r1 = client.post(
        "/gate/escrows",
        json={"approval_id": APV_ESC_CREATE, "expires_on": "2026-12-10"},
        headers={"X-Service-Key": SERVICE_KEYS["merchant-api"]},
    )
    assert r1.status_code == 201 and r1.json()["status"] == "held"
    esc_id = r1.json()["escrow_id"]

    # Second escrow on same PO while first is held -> 422 GATE_DENIED (ALREADY_PAID)
    r_dup = client.post(
        "/gate/escrows",
        json={"approval_id": APV_ESC_CREATE, "expires_on": "2026-12-10"},
        headers={"X-Service-Key": SERVICE_KEYS["merchant-api"]},
    )
    assert r_dup.status_code == 422

    # Seed release invoice + approval (channel=escrow)
    _seed_invoice_and_approval(
        conninfo,
        invoice_id=INV_SYRUP,
        approval_id=APV_ESC_RELEASE,
        amount_vnd=8_800_000,
        method="single",
        status="escrow_held",
        severity="yellow",
        vendor_id=VENDOR_SYRUP,
        seller_tax_id="0999090001",
        payee_account_id=ACC_SYRUP_ESCROW,
        channel="escrow",
        purchase_order_id=PO_01,
        doc_sha=DOC_SHA_SYRUP,
    )

    r_rel = client.post(
        f"/gate/escrows/{esc_id}:release",
        json={"approval_id": APV_ESC_RELEASE, "goods_receipt_id": GRN_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_rel.status_code == 200
    assert r_rel.json()["status"] == "released"

    with psycopg.connect(conninfo, row_factory=dict_row) as conn:
        entries = conn.execute("SELECT * FROM ledger.ledger_entries ORDER BY created_at;").fetchall()
        assert [e["entry_type"] for e in entries] == ["escrow_held", "escrow_released"]
        outbox = conn.execute("SELECT * FROM ledger.outbox ORDER BY seq;").fetchall()
        assert [o["type"] for o in outbox] == ["escrow.held", "escrow.released"]
        for o in outbox:
            validate_outbox_event_against_contract(o)

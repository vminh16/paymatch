"""Postgres 16 DB tests for Payment Gate safety invariants (testcontainers, @pytest.mark.db).

Mirrors `core`'s REAL migrations `001..004` (`core_schema_fixture.py`) verbatim, runs
Gate's real `ledger` migrations AS the least-privilege `gate` role (NOT superuser),
and tests all money-safety blockers (B1–B6 + Important) against real Postgres 16.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlparse, urlunparse

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from testcontainers.postgres import PostgresContainer

from core_schema_fixture import CORE_MIGRATIONS
from gate.adapters.fakes import FakeClock, FakePaymentRail
from gate.adapters.http import create_app
from gate.adapters.postgres import PostgresCoreReadStore, PostgresLedgerStore, apply_migrations
from gate.adapters.sim_world import SimWorldPaymentRail
from gate.config import Settings
from gate.domain.hashing import (
    compute_escrow_intent_hash,
    compute_invoice_intent_hash,
    hash_tax_id_indicator,
)
from gate.domain.models import GateDeniedError
from gate.domain.rules import VN_TZ

from gate_fixtures import (
    ACC_COFFEE,
    ACC_SYRUP_ESCROW,
    APV_01,
    APV_02,
    APV_ESC_CREATE,
    APV_ESC_CREATE_2,
    APV_ESC_RELEASE,
    DOC_SHA_COFFEE,
    DOC_SHA_SYRUP,
    GRN_01,
    INV_COFFEE,
    INV_COFFEE_2,
    INV_SYRUP,
    NOW_VN,
    PO_01,
    SERVICE_KEYS,
    STORE_01,
    TENANT_A,
    TENANT_B,
    USER_OWNER,
    VENDOR_COFFEE,
    VENDOR_SYRUP,
    WALLET_A,
    validate_outbox_event_against_contract,
)

USER_ACCOUNTANT = "usr_01M88ACCNT0000000000000001"
USER_OWNER_B = "usr_01M880WNRB0000000000000001"
STORE_B = "str_01M88STRB00000000000000001"
WALLET_B = "wal_01M88WALB00000000000000001"
VENDOR_B = "vnd_01M88VNDB00000000000000001"
ACC_B = "vac_01M88ACCB00000000000000001"
INV_B = "inv_01M881NVB00000000000000001"
PO_B = "po_01M88P0B000000000000000001"
GRN_B = "grn_01M88GRNB00000000000000001"
APV_B = "apv_01M88APVB00000000000000001"
APV_03 = "apv_01M88000030000000000000003"


def _as_role_url(admin_url: str, username: str, password: str) -> str:
    parsed = urlparse(admin_url)
    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    return urlunparse(
        (parsed.scheme, f"{username}:{password}@{host}{port}", parsed.path, "", "", "")
    )


@pytest.fixture(scope="module")
def pg_urls():
    with PostgresContainer("postgres:16-alpine") as pg:
        admin_url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        with psycopg.connect(admin_url, autocommit=True) as conn:
            for _, sql in CORE_MIGRATIONS:
                conn.execute(sql)
            # Enable least-privilege login for `gate`, own `ledger`, and grant SELECT on core.users (B5).
            conn.execute("ALTER ROLE gate WITH LOGIN PASSWORD 'gate';")
            conn.execute("CREATE SCHEMA IF NOT EXISTS ledger AUTHORIZATION gate;")
            conn.execute("GRANT SELECT ON core.users TO gate;")
            conn.execute("DROP POLICY IF EXISTS gate_readonly ON core.users;")
            conn.execute("CREATE POLICY gate_readonly ON core.users FOR SELECT TO gate USING (true);")

            role_info = conn.execute(
                "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = 'gate';"
            ).fetchone()
            assert role_info == (False, False, False, False)

        gate_url = _as_role_url(admin_url, "gate", "gate")
        applied = apply_migrations(gate_url)
        assert "001_init_ledger.sql" in applied
        assert apply_migrations(gate_url) == []
        yield admin_url, gate_url


def _make_settings(gate_url: str, *, auto_migrate: bool = False) -> Settings:
    return Settings(
        port=8100,
        database_url=gate_url,
        sim_url="http://sim-world.test/sim",
        sim_gate_service_key="sim-gate-key",
        demo_mode=False,
        merchant_api_service_key=SERVICE_KEYS["merchant-api"],
        core_worker_service_key=SERVICE_KEYS["core-worker"],
        internal_api_service_key=SERVICE_KEYS["internal-api"],
        console_api_service_key=SERVICE_KEYS["console-api"],
        enable_background_poller=False,
        auto_migrate=auto_migrate,
    )


@pytest.fixture()
def db_env(pg_urls: tuple[str, str]):
    """Reset all tables as admin and seed baseline data; Gate connects strictly as least-privilege `gate`."""
    admin_url, gate_url = pg_urls
    with psycopg.connect(admin_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE
                    ledger.outbox,
                    ledger.rail_transactions,
                    ledger.daily_budgets,
                    ledger.ledger_entries,
                    ledger.invoice_claims,
                    ledger.payment_tokens,
                    ledger.payment_intents,
                    ledger.escrows,
                    core.goods_receipts,
                    core.purchase_orders,
                    core.approvals,
                    core.jobs,
                    core.invoices,
                    core.invoice_documents,
                    core.auto_pay_suspensions,
                    core.mandates,
                    core.vendor_accounts,
                    core.vendors,
                    core.users,
                    core.stores,
                    core.tenants,
                    control.policies,
                    risk.indicators,
                    risk.hard_blocks,
                    risk.cross_alerts
                RESTART IDENTITY CASCADE;
                """
            )
            cur.execute(
                """
                INSERT INTO core.tenants (tenant_id, wallet_id, tax_id, name, mailbox, created_at)
                VALUES
                    (%s, %s, '0312000001', 'Chuỗi Lá Xanh', 'hoadon@laxanh.example', now()),
                    (%s, %s, '0312000002', 'Chuỗi Khác', 'hoadon@other.example', now());
                """,
                (TENANT_A, WALLET_A, TENANT_B, WALLET_B),
            )
            cur.execute(
                """
                INSERT INTO core.stores (store_id, tenant_id, name, kind)
                VALUES
                    (%s, %s, 'Chi nhánh Q1', 'outlet'),
                    (%s, %s, 'Chi nhánh B', 'outlet');
                """,
                (STORE_01, TENANT_A, STORE_B, TENANT_B),
            )
            cur.execute(
                """
                INSERT INTO core.users (user_id, tenant_id, name, email, role)
                VALUES
                    (%s, %s, 'Chị Lan (Chủ)', 'lan@laxanh.example', 'owner'),
                    (%s, %s, 'Anh Minh (Kế toán)', 'minh@laxanh.example', 'accountant'),
                    (%s, %s, 'Chủ B', 'owner@other.example', 'owner');
                """,
                (USER_OWNER, TENANT_A, USER_ACCOUNTANT, TENANT_A, USER_OWNER_B, TENANT_B),
            )
            cur.execute(
                """
                INSERT INTO core.vendors (vendor_id, tenant_id, name, tax_id, phone_on_file, status, created_at)
                VALUES
                    (%s, %s, 'CÔNG TY TNHH CÀ PHÊ RANG MỘC TÂY NGUYÊN', '0999010001', '0280001001', 'active', now()),
                    (%s, %s, 'CÔNG TY TNHH THƯƠNG MẠI NGÂN HÀ MẪU', '0999090001', '0280009001', 'active', now()),
                    (%s, %s, 'NCC TENANT B', '0999888001', '0280008001', 'active', now());
                """,
                (VENDOR_COFFEE, TENANT_A, VENDOR_SYRUP, TENANT_A, VENDOR_B, TENANT_B),
            )
            cur.execute(
                """
                INSERT INTO core.vendor_accounts (
                    vendor_account_id, vendor_id, tenant_id, kind,
                    bank_code, bank_name, account_number, merchant_id, account_name, status
                ) VALUES
                    (%s, %s, %s, 'bank_account', 'VNMB01', 'Ngân hàng Mẫu Á Châu', '990010000001', NULL, 'CONG TY TNHH CA PHE RANG MOC TAY NGUYEN', 'verified'),
                    (%s, %s, %s, 'bank_account', 'VNMB02', 'Ngân hàng Mẫu Nam Việt', '990090000002', NULL, 'CONG TY TNHH THUONG MAI NGAN HA MAU', 'escrow_only'),
                    (%s, %s, %s, 'bank_account', 'VNMB02', 'Ngân hàng Mẫu B', '990088000002', NULL, 'NCC TENANT B', 'escrow_only');
                """,
                (
                    ACC_COFFEE, VENDOR_COFFEE, TENANT_A,
                    ACC_SYRUP_ESCROW, VENDOR_SYRUP, TENANT_A,
                    ACC_B, VENDOR_B, TENANT_B,
                ),
            )
            cur.execute(
                """
                INSERT INTO core.mandates (
                    mandate_id, tenant_id, version, mode, limits,
                    auto_pay_vendor_ids, channel_rules, bulk_approvable, auto_pay_window, signed, created_at
                ) VALUES (
                    'man_01M88C0Z95W938KHTM1EWXVCHQ', %s, 1, 'auto_pay',
                    %s::jsonb, ARRAY[%s]::text[], %s::jsonb, %s::jsonb, %s::jsonb, '{}'::jsonb, now()
                );
                """,
                (
                    TENANT_A,
                    json.dumps({"per_invoice_vnd": 30_000_000, "per_day_vnd": 50_000_000}),
                    VENDOR_COFFEE,
                    json.dumps([{"invoice_type": "software", "channel": "virtual_card"}]),
                    json.dumps([{"reason_codes": ["NON_XML_SOURCE"], "max_amount_vnd": 2_000_000}]),
                    json.dumps({"start": "00:00", "end": "23:59"}),
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
    read_store = PostgresCoreReadStore(gate_url)
    ledger_store = PostgresLedgerStore(gate_url)
    app = create_app(
        settings=_make_settings(gate_url),
        read_store=read_store,
        ledger_store=ledger_store,
        rail=rail,
        clock=clock,
    )
    client = TestClient(app)
    return admin_url, gate_url, client, app.state.service, app.state.poller, rail, clock


def _seed_invoice_and_approval(
    admin_url: str,
    *,
    invoice_id: str,
    approval_id: str,
    amount_vnd: int,
    tenant_id: str = TENANT_A,
    store_id: str = STORE_01,
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
    approver_user_id: str | None = "AUTO",
) -> str:
    ih = compute_invoice_intent_hash(
        invoice_id=invoice_id,
        document_sha256=doc_sha,
        payee_account_id=payee_account_id,
        amount_vnd=amount_vnd,
        channel=channel,
    )
    doc_id = f"doc_{invoice_id[4:]}"
    job_id = f"job_{invoice_id[4:]}"
    resolved_approver = (
        (None if method == "mandate" else USER_OWNER)
        if approver_user_id == "AUTO"
        else approver_user_id
    )
    with psycopg.connect(admin_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.invoice_documents (
                    document_id, tenant_id, format, sha256, raw_bytes, received_at
                ) VALUES (%s, %s, 'xml', %s, %s, now())
                ON CONFLICT (document_id) DO UPDATE SET sha256 = EXCLUDED.sha256;
                """,
                (doc_id, tenant_id, doc_sha, b"<xml/>"),
            )
            # Intentionally store an empty string in core.invoices.document_sha256 to prove Gate reads
            # authoritative sha256 from core.invoice_documents joined via document_id!
            cur.execute(
                """
                INSERT INTO core.invoices (
                    invoice_id, tenant_id, document_id, document_sha256, store_id, vendor_id,
                    purchase_order_id, seller_tax_id, symbol, number, invoice_type, source,
                    total_vnd, status, severity, reason_codes
                ) VALUES (
                    %s, %s, %s, '', %s, %s, %s, %s, '1C26TTN', %s, 'goods', 'email',
                    %s, %s, %s, ARRAY['OK']
                )
                ON CONFLICT (invoice_id) DO NOTHING;
                """,
                (
                    invoice_id, tenant_id, doc_id, store_id, vendor_id, purchase_order_id,
                    seller_tax_id, number, amount_vnd, status, severity,
                ),
            )
            cur.execute(
                """
                INSERT INTO core.jobs (job_id, tenant_id, task_type, subject, invoice_id, status, completed_at)
                VALUES (%s, %s, 'investigate_invoice', '{}'::jsonb, %s, 'completed', now())
                ON CONFLICT (job_id) DO NOTHING;
                """,
                (job_id, tenant_id, invoice_id),
            )
            cur.execute(
                """
                INSERT INTO core.approvals (
                    approval_id, tenant_id, invoice_id, job_id, status, method,
                    amount_vnd, payee_account_id, channel, intent_hash, approver_user_id, mandate_version
                ) VALUES (%s, %s, %s, %s, 'active', %s, %s, %s, %s, %s, %s, 1);
                """,
                (
                    approval_id, tenant_id, invoice_id, job_id, method,
                    amount_vnd, payee_account_id, channel, ih, resolved_approver,
                ),
            )
            conn.commit()
    return ih


def _seed_po_and_escrow_approvals(admin_url: str, *, po_id: str = PO_01, tenant_id: str = TENANT_A, vendor_id: str = VENDOR_SYRUP, store_id: str = STORE_01, grn_id: str = GRN_01, acc_id: str = ACC_SYRUP_ESCROW, approval_ids: tuple[str, ...] = (APV_ESC_CREATE, APV_ESC_CREATE_2), owner_id: str = USER_OWNER) -> None:
    esc_ih = compute_escrow_intent_hash(
        purchase_order_id=po_id, payee_account_id=acc_id, amount_vnd=8_800_000
    )
    with psycopg.connect(admin_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.purchase_orders (
                    purchase_order_id, tenant_id, vendor_id, store_id, lines, total_vnd, status, created_by, created_at
                ) VALUES (%s, %s, %s, %s, '[]'::jsonb, 8800000, 'open', %s, now())
                ON CONFLICT (purchase_order_id) DO NOTHING;
                """,
                (po_id, tenant_id, vendor_id, store_id, owner_id),
            )
            cur.execute(
                """
                INSERT INTO core.goods_receipts (
                    goods_receipt_id, tenant_id, purchase_order_id, store_id, lines, confirmed_by, confirmed_at
                ) VALUES (%s, %s, %s, %s, '[]'::jsonb, %s, now())
                ON CONFLICT (goods_receipt_id) DO NOTHING;
                """,
                (grn_id, tenant_id, po_id, store_id, owner_id),
            )
            for apv_id in approval_ids:
                cur.execute(
                    """
                    INSERT INTO core.approvals (
                        approval_id, tenant_id, invoice_id, purchase_order_id, source_invoice_id,
                        job_id, status, method, amount_vnd, payee_account_id, channel, intent_hash, approver_user_id
                    ) VALUES (%s, %s, NULL, %s, NULL, NULL, 'active', 'single', 8800000, %s, 'escrow', %s, %s);
                    """,
                    (apv_id, tenant_id, po_id, acc_id, esc_ih, owner_id),
                )
            conn.commit()


@pytest.mark.db
def test_db_least_privilege_gate_role_boot_auto_migrate_and_readyz(db_env):
    """Gate connects as least-privilege `gate` role (cannot mutate core.*), auto-migrates on boot, readyz verifies relations."""
    admin_url, gate_url, client, *_ = db_env

    # 1. `gate` role CANNOT write to `core.invoices` (InsufficientPrivilege)
    with psycopg.connect(gate_url, autocommit=True) as gconn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            gconn.execute("DELETE FROM core.invoices;")

    # 2. `/gate/readyz` is 200 when all required core/control/risk/ledger relations & platform_limits exist
    assert client.get("/gate/readyz").status_code == 200

    # 3. Boot auto-migration via FastAPI lifespan with `auto_migrate=True` succeeds as `gate`
    boot_app = create_app(settings=_make_settings(gate_url, auto_migrate=True), rail=FakePaymentRail(), clock=FakeClock(NOW_VN))
    with TestClient(boot_app) as boot_client:
        assert boot_client.get("/gate/readyz").status_code == 200


@pytest.mark.db
def test_db_invariant_11_parallel_executes_same_invoice_produce_exactly_one_ledger_row(db_env):
    """Invariant #11: two parallel executes of the same invoice -> 1 rail call & 1 append-only ledger row."""
    admin_url, gate_url, _, service, _, rail, _ = db_env
    _seed_invoice_and_approval(admin_url, invoice_id=INV_COFFEE, approval_id=APV_01, amount_vnd=26_500_000)

    outcome = service.create_intent(invoice_id=INV_COFFEE, approval_id=APV_01)
    assert outcome.created is True
    pi_id = outcome.intent.payment_intent_id

    barrier = threading.Barrier(2)

    def worker() -> str:
        barrier.wait()
        return service.execute_intent(payment_intent_id=pi_id).status.value

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(worker)
        f2 = pool.submit(worker)
        statuses = {f1.result(), f2.result()}

    assert statuses <= {"executing", "settled"} and "settled" in statuses
    assert len(rail.transfer_calls) == 1

    with psycopg.connect(gate_url, row_factory=dict_row) as conn:
        entries = conn.execute("SELECT * FROM ledger.ledger_entries WHERE invoice_id = %s;", (INV_COFFEE,)).fetchall()
        assert len(entries) == 1 and entries[0]["entry_type"] == "settled"
        outbox_rows = conn.execute("SELECT * FROM ledger.outbox ORDER BY seq ASC;").fetchall()
        assert [r["type"] for r in outbox_rows] == ["payment.authorized", "payment.executed"]
        for r in outbox_rows:
            validate_outbox_event_against_contract(r)
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("DELETE FROM ledger.ledger_entries;")


@pytest.mark.db
def test_db_invariant_parallel_daily_limit_two_30m_autopays_only_one_succeeds(db_env):
    """Two 30tr auto-pays on the same day in parallel (50tr daily limit) -> ONLY ONE allowed."""
    admin_url, gate_url, _, service, _, rail, _ = db_env
    _seed_invoice_and_approval(admin_url, invoice_id=INV_COFFEE, approval_id=APV_01, amount_vnd=30_000_000, number="00001425")
    _seed_invoice_and_approval(admin_url, invoice_id=INV_COFFEE_2, approval_id=APV_02, amount_vnd=30_000_000, number="00001426", doc_sha="2" * 64)

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
    assert len(oks) == 1 and len(denieds) == 1
    assert "ABOVE_DAILY_LIMIT" in denieds[0][1]
    assert len(rail.transfer_calls) == 1

    with psycopg.connect(gate_url, row_factory=dict_row) as conn:
        budget = conn.execute(
            "SELECT * FROM ledger.daily_budgets WHERE tenant_id = %s AND budget_date = %s;",
            (TENANT_A, NOW_VN.date()),
        ).fetchone()
        assert budget is not None
        assert budget["auto_pay_used_vnd"] == 30_000_000 and budget["auto_pay_reserved_vnd"] == 0


@pytest.mark.db
def test_db_b1_cross_channel_timeout_blocks_double_pay_both_directions(db_env):
    """B1: Lost-reply transfer + escrow release (and reverse) CANNOT double-pay the same invoice."""
    admin_url, _, client, _, poller, rail, _ = db_env
    _seed_po_and_escrow_approvals(admin_url)

    # Hold an escrow on PO_01
    r_esc = client.post(
        "/gate/escrows",
        json={"approval_id": APV_ESC_CREATE, "expires_on": "2026-12-10"},
        headers={"X-Service-Key": SERVICE_KEYS["merchant-api"]},
    )
    assert r_esc.status_code == 201 and r_esc.json()["status"] == "held"
    esc_id = r_esc.json()["escrow_id"]

    # Direction 1: Bank transfer times out (stays `executing`, holds `ledger.invoice_claims`) ->
    # trying to release the escrow against the SAME invoice MUST be DENIED with ALREADY_PAID!
    _seed_invoice_and_approval(
        admin_url,
        invoice_id=INV_COFFEE,
        approval_id=APV_01,
        amount_vnd=8_800_000,
        method="single",
        status="pending_approval",
        severity="yellow",
        vendor_id=VENDOR_COFFEE,
        seller_tax_id="0999010001",
        payee_account_id=ACC_COFFEE,
        channel="bank_transfer",
        purchase_order_id=None,
    )
    pi_id = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    ).json()["payment_intent_id"]

    rail.timeout_next_transfer = True
    r_exec = client.post(
        f"/gate/intents/{pi_id}:execute",
        json={},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_exec.status_code == 200 and r_exec.json()["status"] == "executing"

    # Now try to release escrow for INV_COFFEE (even with a matching escrow release approval)
    rel_ih = compute_invoice_intent_hash(
        invoice_id=INV_COFFEE,
        document_sha256=DOC_SHA_COFFEE,
        payee_account_id=ACC_SYRUP_ESCROW,
        amount_vnd=8_800_000,
        channel="escrow",
    )
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("UPDATE core.invoices SET purchase_order_id = %s, vendor_id = %s, seller_tax_id = '0999090001' WHERE invoice_id = %s;", (PO_01, VENDOR_SYRUP, INV_COFFEE))
        conn.execute("UPDATE core.approvals SET status = 'superseded' WHERE approval_id = %s;", (APV_01,))
        conn.execute(
            """
            INSERT INTO core.approvals (
                approval_id, tenant_id, invoice_id, job_id, status, method,
                amount_vnd, payee_account_id, channel, intent_hash, approver_user_id
            ) VALUES (%s, %s, %s, %s, 'active', 'single', 8800000, %s, 'escrow', %s, %s);
            """,
            (APV_ESC_RELEASE, TENANT_A, INV_COFFEE, f"job_{INV_COFFEE[4:]}", ACC_SYRUP_ESCROW, rel_ih, USER_OWNER),
        )

    release_calls_before = sum(1 for c in rail.escrow_calls if c["op"] == "release")
    r_rel = client.post(
        f"/gate/escrows/{esc_id}:release",
        json={"approval_id": APV_ESC_RELEASE, "goods_receipt_id": GRN_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_rel.status_code == 422
    assert any(gr["code"] == "ALREADY_PAID" for gr in r_rel.json()["gate_reasons"])
    assert sum(1 for c in rail.escrow_calls if c["op"] == "release") == release_calls_before

    # Direction 2: Escrow release times out (persists pending_action='release' & claims INV_SYRUP) ->
    # trying to create a payment intent for INV_SYRUP MUST be DENIED with ALREADY_PAID!
    _seed_invoice_and_approval(
        admin_url,
        invoice_id=INV_SYRUP,
        approval_id=APV_02,
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
    rail.timeout_next_release = True
    r_rel_timeout = client.post(
        f"/gate/escrows/{esc_id}:release",
        json={"approval_id": APV_02, "goods_receipt_id": GRN_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_rel_timeout.status_code == 504

    # Attempt to create an intent on INV_SYRUP while escrow release is in flight -> DENIED (ALREADY_PAID)!
    r_pi_blocked = client.post(
        "/gate/intents",
        json={"invoice_id": INV_SYRUP, "approval_id": APV_02},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_pi_blocked.status_code == 422
    assert any(gr["code"] == "ALREADY_PAID" for gr in r_pi_blocked.json()["gate_reasons"])

    # Poller reconciles the timed-out escrow release against stored binding -> released!
    tick = poller.run_once()
    assert tick.released_escrows == 1
    assert client.get(f"/gate/escrows/{esc_id}", headers={"X-Service-Key": SERVICE_KEYS["core-worker"]}).json()["status"] == "released"


@pytest.mark.db
def test_db_b4_midnight_budget_rollover_vn_local_date(db_env):
    """B4: Daily budget is charged on Asia/Ho_Chi_Minh execution date, re-reserved or denied at midnight."""
    admin_url, gate_url, client, _, _, rail, clock = db_env

    # Start at 23:55 VN on 2026-11-26
    clock.set(datetime(2026, 11, 26, 23, 55, 0, tzinfo=VN_TZ))
    _seed_invoice_and_approval(admin_url, invoice_id=INV_COFFEE, approval_id=APV_01, amount_vnd=30_000_000, number="00001425")
    _seed_invoice_and_approval(admin_url, invoice_id=INV_COFFEE_2, approval_id=APV_02, amount_vnd=20_000_000, number="00001426", doc_sha="2" * 64)

    # Authorize BOTH before midnight (reserves 30M + 20M = 50M on 2026-11-26)
    pi_30m = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    ).json()["payment_intent_id"]
    pi_20m = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE_2, "approval_id": APV_02},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    ).json()["payment_intent_id"]

    # Pre-seed 30M already used on 2026-11-27 (50M daily limit -> only 20M room left on 2026-11-27!)
    with psycopg.connect(gate_url, autocommit=True) as gconn:
        gconn.execute(
            """
            INSERT INTO ledger.daily_budgets (tenant_id, budget_date, auto_pay_used_vnd, auto_pay_reserved_vnd, total_paid_vnd, updated_at)
            VALUES (%s, '2026-11-27', 30000000, 0, 30000000, now());
            """,
            (TENANT_A,),
        )

    # Advance clock across VN midnight to 2026-11-27T00:05:00+07:00 (still within 15m TTL!)
    clock.advance(minutes=10)

    # 1. Executing 30M intent on 2026-11-27 (30M + 30M = 60M > 50M) -> DENIED with ABOVE_DAILY_LIMIT!
    r_30m = client.post(
        f"/gate/intents/{pi_30m}:execute",
        json={},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_30m.status_code == 422
    assert any(gr["code"] == "ABOVE_DAILY_LIMIT" for gr in r_30m.json()["gate_reasons"])
    assert len(rail.transfer_calls) == 0

    # 2. Executing 20M intent on 2026-11-27 (30M + 20M = 50M <= 50M) -> SUCCEEDS and charges 2026-11-27!
    r_20m = client.post(
        f"/gate/intents/{pi_20m}:execute",
        json={},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_20m.status_code == 200 and r_20m.json()["status"] == "settled"
    assert len(rail.transfer_calls) == 1

    with psycopg.connect(gate_url, row_factory=dict_row) as gconn:
        b26 = gconn.execute("SELECT * FROM ledger.daily_budgets WHERE tenant_id = %s AND budget_date = '2026-11-26';", (TENANT_A,)).fetchone()
        b27 = gconn.execute("SELECT * FROM ledger.daily_budgets WHERE tenant_id = %s AND budget_date = '2026-11-27';", (TENANT_A,)).fetchone()
        assert b26 is not None and b26["auto_pay_reserved_vnd"] == 0 and b26["auto_pay_used_vnd"] == 0
        assert b27 is not None and b27["auto_pay_reserved_vnd"] == 0 and b27["auto_pay_used_vnd"] == 50_000_000


@pytest.mark.db
def test_db_b5_owner_approval_proof_tainted_approval_and_execution_tuple_mismatch(db_env):
    """B5: Owner proof on manual approvals, tainted approval non-reusability, and full tuple check at :execute."""
    admin_url, gate_url, client, _, _, rail, _ = db_env

    # 1. Manual approval with accountant (non-owner) -> DENIED!
    _seed_invoice_and_approval(
        admin_url,
        invoice_id=INV_COFFEE,
        approval_id=APV_01,
        amount_vnd=26_500_000,
        method="single",
        status="pending_approval",
        severity="yellow",
        approver_user_id=USER_ACCOUNTANT,
    )
    r_acc = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_acc.status_code == 422
    assert any(gr["code"] == "APPROVAL_STALE" for gr in r_acc.json()["gate_reasons"])

    # 2. Manual approval with NULL approver_user_id -> DENIED!
    _seed_invoice_and_approval(
        admin_url,
        invoice_id=INV_COFFEE_2,
        approval_id=APV_02,
        amount_vnd=20_000_000,
        method="single",
        status="pending_approval",
        severity="yellow",
        number="00001426",
        doc_sha="2" * 64,
        approver_user_id=None,
    )
    r_null = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE_2, "approval_id": APV_02},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_null.status_code == 422

    # 3. Valid owner approval -> fails at rail -> CANNOT reuse the same approval_id!
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("UPDATE core.approvals SET status = 'superseded' WHERE approval_id = %s;", (APV_01,))
    _seed_invoice_and_approval(
        admin_url,
        invoice_id=INV_COFFEE,
        approval_id=APV_03,
        amount_vnd=26_500_000,
        method="single",
        status="pending_approval",
        severity="yellow",
        approver_user_id=USER_OWNER,
    )
    pi_fail = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_03},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    ).json()["payment_intent_id"]
    rail.fail_next_transfer_code = "INSUFFICIENT_FUNDS"
    assert client.post(f"/gate/intents/{pi_fail}:execute", json={}, headers={"X-Service-Key": SERVICE_KEYS["core-worker"]}).json()["status"] == "failed"

    r_reuse = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_03},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_reuse.status_code == 422
    assert any(gr["code"] == "APPROVAL_STALE" for gr in r_reuse.json()["gate_reasons"])

    # 4. Mutating core.invoice_documents.sha256 between authorize and :execute -> full tuple check DENIES!
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("UPDATE core.approvals SET status = 'superseded' WHERE approval_id = %s;", (APV_02,))
        conn.execute("UPDATE core.approvals SET approver_user_id = %s, status = 'active' WHERE approval_id = %s;", (USER_OWNER, APV_02))
    # Clear the prior denied intent for APV_02? No, create a clean fresh approval on INV_COFFEE_2!
    apv_clean = "apv_01M88000040000000000000004"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("UPDATE core.approvals SET status = 'superseded' WHERE approval_id = %s;", (APV_02,))
    _seed_invoice_and_approval(
        admin_url,
        invoice_id=INV_COFFEE_2,
        approval_id=apv_clean,
        amount_vnd=20_000_000,
        method="single",
        status="pending_approval",
        severity="yellow",
        number="00001426",
        doc_sha="2" * 64,
        approver_user_id=USER_OWNER,
    )
    pi_tamper = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE_2, "approval_id": apv_clean},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    ).json()["payment_intent_id"]

    # Tamper core.invoice_documents.sha256 before :execute (simulating document swap!)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            "UPDATE core.invoice_documents SET sha256 = %s WHERE document_id = %s;",
            ("f" * 64, f"doc_{INV_COFFEE_2[4:]}"),
        )
    calls_before = len(rail.transfer_calls)
    r_tamper = client.post(
        f"/gate/intents/{pi_tamper}:execute",
        json={},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_tamper.status_code == 422
    assert any(gr["code"] == "APPROVAL_STALE" for gr in r_tamper.json()["gate_reasons"])
    assert len(rail.transfer_calls) == calls_before


@pytest.mark.db
def test_db_b3_real_rail_403_409_5xx_keep_executing_claim_and_budget_and_alert_stuck(db_env):
    """B3: Real SimWorldPaymentRail HTTP 403/409/500 keep executing, claim & budget intact, alert after 24h."""
    admin_url, gate_url, _, _, _, _, clock = db_env
    _seed_invoice_and_approval(admin_url, invoice_id=INV_COFFEE, approval_id=APV_01, amount_vnd=26_500_000)

    # Sequence of real HTTP error replies from sim-world: POST -> 403, GET #1 -> 409, GET #2 -> 500
    replies = iter(
        [
            httpx.Response(403, json={"code": "FORBIDDEN", "detail": "service key mismatch"}),
            httpx.Response(409, json={"code": "IDEMPOTENCY_KEY_REUSED", "detail": "conflict"}),
            httpx.Response(500, json={"code": "INTERNAL_ERROR", "detail": "rail 500"}),
        ]
    )
    real_rail = SimWorldPaymentRail(
        sim_url="http://sim-world.test/sim",
        service_key="sim-gate-key",
        client=httpx.Client(transport=httpx.MockTransport(lambda req: next(replies))),
    )
    app = create_app(
        settings=_make_settings(gate_url),
        read_store=PostgresCoreReadStore(gate_url),
        ledger_store=PostgresLedgerStore(gate_url),
        rail=real_rail,
        clock=clock,
    )
    client = TestClient(app)
    poller = app.state.poller

    pi_id = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    ).json()["payment_intent_id"]

    # Execute hits 403 -> MUST stay `executing`, NOT `failed`!
    r_exec = client.post(
        f"/gate/intents/{pi_id}:execute",
        json={},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_exec.status_code == 200 and r_exec.json()["status"] == "executing"

    # Poller tick #1 (409) at +1h -> still executing
    clock.advance(hours=1)
    t1 = poller.run_once()
    assert t1.failed_intents == 0 and t1.stuck_notified == 0

    # Poller tick #2 (500) at +25h -> still executing, emits payment.stuck ONCE!
    clock.advance(hours=24)
    t2 = poller.run_once()
    assert t2.failed_intents == 0 and t2.stuck_notified == 1

    with psycopg.connect(gate_url, row_factory=dict_row) as gconn:
        intent = gconn.execute("SELECT status FROM ledger.payment_intents WHERE payment_intent_id = %s;", (pi_id,)).fetchone()
        claim = gconn.execute("SELECT status FROM ledger.invoice_claims WHERE invoice_id = %s;", (INV_COFFEE,)).fetchone()
        budget = gconn.execute("SELECT auto_pay_reserved_vnd, auto_pay_used_vnd FROM ledger.daily_budgets WHERE tenant_id = %s AND budget_date = '2026-11-26';", (TENANT_A,)).fetchone()
        entries = gconn.execute("SELECT * FROM ledger.ledger_entries WHERE payment_intent_id = %s;", (pi_id,)).fetchall()
        stuck_evts = gconn.execute("SELECT * FROM ledger.outbox WHERE type = 'payment.stuck';").fetchall()
        assert intent is not None and intent["status"] == "executing"
        assert claim is not None and claim["status"] == "claimed"
        assert budget is not None and budget["auto_pay_reserved_vnd"] == 26_500_000 and budget["auto_pay_used_vnd"] == 0
        assert entries == []
        assert len(stuck_evts) == 1
        validate_outbox_event_against_contract(stuck_evts[0])


@pytest.mark.db
def test_db_b6_unreadable_risk_table_fails_closed(db_env):
    """B6 & Invariant #10: Revoking SELECT on risk.indicators forces fail-closed 503 on evaluate & readyz."""
    admin_url, _, client, _, _, rail, _ = db_env
    _seed_invoice_and_approval(admin_url, invoice_id=INV_COFFEE, approval_id=APV_01, amount_vnd=26_500_000)

    try:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute("REVOKE SELECT ON risk.indicators FROM gate;")

        assert client.get("/gate/readyz").status_code == 503
        r_eval = client.post(
            "/gate/evaluate",
            json={"invoice_id": INV_COFFEE},
            headers={"X-Service-Key": SERVICE_KEYS["merchant-api"]},
        )
        assert r_eval.status_code == 503 and r_eval.json()["code"] == "UPSTREAM_UNAVAILABLE"

        r_int = client.post(
            "/gate/intents",
            json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
            headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
        )
        assert r_int.status_code == 503
        assert len(rail.transfer_calls) == 0
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute("GRANT SELECT ON risk.indicators TO gate;")

    # Verify cross_alert matched via indicator_ids[] (core's real schema!) denies at :execute
    pi_id = client.post(
        "/gate/intents",
        json={"invoice_id": INV_COFFEE, "approval_id": APV_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    ).json()["payment_intent_id"]
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO risk.indicators (indicator_id, kind, value_hash) VALUES ('ind_01', 'tax_id', %s);",
            (hash_tax_id_indicator("0999010001"),),
        )
        conn.execute(
            """
            INSERT INTO risk.cross_alerts (cross_alert_id, indicator_ids, published_by, status)
            VALUES ('cxa_01', ARRAY['ind_01'], 'stf_01', 'published');
            """
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
def test_db_escrow_atomic_idempotency_tenant_mismatch_and_review_only_release(db_env):
    """Atomic B2 escrow idempotency under concurrency + release tenant mismatch (403) + review_only mandate DENY."""
    admin_url, gate_url, client, _, _, rail, _ = db_env
    _seed_po_and_escrow_approvals(admin_url)
    _seed_po_and_escrow_approvals(
        admin_url,
        po_id=PO_B,
        tenant_id=TENANT_B,
        vendor_id=VENDOR_B,
        store_id=STORE_B,
        grn_id=GRN_B,
        acc_id=ACC_B,
        approval_ids=(),
        owner_id=USER_OWNER_B,
    )

    # 1. Concurrent POST /gate/escrows with the SAME approval_id -> one 201, one 200, single escrow row!
    barrier = threading.Barrier(2)

    def post_escrow():
        barrier.wait()
        return client.post(
            "/gate/escrows",
            json={"approval_id": APV_ESC_CREATE, "expires_on": "2026-12-10"},
            headers={"X-Service-Key": SERVICE_KEYS["merchant-api"]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(post_escrow)
        f2 = pool.submit(post_escrow)
        r1 = f1.result()
        r2 = f2.result()

    assert sorted([r1.status_code, r2.status_code]) == [200, 201]
    assert r1.json()["escrow_id"] == r2.json()["escrow_id"]
    esc_id = r1.json()["escrow_id"]
    assert sum(1 for c in rail.escrow_calls if c["op"] == "hold") == 1

    # 2. Second approval on same open PO -> 422 GATE_DENIED
    r_dup = client.post(
        "/gate/escrows",
        json={"approval_id": APV_ESC_CREATE_2, "expires_on": "2026-12-10"},
        headers={"X-Service-Key": SERVICE_KEYS["merchant-api"]},
    )
    assert r_dup.status_code == 422

    # 3. Release with TENANT_B approval -> 403 TENANT_MISMATCH!
    _seed_invoice_and_approval(
        admin_url,
        invoice_id=INV_B,
        approval_id=APV_B,
        amount_vnd=8_800_000,
        tenant_id=TENANT_B,
        store_id=STORE_B,
        method="single",
        status="escrow_held",
        severity="yellow",
        vendor_id=VENDOR_B,
        seller_tax_id="0999888001",
        payee_account_id=ACC_B,
        channel="escrow",
        purchase_order_id=PO_B,
        doc_sha="c" * 64,
        approver_user_id=USER_OWNER_B,
    )
    r_tm = client.post(
        f"/gate/escrows/{esc_id}:release",
        json={"approval_id": APV_B, "goods_receipt_id": GRN_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_tm.status_code == 403 and r_tm.json()["code"] == "TENANT_MISMATCH"

    # 4. Seed valid TENANT_A release approval + invoice, then switch mandate to `review_only` -> 422 DENY!
    _seed_invoice_and_approval(
        admin_url,
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
    # Cross-tenant GRN -> 403 TENANT_MISMATCH!
    r_grn_tm = client.post(
        f"/gate/escrows/{esc_id}:release",
        json={"approval_id": APV_ESC_RELEASE, "goods_receipt_id": GRN_B},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_grn_tm.status_code == 403 and r_grn_tm.json()["code"] == "TENANT_MISMATCH"

    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("UPDATE core.mandates SET mode = 'review_only' WHERE tenant_id = %s;", (TENANT_A,))
    r_ro = client.post(
        f"/gate/escrows/{esc_id}:release",
        json={"approval_id": APV_ESC_RELEASE, "goods_receipt_id": GRN_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_ro.status_code == 422
    assert any(gr["code"] == "MANDATE_NOT_AUTO_PAY" for gr in r_ro.json()["gate_reasons"])

    # Switch mandate back to ask_first -> release succeeds and writes append-only ledger + outbox!
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("UPDATE core.mandates SET mode = 'ask_first' WHERE tenant_id = %s;", (TENANT_A,))
    r_rel = client.post(
        f"/gate/escrows/{esc_id}:release",
        json={"approval_id": APV_ESC_RELEASE, "goods_receipt_id": GRN_01},
        headers={"X-Service-Key": SERVICE_KEYS["core-worker"]},
    )
    assert r_rel.status_code == 200 and r_rel.json()["status"] == "released"

    with psycopg.connect(gate_url, row_factory=dict_row) as gconn:
        entries = gconn.execute("SELECT * FROM ledger.ledger_entries ORDER BY created_at;").fetchall()
        assert [e["entry_type"] for e in entries] == ["escrow_held", "escrow_released"]
        outbox = gconn.execute("SELECT * FROM ledger.outbox ORDER BY seq;").fetchall()
        assert [o["type"] for o in outbox] == ["escrow.held", "escrow.released"]
        for o in outbox:
            validate_outbox_event_against_contract(o)

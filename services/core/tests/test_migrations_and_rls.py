"""DB tests for migrations, seed loader, RLS tenant isolation, and staff role isolation."""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from core.persistence.db import Database
from core.persistence.migrator import apply_migrations
from core.persistence.seeder import load_core_seed
from core.shared.ids import new_id

import json
import pathlib

DEMO_SEED_DIR = (
    pathlib.Path(__file__).resolve().parents[3]
    / "services"
    / "sim-world"
    / "data"
    / "demo"
    / "core_seed"
)
_SEED_VENDORS = json.loads((DEMO_SEED_DIR / "vendors.json").read_text(encoding="utf-8"))
TENANT_A = "ten_01M88D3C06B97Y4G0S9W8BVKNG"
TENANT_B = "ten_01M88AXX2KPMD46VQQTDDH040J"


@pytest.mark.db
def test_migrations_are_idempotent_and_seed_loads_demo_counts(pg_dsn: str) -> None:
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        second_run = apply_migrations(conn)
        assert second_run == []
        counts = load_core_seed(conn, seed_dir=DEMO_SEED_DIR, reset=True)

    assert counts["tenants"] == 2
    assert counts["stores"] == 19
    assert counts["vendors"] == len(_SEED_VENDORS["vendors"])
    assert counts["tools"] == 30
    assert counts["bots"] == 6
    assert counts["utility_accounts"] == 32
    assert counts["utility_readings"] == 384


@pytest.mark.db
def test_invariant_rls_tenant_a_sees_zero_rows_of_tenant_b(seeded_db: Database) -> None:
    """Invariant (repo-and-testing.md §4): role merchant tenant A querying tenant B invoices returns 0 rows."""
    doc_a = new_id("doc")
    doc_b = new_id("doc")
    inv_a = new_id("inv")
    inv_b = new_id("inv")

    with seeded_db.connect() as conn:
        with conn.transaction():
            for tid, doc_id, inv_id, num in [
                (TENANT_A, doc_a, inv_a, "0001"),
                (TENANT_B, doc_b, inv_b, "0002"),
            ]:
                conn.execute(
                    """
                    INSERT INTO core.invoice_documents (document_id, tenant_id, format, sha256, raw_bytes, received_at)
                    VALUES (%s, %s, 'xml', %s, %s, now())
                    """,
                    (doc_id, tid, f"sha_{inv_id}", b"<HDon/>"),
                )
                conn.execute(
                    """
                    INSERT INTO core.invoices (
                        invoice_id, tenant_id, document_id, seller_tax_id, symbol, number, number_norm,
                        invoice_type, source, status
                    )
                    VALUES (%s, %s, %s, '0999010001', '1C26TAA', %s, %s, 'goods', 'upload', 'investigating')
                    """,
                    (inv_id, tid, doc_id, num, str(int(num))),
                )

    with seeded_db.connect(role="merchant", tenant_id=TENANT_A) as conn:
        rows = conn.execute("SELECT invoice_id, tenant_id FROM core.invoices").fetchall()
        assert [r["invoice_id"] for r in rows] == [inv_a]
        b_rows = conn.execute(
            "SELECT invoice_id FROM core.invoices WHERE invoice_id = %s", (inv_b,)
        ).fetchall()
        assert b_rows == []
        vendors = conn.execute("SELECT DISTINCT tenant_id FROM core.vendors").fetchall()
        assert [v["tenant_id"] for v in vendors] == [TENANT_A]

    with seeded_db.connect(role="merchant", tenant_id=TENANT_B) as conn:
        rows_b = conn.execute("SELECT invoice_id FROM core.invoices").fetchall()
        assert [r["invoice_id"] for r in rows_b] == [inv_b]


@pytest.mark.db
def test_invariant_staff_role_cannot_read_invoices_table(seeded_db: Database) -> None:
    """Invariant (repo-and-testing.md §4): role staff reading core.invoices directly is denied."""
    with seeded_db.connect(role="staff") as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM core.invoices").fetchall()

    # Meanwhile staff CAN read/write risk & control and INSERT into core.outbox
    with seeded_db.connect(role="staff") as conn:
        with conn.transaction():
            cxa_id = new_id("cxa")
            conn.execute(
                """
                INSERT INTO risk.cross_alerts (cross_alert_id, indicator_ids, reason_codes, published_by, status)
                VALUES (%s, %s, %s, 'stf_test', 'published')
                """,
                (cxa_id, ["ind_test"], ["PERSONAL_ACCOUNT"]),
            )
            conn.execute(
                """
                INSERT INTO core.outbox (event_id, type, occurred_at, tenant_id, data)
                VALUES (%s, 'cross_alert.published', now(), NULL, '{}'::jsonb)
                """,
                (new_id("evt"),),
            )


@pytest.mark.db
def test_gate_role_readonly_cross_schema_shape(seeded_db: Database) -> None:
    """Verify payment-gate DB role can SELECT all agreed cross-schema tables/columns and cannot mutate core."""
    with seeded_db.connect(role="gate") as conn:
        tenants = conn.execute("SELECT tenant_id, wallet_id FROM core.tenants").fetchall()
        assert len(tenants) == 2
        assert all(t["wallet_id"].startswith("wal_") for t in tenants)

        owners = conn.execute(
            "SELECT user_id, tenant_id, role FROM core.users WHERE role = 'owner'"
        ).fetchall()
        assert len(owners) >= 2

        conn.execute(
            """
            SELECT invoice_id, tenant_id, store_id, vendor_id, purchase_order_id, status, total_vnd, document_sha256
            FROM core.invoices
            """
        ).fetchall()
        conn.execute(
            """
            SELECT approval_id, invoice_id, purchase_order_id, status, method, amount_vnd,
                   payee_account_id, channel, intent_hash, verification
            FROM core.approvals
            """
        ).fetchall()
        vas = conn.execute(
            "SELECT vendor_account_id, vendor_id, kind, status FROM core.vendor_accounts"
        ).fetchall()
        assert len(vas) == len(_SEED_VENDORS["vendor_accounts"])
        mandates = conn.execute("SELECT mandate_id, tenant_id, mode, limits FROM core.mandates").fetchall()
        assert len(mandates) == 2

        pols = conn.execute(
            """
            SELECT policy_id, kind, scope, target_id, value, status, engaged_by, released_by, updated_at
            FROM control.policies WHERE kind = 'platform_limits' AND status = 'active'
            """
        ).fetchall()
        assert len(pols) == 1
        assert pols[0]["value"]["auto_pay_per_invoice_vnd"] == 30_000_000
        assert pols[0]["value"]["auto_pay_per_day_vnd"] == 50_000_000

        conn.execute(
            "SELECT hard_block_id, indicator_kind, value_hash, status, created_at FROM risk.hard_blocks"
        ).fetchall()
        conn.execute(
            "SELECT cross_alert_id, indicator_kind, value_hash, status, published_at FROM risk.cross_alerts"
        ).fetchall()

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE core.invoices SET status = 'paid'")
        conn.rollback()
        # I5: gate must NOT be able to read raw document bytes or raw finding reason text
        conn.execute("SET LOCAL ROLE gate")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT raw_bytes FROM core.invoice_documents")
        conn.rollback()
        conn.execute("SET LOCAL ROLE gate")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT reason FROM core.findings")


@pytest.mark.db
def test_b1_i5_non_superuser_service_roles_rls_and_narrow_grants(
    seeded_db: Database,
    merchant_db: Database,
    internal_db: Database,
    worker_db: Database,
    migrator_db: Database,
) -> None:
    """B1 & I5: separate non-superuser login roles per service, narrow grants, outbox type guards, immutable docs."""
    with seeded_db.connect() as conn:
        roles = {
            r["rolname"]: r
            for r in conn.execute(
                """
                SELECT rolname, rolsuper, rolbypassrls
                FROM pg_roles
                WHERE rolname IN ('merchant_api', 'internal_api', 'worker', 'migrator')
                """
            ).fetchall()
        }
    assert set(roles.keys()) == {"merchant_api", "internal_api", "worker", "migrator"}
    for name, info in roles.items():
        assert info["rolsuper"] is False, f"{name} must not be superuser"
    for name in ("merchant_api", "internal_api", "worker"):
        assert roles[name]["rolbypassrls"] is False, f"{name} must not bypass RLS"

    # internal_api cannot query core.invoices without SET LOCAL ROLE merchant + app.tenant_id
    with internal_db.connect() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM core.invoices")
        conn.rollback()
        # But CAN read model_configs and call lookup_job_tenant
        conn.execute("SELECT purpose FROM control.model_configs").fetchall()
        assert conn.execute("SELECT core.lookup_job_tenant('job_nonexistent') AS tid").fetchone()["tid"] is None

    # internal_api under SET LOCAL ROLE merchant + app.tenant_id sees ONLY that tenant
    with internal_db.connect(role="merchant", tenant_id=TENANT_A) as conn:
        tids = {r["tenant_id"] for r in conn.execute("SELECT tenant_id FROM core.tenants").fetchall()}
        assert tids == {TENANT_A}

    # merchant_api cannot mutate immutable core.invoice_documents or insert staff-only outbox events
    with merchant_db.connect(role="merchant", tenant_id=TENANT_A) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE core.invoice_documents SET filename = 'tampered'")
        conn.rollback()
        conn.execute("SET LOCAL ROLE merchant")
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (TENANT_A,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE core.audit_events SET action = 'tampered'")
        conn.rollback()
        conn.execute("SET LOCAL ROLE merchant")
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (TENANT_A,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                """
                INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, data)
                VALUES ('evt_01TESTBADMERCH000000000000', 'cross_alert.published', 1, now(), NULL, '{}'::jsonb)
                """
            )
        conn.rollback()

    # staff cannot insert non-staff event types (e.g. invoice.ingested) into core.outbox
    with seeded_db.connect(role="staff") as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                """
                INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, data)
                VALUES ('evt_01TESTBADSTAFF0000000000', 'invoice.ingested', 1, now(), %s, '{}'::jsonb)
                """,
                (TENANT_A,),
            )
        conn.rollback()

    # worker cannot mutate immutable invoice_documents
    with worker_db.connect() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE core.invoice_documents SET filename = 'tampered'")
        conn.rollback()
        # worker CAN read core.tenants and core.outbox_receipts
        assert len(conn.execute("SELECT tenant_id FROM core.tenants").fetchall()) == 2
        conn.execute("SELECT source, event_id FROM core.outbox_receipts").fetchall()

    # migrator (non-superuser) CAN run full seed reset cleanly
    with migrator_db.connect() as conn:
        counts = load_core_seed(conn, seed_dir=DEMO_SEED_DIR, reset=True)
    assert counts["tenants"] == 2


@pytest.mark.db
def test_i1_i7_backfill_receipts_staff_kill_switch_and_demo_reset_role(
    pg_dsn: str,
    seeded_db: Database,
    demo_reset_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I1 & I7: pre-006 processed_events backfill into outbox_receipts; staff kill_switch.engaged/released; narrow demo_reset role; no bootstrap DSN default."""
    from urllib.parse import urlparse, urlunparse
    from core.shared.config import CoreSettings

    # I7: CoreSettings.from_env() fails closed when DATABASE_URL is unset and ignores DEMO_RESET_DATABASE_URL outside DEMO_MODE
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("DEMO_RESET_DATABASE_URL", "postgresql://demo_reset:demo_reset_dev@localhost:5432/paymatch")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        CoreSettings.from_env()
    monkeypatch.setenv("DATABASE_URL", "postgresql://merchant_api:merchant_api_dev@localhost:5432/paymatch")
    cfg_prod = CoreSettings.from_env()
    assert cfg_prod.demo_reset_database_url is None
    monkeypatch.setenv("DEMO_MODE", "true")
    cfg_demo = CoreSettings.from_env()
    assert cfg_demo.demo_reset_database_url is not None and "demo_reset" in cfg_demo.demo_reset_database_url

    # I7: staff CAN insert contracted kill_switch.engaged and kill_switch.released, CANNOT insert kill_switch.updated
    with seeded_db.connect(role="staff") as conn:
        with conn.transaction():
            for ev_type in ("kill_switch.engaged", "kill_switch.released"):
                conn.execute(
                    """
                    INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, data)
                    VALUES (%s, %s, 1, now(), NULL, '{}'::jsonb)
                    """,
                    (new_id("evt"), ev_type),
                )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                """
                INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, data)
                VALUES (%s, 'kill_switch.updated', 1, now(), NULL, '{}'::jsonb)
                """,
                (new_id("evt"),),
            )
        conn.rollback()

    # I7: demo_reset role is non-superuser, CAN run seed reset via core.truncate_for_demo_reset(), CANNOT DDL or direct TRUNCATE
    with seeded_db.connect() as conn:
        dr_role = conn.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname = 'demo_reset'"
        ).fetchone()
        assert dr_role is not None and dr_role["rolsuper"] is False

    with demo_reset_db.connect() as conn:
        counts = load_core_seed(conn, seed_dir=DEMO_SEED_DIR, reset=True)
        assert counts["tenants"] == 2
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("TRUNCATE TABLE core.invoices CASCADE")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("ALTER TABLE core.invoices ADD COLUMN evil TEXT")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DROP TABLE core.approval_previews")
        conn.rollback()

    # I1: Upgrade from 001..005 with existing core.processed_events backfills core.outbox_receipts in 006
    migrations_dir = pathlib.Path(__file__).resolve().parents[1] / "migrations"
    upgrade_db = "test_i1_upgrade_backfill"
    with psycopg.connect(pg_dsn, autocommit=True) as admin_conn:
        admin_conn.execute(f"DROP DATABASE IF EXISTS {upgrade_db}")
        admin_conn.execute(f"CREATE DATABASE {upgrade_db}")
    parsed = urlparse(pg_dsn)
    upgrade_dsn = urlunparse(parsed._replace(path=f"/{upgrade_db}"))
    try:
        with psycopg.connect(upgrade_dsn, row_factory=dict_row) as uconn:
            with uconn.transaction():
                uconn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS core_schema_migrations (
                        filename TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            for sql_path in sorted(migrations_dir.glob("*.sql")):
                if sql_path.name.startswith("006_"):
                    break
                with uconn.transaction():
                    uconn.execute(sql_path.read_text(encoding="utf-8"))
                    uconn.execute(
                        "INSERT INTO core_schema_migrations (filename) VALUES (%s)",
                        (sql_path.name,),
                    )
            # Simulate pre-006 worker having processed events in core.processed_events
            hist_evt = new_id("evt")
            with uconn.transaction():
                uconn.execute(
                    """
                    INSERT INTO core.processed_events (outbox_name, event_id, processed_at)
                    VALUES ('core', %s, now()), ('ledger', 'evt_01HISTLEDGER00000000000000', now())
                    """,
                    (hist_evt,),
                )
            # Now apply remaining migrations (006+)
            applied = apply_migrations(uconn)
            assert any(f.startswith("006_") for f in applied)
            receipts = {
                (r["source"], r["event_id"])
                for r in uconn.execute("SELECT source, event_id FROM core.outbox_receipts").fetchall()
            }
            assert ("core", hist_evt) in receipts
            assert ("ledger", "evt_01HISTLEDGER00000000000000") in receipts
    finally:
        with psycopg.connect(pg_dsn, autocommit=True) as admin_conn:
            admin_conn.execute(f"DROP DATABASE IF EXISTS {upgrade_db}")


@pytest.mark.db
def test_n8_cli_migrator_and_seeder_and_n7_negative_ledger_grant_and_n6_fair_claim(
    pg_dsn: str,
    seeded_db: Database,
    internal_db: Database,
) -> None:
    """N8: real CLI `python -m core.persistence.migrator` + `seeder` & default-tuple `truncate_all` work against Postgres.
    N7: worker gets narrow SELECT on ledger.outbox/payment_intents only — DENIED on unrelated ledger.payment_tokens.
    N6: 60 queued jobs in a saturated tenant cannot starve another tenant's eligible job in core.claim_next_job.
    """
    import json
    import os
    import subprocess
    import sys
    from urllib.parse import urlparse, urlunparse
    from core.persistence.db import dsn_for_role
    from core.persistence.job_lease import claim_next_job
    from core.persistence.seeder import load_core_seed, seed_dsn

    # --- N8 + N7: Fresh DB with ledger (including unrelated ledger.payment_tokens) -> run REAL CLI migrator + seeder ---
    cli_db = "test_n8_cli_seeder"
    with psycopg.connect(pg_dsn, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {cli_db}")
        admin.execute(f"CREATE DATABASE {cli_db}")
    parsed = urlparse(pg_dsn)
    cli_dsn = urlunparse(parsed._replace(path=f"/{cli_db}"))
    try:
        with psycopg.connect(cli_dsn) as conn:
            with conn.transaction():
                conn.execute("CREATE SCHEMA ledger")
                conn.execute(
                    """
                    CREATE TABLE ledger.outbox (
                        seq BIGSERIAL, event_id TEXT PRIMARY KEY, type TEXT NOT NULL,
                        schema_version INT NOT NULL DEFAULT 1, occurred_at TIMESTAMPTZ NOT NULL,
                        tenant_id TEXT NULL, trace_id TEXT NULL, data JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE ledger.payment_intents (
                        payment_intent_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                        invoice_id TEXT NOT NULL, approval_id TEXT NOT NULL,
                        status TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE ledger.payment_tokens (
                        token_id TEXT PRIMARY KEY, secret_pan TEXT NOT NULL
                    )
                    """
                )

        env = {**os.environ, "DATABASE_URL": cli_dsn}
        r_mig = subprocess.run(
            [sys.executable, "-m", "core.persistence.migrator"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "006_reverify_hardening.sql" in r_mig.stdout

        r_seed = subprocess.run(
            [sys.executable, "-m", "core.persistence.seeder"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        seed_counts = json.loads(r_seed.stdout)
        assert seed_counts["tenants"] == 2
        assert seed_counts["bots"] == 6

        # Also verify direct seed_dsn() and tuple-row connection load_core_seed(reset=True)
        counts2 = seed_dsn(cli_dsn, seed_dir=DEMO_SEED_DIR, reset=True)
        assert counts2["tenants"] == 2
        with psycopg.connect(cli_dsn) as tuple_conn:
            counts3 = load_core_seed(tuple_conn, seed_dir=DEMO_SEED_DIR, reset=True)
            assert counts3["tenants"] == 2

        # N7: negative ledger grant test — worker CAN read outbox & payment_intents, CANNOT read unrelated ledger.payment_tokens!
        worker_cli_dsn = dsn_for_role(cli_dsn, "worker", "worker_dev")
        with psycopg.connect(worker_cli_dsn, row_factory=dict_row) as wconn:
            wconn.execute("SELECT event_id FROM ledger.outbox").fetchall()
            wconn.execute("SELECT payment_intent_id FROM ledger.payment_intents").fetchall()
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                wconn.execute("SELECT * FROM ledger.payment_tokens").fetchall()
            wconn.rollback()
    finally:
        with psycopg.connect(pg_dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {cli_db}")

    # --- N6: Saturated Tenant A (1 running + 60 older queued jobs) MUST NOT starve Tenant B's newer queued job ---
    with seeded_db.connect() as conn:
        with conn.transaction():
            conn.execute("DELETE FROM core.jobs")
            # Tenant A already has 1 running job (saturates max_concurrent=1)
            conn.execute(
                """
                INSERT INTO core.jobs (job_id, tenant_id, task_type, subject, status, attempt, worker_id, lease_expires_at, created_at)
                VALUES (%s, %s, 'investigate_invoice', '{}'::jsonb, 'running', 1, 'w_busy', clock_timestamp() + interval '5 minutes', now() - interval '2 hours')
                """,
                (new_id("job"), TENANT_A),
            )
            # 60 older queued jobs for saturated Tenant A
            for i in range(60):
                conn.execute(
                    """
                    INSERT INTO core.jobs (job_id, tenant_id, task_type, subject, status, created_at)
                    VALUES (%s, %s, 'investigate_invoice', '{}'::jsonb, 'queued', now() - interval '1 hour' + make_interval(secs => %s))
                    """,
                    (new_id("job"), TENANT_A, i),
                )
            # 1 newer queued job for idle Tenant B
            job_b = new_id("job")
            conn.execute(
                """
                INSERT INTO core.jobs (job_id, tenant_id, task_type, subject, status, created_at)
                VALUES (%s, %s, 'investigate_invoice', '{}'::jsonb, 'queued', now())
                """,
                (job_b, TENANT_B),
            )

    with internal_db.connect() as iconn:
        with iconn.transaction():
            claimed = claim_next_job(
                iconn,
                worker_id="w_fair",
                allowed_types=["investigate_invoice"],
                lease_seconds=120,
                max_concurrent_per_tenant=1,
            )
    assert claimed is not None
    assert claimed["job_id"] == job_b
    assert claimed["tenant_id"] == TENANT_B

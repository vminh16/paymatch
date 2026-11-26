"""DB tests for migrations, seed loader, RLS tenant isolation, and staff role isolation."""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from core.persistence.db import Database
from core.persistence.migrator import apply_migrations
from core.persistence.seeder import load_core_seed
from core.shared.ids import new_id

import pathlib

DEMO_SEED_DIR = (
    pathlib.Path(__file__).resolve().parents[3]
    / "services"
    / "sim-world"
    / "data"
    / "demo"
    / "core_seed"
)
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
    assert counts["vendors"] == 52
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
        assert len(vas) == 52
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

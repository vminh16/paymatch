"""Plain numbered SQL migration runner for schema `ledger` (no ORM, no Alembic).

Resolves packaged `gate/migrations` first (inside wheel/Docker), falling back to
the repository `services/payment-gate/migrations` directory in editable installs.
"""

from __future__ import annotations

import os
import pathlib
import sys

import psycopg


def resolve_migrations_dir(migrations_dir: pathlib.Path | None = None) -> pathlib.Path:
    if migrations_dir is not None:
        return migrations_dir
    packaged = pathlib.Path(__file__).resolve().parents[2] / "migrations"
    if packaged.is_dir() and list(packaged.glob("[0-9]*.sql")):
        return packaged
    repo_dir = pathlib.Path(__file__).resolve().parents[4] / "migrations"
    if repo_dir.is_dir() and list(repo_dir.glob("[0-9]*.sql")):
        return repo_dir
    raise FileNotFoundError(
        f"Could not find ledger SQL migrations in {packaged} or {repo_dir}."
    )


def apply_migrations(
    conninfo: str,
    migrations_dir: pathlib.Path | None = None,
) -> list[str]:
    """Apply all unapplied numbered *.sql migrations in lexicographical order."""
    mig_dir = resolve_migrations_dir(migrations_dir)
    sql_files = sorted(mig_dir.glob("[0-9]*.sql"))
    applied: list[str] = []

    with psycopg.connect(conninfo, autocommit=False) as conn:
        with conn.cursor() as cur:
            # Serialize concurrent boot migrations across replicas.
            cur.execute("SELECT pg_advisory_lock(hashtextextended('paymatch.ledger.migrations', 0));")
            try:
                cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.schemata WHERE schema_name = 'ledger'
                        ) THEN
                            EXECUTE 'CREATE SCHEMA ledger';
                        END IF;
                    END
                    $$;
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ledger.schema_migrations (
                        version TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                conn.commit()

                cur.execute("SELECT version FROM ledger.schema_migrations;")
                existing = {row[0] for row in cur.fetchall()}

                for sql_path in sql_files:
                    version = sql_path.name
                    if version in existing:
                        continue
                    cur.execute(sql_path.read_text(encoding="utf-8"))
                    cur.execute(
                        "INSERT INTO ledger.schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING;",
                        (version,),
                    )
                    conn.commit()
                    applied.append(version)
            finally:
                cur.execute(
                    "SELECT pg_advisory_unlock(hashtextextended('paymatch.ledger.migrations', 0));"
                )
                conn.commit()

    return applied


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        sys.exit(1)
    applied = apply_migrations(database_url)
    print(f"Applied migrations: {applied or 'none (already up to date)'}")


if __name__ == "__main__":
    main()

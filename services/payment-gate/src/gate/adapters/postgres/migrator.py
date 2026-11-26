"""Plain numbered SQL migration runner for schema `ledger` (no ORM, no Alembic)."""

from __future__ import annotations

import os
import pathlib
import sys

import psycopg

DEFAULT_MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[4] / "migrations"


def apply_migrations(
    conninfo: str,
    migrations_dir: pathlib.Path | None = None,
) -> list[str]:
    """Apply all unapplied numbered *.sql migrations in lexicographical order."""
    mig_dir = migrations_dir or DEFAULT_MIGRATIONS_DIR
    sql_files = sorted(mig_dir.glob("[0-9]*.sql"))
    applied: list[str] = []

    with psycopg.connect(conninfo, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS ledger;")
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

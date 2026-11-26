"""Plain numbered SQL migration runner for services/core/migrations/."""

from __future__ import annotations

import pathlib
import sys

import psycopg

DEFAULT_MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[3] / "migrations"


def apply_migrations(
    conn: psycopg.Connection,
    migrations_dir: pathlib.Path = DEFAULT_MIGRATIONS_DIR,
) -> list[str]:
    """Apply all pending numbered .sql migration files in lexical order. Returns applied filenames."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS public.core_schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.commit()

    applied_rows = conn.execute(
        "SELECT filename FROM public.core_schema_migrations"
    ).fetchall()
    already_applied = {
        row["filename"] if isinstance(row, dict) else row[0] for row in applied_rows
    }

    applied_now: list[str] = []
    sql_files = sorted(migrations_dir.glob("*.sql"))
    for sql_file in sql_files:
        if sql_file.name in already_applied:
            continue
        sql = sql_file.read_text(encoding="utf-8")
        with conn.transaction():
            conn.execute(sql)
            conn.execute(
                "INSERT INTO public.core_schema_migrations (filename) VALUES (%s)",
                (sql_file.name,),
            )
        applied_now.append(sql_file.name)
    return applied_now


def migrate_dsn(dsn: str, migrations_dir: pathlib.Path = DEFAULT_MIGRATIONS_DIR) -> list[str]:
    with psycopg.connect(dsn) as conn:
        return apply_migrations(conn, migrations_dir=migrations_dir)


if __name__ == "__main__":
    from core.shared.config import CoreSettings

    cfg = CoreSettings.from_env()
    applied = migrate_dsn(cfg.database_url)
    print(f"Applied migrations: {applied}" if applied else "All migrations already applied.")
    sys.exit(0)

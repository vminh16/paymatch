"""PostgreSQL connection helper with optional RLS role/tenant scoping."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row


class Database:
    """Thin psycopg v3 connection factory supporting RLS tenant context."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @contextmanager
    def connect(
        self,
        *,
        role: str | None = None,
        tenant_id: str | None = None,
        autocommit: bool = False,
    ) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        with psycopg.connect(self.dsn, row_factory=dict_row, autocommit=autocommit) as conn:
            if role is not None:
                if role not in {"merchant", "staff", "gate"}:
                    raise ValueError(f"Unsupported DB role: {role!r}")
                conn.execute(f"SET LOCAL ROLE {role}")
            if tenant_id is not None:
                conn.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (tenant_id,),
                )
            yield conn

    def ping(self) -> bool:
        try:
            with psycopg.connect(self.dsn, connect_timeout=2) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False

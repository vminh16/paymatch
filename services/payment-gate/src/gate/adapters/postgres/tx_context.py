"""Context-scoped Postgres connection binding so read queries reuse an active transaction."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import psycopg

_BOUND_CONN: ContextVar[psycopg.Connection[dict[str, Any]] | None] = ContextVar(
    "gate_pg_bound_conn", default=None
)


def get_bound_connection() -> psycopg.Connection[dict[str, Any]] | None:
    return _BOUND_CONN.get()


@contextmanager
def bind_connection(conn: psycopg.Connection[dict[str, Any]]) -> Iterator[None]:
    token = _BOUND_CONN.set(conn)
    try:
        yield
    finally:
        _BOUND_CONN.reset(token)

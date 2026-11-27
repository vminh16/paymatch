"""Receipt-based outbox polling (B2) immune to BIGSERIAL commit-order gaps."""

from __future__ import annotations

from typing import Any

import psycopg

_ALLOWED_OUTBOX_TABLES = frozenset({"core.outbox", "ledger.outbox"})


def fetch_unacknowledged_events(
    conn: psycopg.Connection,
    *,
    source: str,
    table: str,
    batch_size: int = 100,
    after_seq: int = 0,
) -> list[dict[str, Any]]:
    """Select committed outbox events (seq > after_seq) that have no receipt in core.outbox_receipts."""
    if table not in _ALLOWED_OUTBOX_TABLES:
        raise ValueError(f"Unsupported outbox table: {table!r}")
    return conn.execute(
        f"""
        SELECT o.seq, o.event_id, o.type, o.schema_version, o.occurred_at, o.tenant_id, o.trace_id, o.data
        FROM {table} o
        WHERE o.seq > %s
          AND NOT EXISTS (
            SELECT 1 FROM core.outbox_receipts r
            WHERE r.source = %s AND r.event_id = o.event_id
        )
        ORDER BY o.seq ASC
        LIMIT %s
        """,
        (after_seq, source, batch_size),
    ).fetchall()


def record_receipt(conn: psycopg.Connection, *, source: str, event_id: str) -> bool:
    """Atomically record receipt in core.outbox_receipts within the caller's transaction.

    Returns True if newly recorded (caller should apply effects), False if already processed.
    """
    row = conn.execute(
        """
        INSERT INTO core.outbox_receipts (source, event_id, processed_at)
        VALUES (%s, %s, now())
        ON CONFLICT (source, event_id) DO NOTHING
        RETURNING event_id
        """,
        (source, event_id),
    ).fetchone()
    return row is not None

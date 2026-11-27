"""Risk cross-alert publishing use case (F3) — used by console-api and F3 integration tests."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from core.shared.clock import Clock, SystemClock
from core.shared.ids import new_id

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def publish_cross_alert(
    conn: psycopg.Connection,
    *,
    indicators: Sequence[dict[str, str]],
    reason_codes: Sequence[str],
    published_by: str,
    trace_id: str | None = None,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Upsert indicators, insert published risk.cross_alerts, and emit cross_alert.published in one transaction."""
    clk = clock or SystemClock()
    now = clk.now()
    cross_alert_id = new_id("cxa")
    indicator_ids: list[str] = []
    normalized_indicators: list[dict[str, str]] = []

    with conn.transaction():
        for ind in indicators:
            kind = ind["kind"]
            val_hash = ind["value_hash"].lower()
            if not _SHA256_HEX_RE.fullmatch(val_hash):
                raise ValueError(f"Indicator value_hash must be 64-char lowercase sha256 hex, got {val_hash!r}")
            row = conn.execute(
                """
                INSERT INTO risk.indicators (indicator_id, kind, value_hash, first_seen_at, flags_count)
                VALUES (%s, %s, %s, %s, 1)
                ON CONFLICT (kind, value_hash) DO UPDATE SET flags_count = risk.indicators.flags_count + 1
                RETURNING indicator_id
                """,
                (new_id("ind"), kind, val_hash, now),
            ).fetchone()
            indicator_ids.append(row["indicator_id"])
            normalized_indicators.append({"kind": kind, "value_hash": val_hash})

        primary_kind = normalized_indicators[0]["kind"] if normalized_indicators else None
        primary_hash = normalized_indicators[0]["value_hash"] if normalized_indicators else None

        conn.execute(
            """
            INSERT INTO risk.cross_alerts (
                cross_alert_id, indicator_kind, value_hash, indicator_ids,
                reason_codes, published_by, status, affected_invoice_count, published_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'published', 0, %s)
            """,
            (
                cross_alert_id,
                primary_kind,
                primary_hash,
                indicator_ids,
                list(reason_codes),
                published_by,
                now,
            ),
        )

        conn.execute(
            """
            INSERT INTO core.outbox (event_id, type, schema_version, occurred_at, tenant_id, trace_id, data)
            VALUES (%s, 'cross_alert.published', 1, %s, NULL, %s, %s)
            """,
            (
                new_id("evt"),
                now,
                trace_id,
                Jsonb(
                    {
                        "cross_alert_id": cross_alert_id,
                        "indicators": normalized_indicators,
                        "reason_codes": list(reason_codes),
                    }
                ),
            ),
        )

    return {
        "cross_alert_id": cross_alert_id,
        "indicator_ids": indicator_ids,
        "reason_codes": list(reason_codes),
        "published_by": published_by,
        "status": "published",
        "published_at": now.isoformat(timespec="seconds"),
    }

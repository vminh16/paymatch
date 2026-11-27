"""Atomic lease fencing and narrow cross-tenant claim helpers for internal-api (B1, B6, I4)."""

from __future__ import annotations

from typing import Any

import psycopg

from core.shared.errors import ProblemError


def lookup_job_tenant(conn: psycopg.Connection, job_id: str) -> str:
    """Resolve tenant_id for a job_id via narrow SECURITY DEFINER function before entering tenant RLS."""
    row = conn.execute(
        "SELECT core.lookup_job_tenant(%s) AS tenant_id",
        (job_id,),
    ).fetchone()
    if row is None or not row["tenant_id"]:
        raise ProblemError(404, "NOT_FOUND", "Job not found", f"Job {job_id} không tồn tại.")
    return str(row["tenant_id"])


def claim_next_job(
    conn: psycopg.Connection,
    *,
    worker_id: str,
    allowed_types: list[str],
    lease_seconds: int,
    max_concurrent_per_tenant: int,
) -> dict[str, Any] | None:
    """Atomically claim next queued or expired job via narrow SECURITY DEFINER function using DB clock_timestamp() (B1, I4)."""
    return conn.execute(
        "SELECT * FROM core.claim_next_job(%s, %s, %s, %s)",
        (worker_id, allowed_types, int(lease_seconds), int(max_concurrent_per_tenant)),
    ).fetchone()


def lock_active_job_lease(
    conn: psycopg.Connection,
    *,
    job_id: str,
    tenant_id: str,
    worker_id: str,
    attempt: int,
) -> dict[str, Any]:
    """Acquire FOR UPDATE lock on core.jobs ONLY if job is still actively leased at DB clock_timestamp() (B6, I4).

    Must be called inside an open transaction (`with conn.transaction():`) so the lock serializes
    the subsequent write (tool_call, finding, bot_answer, progress, complete, fail) against
    concurrent lease reclamation by core.claim_next_job.
    """
    job = conn.execute(
        """
        SELECT * FROM core.jobs
        WHERE job_id = %s
          AND tenant_id = %s
          AND status = 'running'
          AND worker_id = %s
          AND attempt = %s
          AND lease_expires_at >= clock_timestamp()
        FOR UPDATE
        """,
        (job_id, tenant_id, worker_id, attempt),
    ).fetchone()
    if job is not None:
        return job

    exists = conn.execute(
        "SELECT job_id FROM core.jobs WHERE job_id = %s AND tenant_id = %s",
        (job_id, tenant_id),
    ).fetchone()
    if exists is None:
        raise ProblemError(404, "NOT_FOUND", "Job not found", f"Job {job_id} không tồn tại.")
    raise ProblemError(
        409,
        "LEASE_LOST",
        "Job lease lost",
        f"Lease của ({job_id}, attempt={attempt}, worker_id={worker_id}) không còn hiệu lực.",
    )


def verify_active_job_lease_readonly(
    conn: psycopg.Connection,
    *,
    job_id: str,
    tenant_id: str,
    worker_id: str,
    attempt: int,
) -> dict[str, Any]:
    """Non-locking lease check against DB clock_timestamp() for read-only endpoints or pre-HTTP checks."""
    job = conn.execute(
        """
        SELECT * FROM core.jobs
        WHERE job_id = %s
          AND tenant_id = %s
          AND status = 'running'
          AND worker_id = %s
          AND attempt = %s
          AND lease_expires_at >= clock_timestamp()
        """,
        (job_id, tenant_id, worker_id, attempt),
    ).fetchone()
    if job is not None:
        return job

    exists = conn.execute(
        "SELECT job_id FROM core.jobs WHERE job_id = %s AND tenant_id = %s",
        (job_id, tenant_id),
    ).fetchone()
    if exists is None:
        raise ProblemError(404, "NOT_FOUND", "Job not found", f"Job {job_id} không tồn tại.")
    raise ProblemError(
        409,
        "LEASE_LOST",
        "Job lease lost",
        f"Lease của ({job_id}, attempt={attempt}, worker_id={worker_id}) không còn hiệu lực.",
    )


def renew_job_lease(
    conn: psycopg.Connection,
    *,
    job_id: str,
    tenant_id: str,
    worker_id: str,
    attempt: int,
    lease_seconds: int,
) -> dict[str, Any]:
    """Atomically extend lease_expires_at guarded by DB clock_timestamp() in a single UPDATE (B6, I4)."""
    updated = conn.execute(
        """
        UPDATE core.jobs
        SET lease_expires_at = clock_timestamp() + make_interval(secs => %s),
            updated_at = clock_timestamp()
        WHERE job_id = %s
          AND tenant_id = %s
          AND status = 'running'
          AND worker_id = %s
          AND attempt = %s
          AND lease_expires_at >= clock_timestamp()
        RETURNING *
        """,
        (max(int(lease_seconds), 1), job_id, tenant_id, worker_id, attempt),
    ).fetchone()
    if updated is not None:
        return updated

    exists = conn.execute(
        "SELECT job_id FROM core.jobs WHERE job_id = %s AND tenant_id = %s",
        (job_id, tenant_id),
    ).fetchone()
    if exists is None:
        raise ProblemError(404, "NOT_FOUND", "Job not found", f"Job {job_id} không tồn tại.")
    raise ProblemError(
        409,
        "LEASE_LOST",
        "Job lease lost",
        f"Lease của ({job_id}, attempt={attempt}, worker_id={worker_id}) không còn hiệu lực.",
    )

"""Environment-driven settings for core processes (no hard-coded URLs/keys/limits)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SEED_DIR = (
    Path(__file__).resolve().parents[5] / "services" / "sim-world" / "data" / "demo" / "core_seed"
)


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CoreSettings:
    database_url: str = ""
    demo_reset_database_url: str | None = None
    sim_url: str = "http://localhost:8200/sim"
    gate_url: str = "http://localhost:8100/gate"
    demo_mode: bool = False
    sim_core_service_key: str = ""
    gate_core_service_key: str = ""
    internal_agent_service_key: str = ""
    internal_sim_webhook_key: str = ""
    identity_jwt_issuer: str = "sim-world"
    seed_dir: Path = DEFAULT_SEED_DIR
    capability_signing_key_pem: str | None = None
    session_signing_key_pem: str | None = None
    merchant_port: int = 8001
    internal_port: int = 8003
    worker_poll_interval_s: float = 2.0
    job_lease_seconds: int = 120
    max_concurrent_jobs_per_tenant: int = 5
    session_ttl_seconds: int = 43200  # 12h
    sse_replay_window_seconds: int = 600  # 10 min
    sse_poll_interval_s: float = 0.25
    sse_keepalive_interval_s: float = 15.0
    sse_max_idle_seconds: float | None = 300.0
    max_invoice_bytes: int = 5 * 1024 * 1024  # 5 MiB
    max_xml_elements: int = 10_000
    utility_outlier_ratio: str = "1.5"
    default_due_days: int = 7
    approval_preview_ttl_seconds: int = 300

    @classmethod
    def from_env(cls) -> CoreSettings:
        db_url = os.getenv("DATABASE_URL", "").strip()
        if not db_url:
            raise RuntimeError(
                "DATABASE_URL must be explicitly configured with a least-privilege role DSN (no bootstrap default)."
            )
        demo_mode = _parse_bool(os.getenv("DEMO_MODE"), default=False)
        # I7: never load demo_reset credentials when DEMO_MODE is false
        demo_reset_dsn = (os.getenv("DEMO_RESET_DATABASE_URL") or "").strip() or None if demo_mode else None
        seed_raw = os.getenv("CORE_SEED_DIR")
        seed_dir = Path(seed_raw).resolve() if seed_raw else DEFAULT_SEED_DIR
        sse_max_raw = os.getenv("SSE_MAX_IDLE_SECONDS")
        return cls(
            database_url=db_url,
            demo_reset_database_url=demo_reset_dsn,
            sim_url=os.getenv("SIM_URL", "http://localhost:8200/sim").rstrip("/"),
            gate_url=os.getenv("GATE_URL", "http://localhost:8100/gate").rstrip("/"),
            demo_mode=demo_mode,
            sim_core_service_key=os.getenv("SIM_CORE_SERVICE_KEY", ""),
            gate_core_service_key=os.getenv("GATE_CORE_SERVICE_KEY", ""),
            internal_agent_service_key=os.getenv("INTERNAL_AGENT_SERVICE_KEY", ""),
            internal_sim_webhook_key=os.getenv("SIM_WEBHOOK_SERVICE_KEY", ""),
            identity_jwt_issuer=os.getenv("IDENTITY_JWT_ISSUER", "sim-world"),
            seed_dir=seed_dir,
            capability_signing_key_pem=os.getenv("CAPABILITY_SIGNING_KEY_PEM") or None,
            session_signing_key_pem=os.getenv("SESSION_SIGNING_KEY_PEM") or None,
            merchant_port=int(os.getenv("MERCHANT_PORT", "8001")),
            internal_port=int(os.getenv("INTERNAL_PORT", "8003")),
            worker_poll_interval_s=float(os.getenv("WORKER_POLL_INTERVAL_S", "2.0")),
            job_lease_seconds=int(os.getenv("JOB_LEASE_SECONDS", "120")),
            max_concurrent_jobs_per_tenant=int(os.getenv("MAX_CONCURRENT_JOBS_PER_TENANT", "5")),
            session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "43200")),
            sse_replay_window_seconds=int(os.getenv("SSE_REPLAY_WINDOW_SECONDS", "600")),
            sse_poll_interval_s=float(os.getenv("SSE_POLL_INTERVAL_S", "0.25")),
            sse_keepalive_interval_s=float(os.getenv("SSE_KEEPALIVE_INTERVAL_S", "15.0")),
            sse_max_idle_seconds=float(sse_max_raw) if sse_max_raw else 300.0,
            max_invoice_bytes=int(os.getenv("MAX_INVOICE_BYTES", str(5 * 1024 * 1024))),
            max_xml_elements=int(os.getenv("MAX_XML_ELEMENTS", "10000")),
            utility_outlier_ratio=os.getenv("UTILITY_OUTLIER_RATIO", "1.5"),
            default_due_days=int(os.getenv("DEFAULT_DUE_DAYS", "7")),
            approval_preview_ttl_seconds=int(os.getenv("APPROVAL_PREVIEW_TTL_SECONDS", "300")),
        )

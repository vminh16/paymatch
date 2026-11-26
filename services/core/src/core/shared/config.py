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
    database_url: str = "postgresql://paymatch:paymatch@localhost:5432/paymatch"
    sim_url: str = "http://localhost:8200/sim"
    gate_url: str = "http://localhost:8100/gate"
    demo_mode: bool = False
    sim_core_service_key: str = ""
    gate_core_service_key: str = ""
    internal_agent_service_key: str = ""
    internal_sim_webhook_key: str = ""
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

    @classmethod
    def from_env(cls) -> CoreSettings:
        seed_raw = os.getenv("CORE_SEED_DIR")
        seed_dir = Path(seed_raw).resolve() if seed_raw else DEFAULT_SEED_DIR
        return cls(
            database_url=os.getenv(
                "DATABASE_URL", "postgresql://paymatch:paymatch@localhost:5432/paymatch"
            ),
            sim_url=os.getenv("SIM_URL", "http://localhost:8200/sim").rstrip("/"),
            gate_url=os.getenv("GATE_URL", "http://localhost:8100/gate").rstrip("/"),
            demo_mode=_parse_bool(os.getenv("DEMO_MODE"), default=False),
            sim_core_service_key=os.getenv("SIM_CORE_SERVICE_KEY", ""),
            gate_core_service_key=os.getenv("GATE_CORE_SERVICE_KEY", ""),
            internal_agent_service_key=os.getenv("INTERNAL_AGENT_SERVICE_KEY", ""),
            internal_sim_webhook_key=os.getenv("SIM_WEBHOOK_SERVICE_KEY", ""),
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
        )

"""Environment-driven configuration for Payment Gate (no hard-coded URLs, keys, or limits)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    port: int
    database_url: str
    sim_url: str
    sim_gate_service_key: str
    demo_mode: bool
    merchant_api_service_key: str
    core_worker_service_key: str
    internal_api_service_key: str
    console_api_service_key: str
    rail_timeout_seconds: float = 5.0
    poll_interval_seconds: float = 10.0
    authorization_ttl_seconds: int = 15 * 60
    stuck_threshold_seconds: int = 24 * 60 * 60
    enable_background_poller: bool = True
    auto_migrate: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            port=int(os.getenv("GATE_PORT", "8100")),
            database_url=os.getenv("DATABASE_URL", ""),
            sim_url=os.getenv("SIM_URL", "http://localhost:8200/sim").rstrip("/"),
            sim_gate_service_key=os.getenv("SIM_GATE_SERVICE_KEY", ""),
            demo_mode=_env_bool("DEMO_MODE", default=False),
            merchant_api_service_key=os.getenv("GATE_MERCHANT_API_KEY", ""),
            core_worker_service_key=os.getenv("GATE_CORE_WORKER_KEY", ""),
            internal_api_service_key=os.getenv("GATE_INTERNAL_API_KEY", ""),
            console_api_service_key=os.getenv("GATE_CONSOLE_API_KEY", ""),
            rail_timeout_seconds=float(os.getenv("GATE_RAIL_TIMEOUT_SECONDS", "5.0")),
            poll_interval_seconds=float(os.getenv("GATE_POLL_INTERVAL_SECONDS", "10.0")),
            authorization_ttl_seconds=int(os.getenv("GATE_AUTHORIZATION_TTL_SECONDS", "900")),
            stuck_threshold_seconds=int(os.getenv("GATE_STUCK_THRESHOLD_SECONDS", "86400")),
            enable_background_poller=_env_bool("GATE_ENABLE_POLLER", default=True),
            auto_migrate=_env_bool("GATE_AUTO_MIGRATE", default=True),
        )

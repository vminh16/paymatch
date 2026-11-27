"""Environment-driven configuration for sim-world (no hard-coded secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    port: int = 8200
    data_dir: Path = DEFAULT_DATA_DIR
    default_dataset: str = "demo"
    default_seed: int = 42
    demo_mode: bool = False
    core_service_key: str | None = None
    gate_service_key: str | None = None
    core_internal_url: str | None = None
    webhook_service_key: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        data_dir_raw = os.getenv("SIM_DATA_DIR")
        data_dir = Path(data_dir_raw).resolve() if data_dir_raw else DEFAULT_DATA_DIR
        return cls(
            port=int(os.getenv("SIM_PORT", "8200")),
            data_dir=data_dir,
            default_dataset=os.getenv("SIM_DATASET", "demo"),
            default_seed=int(os.getenv("SIM_SEED", "42")),
            demo_mode=_parse_bool(os.getenv("DEMO_MODE"), default=False),
            core_service_key=os.getenv("SIM_CORE_SERVICE_KEY") or None,
            gate_service_key=os.getenv("SIM_GATE_SERVICE_KEY") or None,
            core_internal_url=os.getenv("CORE_INTERNAL_URL") or None,
            webhook_service_key=os.getenv("SIM_WEBHOOK_SERVICE_KEY") or None,
        )

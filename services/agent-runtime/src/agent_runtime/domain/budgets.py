"""Bot limits and runtime configuration (docs/03-agents/agent-runtime.md §6)."""

from __future__ import annotations

from dataclasses import dataclass

# Specialist bot budget per docs/03-agents/agent-runtime.md §6
BOT_MAX_STEPS: int = 6
BOT_TIMEOUT_S: float = 20.0

# Internal API lease heartbeat & tool call settings (docs/05-api/internal-api.md & README.md §6)
HEARTBEAT_INTERVAL_S: float = 30.0
TOOL_INVOKE_TIMEOUT_S: float = 5.0
TOOL_INVOKE_MAX_RETRIES_5XX: int = 1


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime configuration sourced from environment or caller (no hard-coded URLs/keys)."""

    worker_id: str
    bot_max_steps: int = BOT_MAX_STEPS
    bot_timeout_s: float = BOT_TIMEOUT_S
    heartbeat_interval_s: float = HEARTBEAT_INTERVAL_S
    heartbeat_max_consecutive_errors: int = 3
    tool_invoke_timeout_s: float = TOOL_INVOKE_TIMEOUT_S
    tool_invoke_max_retries_5xx: int = TOOL_INVOKE_MAX_RETRIES_5XX
    default_brief_model: str = "unconfigured-brief-model"
    poll_interval_s: float = 1.0

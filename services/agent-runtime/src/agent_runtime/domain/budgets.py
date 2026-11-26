"""Task budgets, bot limits, and runtime configuration (docs/03-agents/agent-runtime.md §2, §6)."""

from __future__ import annotations

from dataclasses import dataclass

from paymatch_contracts.internal import TaskType


@dataclass(frozen=True)
class TaskBudget:
    """Supervisor time and step budget for a task_type."""

    seconds: float
    max_steps: int


# Defaults per docs/03-agents/agent-runtime.md §2
DEFAULT_TASK_BUDGETS: dict[TaskType, TaskBudget] = {
    TaskType.investigate_invoice: TaskBudget(seconds=30.0, max_steps=12),
    TaskType.question: TaskBudget(seconds=15.0, max_steps=8),
    TaskType.report: TaskBudget(seconds=20.0, max_steps=8),
}

# Specialist bot budget per docs/03-agents/agent-runtime.md §6
BOT_MAX_STEPS: int = 6
BOT_TIMEOUT_S: float = 20.0

# Internal API lease heartbeat & tool call settings (docs/05-api/internal-api.md & README.md §6)
HEARTBEAT_INTERVAL_S: float = 30.0
TOOL_INVOKE_TIMEOUT_S: float = 5.0
TOOL_INVOKE_MAX_RETRIES_5XX: int = 1


def default_budget_for_task(task_type: TaskType) -> TaskBudget:
    """Return the default supervisor budget for a given task_type."""
    return DEFAULT_TASK_BUDGETS[task_type]


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime configuration sourced from environment or caller (no hard-coded URLs/keys)."""

    worker_id: str
    bot_max_steps: int = BOT_MAX_STEPS
    bot_timeout_s: float = BOT_TIMEOUT_S
    heartbeat_interval_s: float = HEARTBEAT_INTERVAL_S
    tool_invoke_timeout_s: float = TOOL_INVOKE_TIMEOUT_S
    tool_invoke_max_retries_5xx: int = TOOL_INVOKE_MAX_RETRIES_5XX
    default_bot_model: str = "unconfigured-bot-model"
    default_brief_model: str = "unconfigured-brief-model"
    poll_interval_s: float = 1.0

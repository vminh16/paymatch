"""CLI entrypoint for agent-worker (reads all configuration from environment variables)."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket

from agent_runtime.adapters.internal_api_http import HttpInternalApiClient
from agent_runtime.domain.budgets import (
    BOT_MAX_STEPS,
    BOT_TIMEOUT_S,
    HEARTBEAT_INTERVAL_S,
    RuntimeConfig,
)
from agent_runtime.llm.replay import ReplayLLM
from agent_runtime.session.worker import AgentWorker


def build_config_from_env() -> RuntimeConfig:
    """Build RuntimeConfig from environment variables (no hard-coded URLs/keys/models)."""
    return RuntimeConfig(
        worker_id=os.environ.get("WORKER_ID", f"agent-worker-{socket.gethostname()}"),
        bot_max_steps=int(os.environ.get("BOT_MAX_STEPS", str(BOT_MAX_STEPS))),
        bot_timeout_s=float(os.environ.get("BOT_TIMEOUT_S", str(BOT_TIMEOUT_S))),
        heartbeat_interval_s=float(
            os.environ.get("HEARTBEAT_INTERVAL_S", str(HEARTBEAT_INTERVAL_S))
        ),
        default_bot_model=os.environ.get("DEFAULT_BOT_MODEL", "unconfigured-bot-model"),
        default_brief_model=os.environ.get("DEFAULT_BRIEF_MODEL", "unconfigured-brief-model"),
        poll_interval_s=float(os.environ.get("POLL_INTERVAL_S", "1.0")),
    )


async def _run_main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    internal_url = os.environ["CORE_INTERNAL_URL"]
    service_key = os.environ["AGENT_SERVICE_KEY"]
    llm_mode = os.environ.get("LLM_MODE", "replay")
    if llm_mode != "replay":
        raise RuntimeError(
            f"Unsupported LLM_MODE={llm_mode!r}: real provider adapter is not configured yet; use 'replay'."
        )
    cassette_path = os.environ["LLM_CASSETTE_PATH"]

    config = build_config_from_env()
    llm = ReplayLLM.from_file(cassette_path)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    async with HttpInternalApiClient(base_url=internal_url, service_key=service_key) as api:
        worker = AgentWorker(api=api, llm=llm, config=config)
        await worker.run_forever(stop_event=stop_event)


def main() -> None:
    asyncio.run(_run_main())


if __name__ == "__main__":
    main()

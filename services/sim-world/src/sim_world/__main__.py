"""CLI entrypoint: python -m sim_world."""

from __future__ import annotations

import uvicorn

from sim_world.config import Settings


def main() -> None:
    cfg = Settings.from_env()
    uvicorn.run("sim_world.app:app", host="0.0.0.0", port=cfg.port)


if __name__ == "__main__":
    main()

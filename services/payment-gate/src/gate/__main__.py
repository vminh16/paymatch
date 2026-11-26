"""CLI entrypoint for running Payment Gate server."""

from __future__ import annotations

import uvicorn

from gate.config import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run("gate.adapters.http.app:app", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()

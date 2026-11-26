"""HTTP adapter (FastAPI) for Payment Gate."""

from gate.adapters.http.app import app, create_app

__all__ = ["app", "create_app"]

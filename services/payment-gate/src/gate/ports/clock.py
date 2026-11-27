"""Clock port interface."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Return timezone-aware current timestamp (Vietnam UTC+07:00)."""
        ...

    def today_vn(self) -> date:
        """Return current calendar date in Vietnam timezone (UTC+07:00)."""
        ...

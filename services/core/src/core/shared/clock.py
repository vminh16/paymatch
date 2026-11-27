"""Clock port and adapters (Vietnam timezone +07:00; optional sim-world clock in DEMO_MODE)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Protocol

import httpx

VN_TZ = timezone(timedelta(hours=7))


class Clock(Protocol):
    def now(self) -> datetime: ...

    def today(self) -> date: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(VN_TZ)

    def today(self) -> date:
        return self.now().date()


class FixedClock:
    def __init__(self, dt: datetime) -> None:
        self._dt = dt.astimezone(VN_TZ) if dt.tzinfo else dt.replace(tzinfo=VN_TZ)

    def now(self) -> datetime:
        return self._dt

    def today(self) -> date:
        return self._dt.date()

    def advance(self, delta: timedelta) -> None:
        self._dt = self._dt + delta


class SimWorldClock:
    """Reads simulated time from GET {SIM_URL}/scenario/clock when DEMO_MODE=true."""

    def __init__(self, sim_url: str, service_key: str = "") -> None:
        self._sim_url = sim_url.rstrip("/")
        self._service_key = service_key

    def now(self) -> datetime:
        headers = {"X-Service-Key": self._service_key} if self._service_key else {}
        try:
            resp = httpx.get(f"{self._sim_url}/scenario/clock", headers=headers, timeout=2.0)
            resp.raise_for_status()
            raw = resp.json()["now"]
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(VN_TZ)
        except Exception:
            return datetime.now(VN_TZ)

    def today(self) -> date:
        return self.now().date()

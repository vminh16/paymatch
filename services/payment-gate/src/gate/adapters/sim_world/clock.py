"""Clock adapters: SystemClock and SimWorldClock (used when DEMO_MODE=true)."""

from __future__ import annotations

from datetime import date, datetime

import httpx

from gate.domain.rules import VN_TZ


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(VN_TZ).replace(microsecond=0)

    def today_vn(self) -> date:
        return self.now().astimezone(VN_TZ).date()


class SimWorldClock:
    """Reads simulated clock from GET {SIM_URL}/scenario/clock when DEMO_MODE=true."""

    def __init__(
        self,
        *,
        sim_url: str,
        service_key: str = "",
        timeout_seconds: float = 2.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._url = f"{sim_url.rstrip('/')}/scenario/clock"
        self._headers = {"X-Service-Key": service_key} if service_key else {}
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def now(self) -> datetime:
        resp = self._client.get(self._url, headers=self._headers)
        resp.raise_for_status()
        dt = datetime.fromisoformat(resp.json()["now"])
        return dt.astimezone(VN_TZ)

    def today_vn(self) -> date:
        return self.now().astimezone(VN_TZ).date()

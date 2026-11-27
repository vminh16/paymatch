"""Fake Clock for deterministic unit tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from gate.domain.rules import VN_TZ


class FakeClock:
    def __init__(self, initial: datetime | None = None) -> None:
        self._now = (
            initial.astimezone(VN_TZ)
            if initial is not None
            else datetime(2026, 11, 26, 8, 30, 0, tzinfo=VN_TZ)
        )

    def now(self) -> datetime:
        return self._now

    def today_vn(self) -> date:
        return self._now.astimezone(VN_TZ).date()

    def set(self, dt: datetime) -> None:
        self._now = dt.astimezone(VN_TZ)

    def advance(self, **kwargs: float) -> datetime:
        self._now = self._now + timedelta(**kwargs)
        return self._now

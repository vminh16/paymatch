"""Fake adapters for fast unit/API tests."""

from gate.adapters.fakes.clock import FakeClock
from gate.adapters.fakes.rail import FakePaymentRail
from gate.adapters.fakes.store import InMemoryCoreReadStore, InMemoryLedgerStore

__all__ = [
    "FakeClock",
    "FakePaymentRail",
    "InMemoryCoreReadStore",
    "InMemoryLedgerStore",
]

"""Pytest configuration for payment-gate tests."""

from __future__ import annotations

import pathlib
import sys

import pytest

_TESTS_DIR = str(pathlib.Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "db: tests requiring Postgres 16 via testcontainers")

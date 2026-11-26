"""Pytest configuration for agent-runtime tests (allows importing local test helpers cleanly)."""

from __future__ import annotations

import pathlib
import sys

_TESTS_DIR = str(pathlib.Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

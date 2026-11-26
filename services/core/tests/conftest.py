"""Shared pytest fixtures for core unit and Postgres 16 testcontainers DB tests."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.rows import dict_row

from core.persistence.db import Database
from core.persistence.migrator import apply_migrations
from core.persistence.seeder import load_core_seed
from core.shared.clock import FixedClock

VN_TZ = timezone(timedelta(hours=7))
DEMO_SEED_DIR = (
    pathlib.Path(__file__).resolve().parents[3]
    / "services"
    / "sim-world"
    / "data"
    / "demo"
    / "core_seed"
)
DEMO_DATA_DIR = pathlib.Path(__file__).resolve().parents[3] / "services" / "sim-world" / "data" / "demo"

TENANT_A = "ten_01M88D3C06B97Y4G0S9W8BVKNG"
TENANT_B = "ten_01M88AXX2KPMD46VQQTDDH040J"
OWNER_A = "usr_01M885AXP309SER6BAC46N5FJT"
ACCOUNTANT_A = "usr_01M88KDM92WAXYR1VPJ05VGKVV"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "db: Postgres 16 testcontainers integration tests")


@pytest.fixture(scope="session")
def pg_dsn() -> Iterator[str]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        # testcontainers returns postgresql+psycopg2://... — normalize to psycopg3 postgresql://
        dsn = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        with psycopg.connect(dsn) as conn:
            apply_migrations(conn)
        yield dsn


@pytest.fixture()
def seeded_db(pg_dsn: str) -> Database:
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        load_core_seed(conn, seed_dir=DEMO_SEED_DIR, reset=True)
    return Database(pg_dsn)


@pytest.fixture()
def fixed_clock() -> FixedClock:
    return FixedClock(datetime(2026, 11, 26, 9, 0, 0, tzinfo=VN_TZ))

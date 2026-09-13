"""Fixtures for migreringstester som krever en ekte PostgreSQL-instans.

Testene kjøres bare når PRISLAPP_POSTGRES_TEST_URL peker på en disponibel
PostgreSQL 16. SQLite-testene dekker ikke låser, Decimal i SQL eller reell migrering.
"""

import os
import uuid
from collections.abc import Iterator

import pytest
from postgres_helpers import POSTGRES_URL_ENV, execute
from sqlalchemy import make_url


@pytest.fixture(scope="session")
def postgres_admin_url() -> str:
    url = os.getenv(POSTGRES_URL_ENV)
    if not url:
        pytest.skip(f"Krever {POSTGRES_URL_ENV} mot en disponibel PostgreSQL-instans")
    return url


@pytest.fixture
def postgres_url(postgres_admin_url: str) -> Iterator[str]:
    """Tom, isolert database per test."""
    database = f"prislapp_mig_{uuid.uuid4().hex[:12]}"
    execute(postgres_admin_url, [f'CREATE DATABASE "{database}"'], autocommit=True)
    try:
        yield (
            make_url(postgres_admin_url)
            .set(database=database)
            .render_as_string(hide_password=False)
        )
    finally:
        execute(
            postgres_admin_url,
            [f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'],
            autocommit=True,
        )

"""Hjelpefunksjoner for migreringstester mot en ekte PostgreSQL-instans."""

import asyncio
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401  (fyller Base.metadata)
from app.database import Base

BACKEND_DIR = Path(__file__).resolve().parents[2]
POSTGRES_URL_ENV = "PRISLAPP_POSTGRES_TEST_URL"
SCHEMA_DIFFERENCE_KINDS = frozenset(
    {"add_table", "remove_table", "add_column", "remove_column"}
)


def execute(url: str, statements: Sequence[str], autocommit: bool = False) -> None:
    async def run() -> None:
        engine = create_async_engine(
            url,
            poolclass=NullPool,
            isolation_level="AUTOCOMMIT" if autocommit else "READ COMMITTED",
        )
        try:
            async with engine.connect() as conn:
                for statement in statements:
                    await conn.execute(text(statement))
                if not autocommit:
                    await conn.commit()
        finally:
            await engine.dispose()

    asyncio.run(run())


def fetch_all(url: str, statement: str) -> list[tuple[Any, ...]]:
    async def run() -> list[tuple[Any, ...]]:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text(statement))
                return [tuple(row) for row in result.all()]
        finally:
            await engine.dispose()

    return asyncio.run(run())


def fetch_scalar(url: str, statement: str) -> Any:
    rows = fetch_all(url, statement)
    assert len(rows) == 1, f"forventet én rad fra {statement!r}, fikk {rows!r}"
    return rows[0][0]


def table_names(url: str) -> list[str]:
    rows = fetch_all(
        url,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename",
    )
    return [row[0] for row in rows]


def create_all_schema(url: str) -> None:
    """Bootstrap skjemaet slik create_all() gjør det, uten Alembic-versjonstabell."""

    async def run() -> None:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    asyncio.run(run())


def metadata_differences(url: str) -> list[Any]:
    """Tabell-/kolonneforskjeller mellom databasen og modellene."""

    def compare(connection) -> list[Any]:
        context = MigrationContext.configure(connection)
        differences: list[Any] = []
        for difference in compare_metadata(context, Base.metadata):
            # Endringer på samme tabell kan komme gruppert i en liste.
            differences.extend(
                difference if isinstance(difference, list) else [difference]
            )
        return [
            difference
            for difference in differences
            if difference[0] in SCHEMA_DIFFERENCE_KINDS
        ]

    async def run() -> list[Any]:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(compare)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def run_backend(
    arguments: Sequence[str],
    url: str,
    timeout: float = 180,
) -> subprocess.CompletedProcess:
    """Kjør en backend-kommando mot `url` slik produksjonsoppstart gjør det."""
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def start_backend(arguments: Sequence[str], url: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, *arguments],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def run_migrations_cli(url: str, timeout: float = 180) -> subprocess.CompletedProcess:
    return run_backend(["-m", "scripts.run_migrations"], url, timeout=timeout)


def alembic_upgrade(url: str, revision: str) -> None:
    result = run_backend(["-m", "alembic", "upgrade", revision], url)
    assert result.returncode == 0, result.stdout + result.stderr

#!/usr/bin/env python3
"""Apply Alembic migrations safely on databases bootstrapped via create_all()."""

from __future__ import annotations

import asyncio
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.database import engine


async def _table_exists(table_name: str) -> bool:
    async with engine.connect() as conn:
        return await conn.run_sync(
            lambda connection: inspect(connection).has_table(table_name),
        )


async def _alembic_revision() -> str | None:
    if not await _table_exists("alembic_version"):
        return None

    query = text("SELECT version_num FROM alembic_version LIMIT 1")
    async with engine.connect() as conn:
        result = await conn.execute(query)
        row = result.first()
        return row[0] if row else None


async def _detect_schema_revision() -> str | None:
    if await _table_exists("price_observations"):
        return "003"
    if await _table_exists("receipts"):
        return "002"
    if await _table_exists("users"):
        return "001"
    return None


async def _stamp_revision(revision: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS alembic_version (
                    version_num VARCHAR(32) NOT NULL,
                    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                )
                """
            ),
        )
        await conn.execute(text("DELETE FROM alembic_version"))
        await conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )


async def prepare_migrations() -> None:
    current_revision = await _alembic_revision()
    if current_revision is not None:
        return

    detected_revision = await _detect_schema_revision()
    if detected_revision is None:
        return

    await _stamp_revision(detected_revision)
    print(
        f"Stamped existing schema to Alembic revision {detected_revision}",
        file=sys.stderr,
    )


def main() -> None:
    asyncio.run(prepare_migrations())
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    main()

import asyncio

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import Base
from scripts import run_migrations


@pytest.fixture
async def migration_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_prepare_migrations_stamps_existing_schema(migration_engine, monkeypatch):
    monkeypatch.setattr(run_migrations, "engine", migration_engine)

    await run_migrations.prepare_migrations()

    async with migration_engine.connect() as conn:
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        assert result.scalar_one() == "003"


@pytest.mark.asyncio
async def test_prepare_migrations_leaves_fresh_db_unstamped(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(run_migrations, "engine", engine)

    await run_migrations.prepare_migrations()

    async with engine.connect() as conn:
        has_version_table = await conn.run_sync(
            lambda connection: inspect(connection).has_table("alembic_version"),
        )
        assert has_version_table is False

    await engine.dispose()

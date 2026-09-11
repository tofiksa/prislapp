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


@pytest.fixture
async def empty_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    yield engine
    await engine.dispose()


async def _stamped_revision(engine) -> str | None:
    async with engine.connect() as conn:
        has_version_table = await conn.run_sync(
            lambda connection: inspect(connection).has_table("alembic_version"),
        )
        if not has_version_table:
            return None
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        return result.scalar_one()


def test_every_migration_script_is_declared_for_detection():
    declared = {revision.revision for revision in run_migrations.SCHEMA_REVISIONS}
    declared |= set(run_migrations.DATA_ONLY_REVISIONS)

    assert set(run_migrations.migration_revisions()) == declared


def test_data_only_revisions_after_the_stamped_one_are_reapplied():
    newest_schema_revision = run_migrations.SCHEMA_REVISIONS[-1].revision

    assert run_migrations.reapplied_data_revisions(newest_schema_revision) == ("004",)


@pytest.mark.asyncio
async def test_prepare_migrations_stamps_newest_verifiable_schema_revision(
    migration_engine, monkeypatch
):
    monkeypatch.setattr(run_migrations, "engine", migration_engine)

    await run_migrations.prepare_migrations()

    assert await _stamped_revision(migration_engine) == (
        run_migrations.SCHEMA_REVISIONS[-1].revision
    )


@pytest.mark.asyncio
async def test_prepare_migrations_leaves_fresh_db_unstamped(empty_engine, monkeypatch):
    monkeypatch.setattr(run_migrations, "engine", empty_engine)

    await run_migrations.prepare_migrations()

    assert await _stamped_revision(empty_engine) is None


@pytest.mark.asyncio
async def test_prepare_migrations_refuses_partially_created_revision(
    empty_engine, monkeypatch
):
    monkeypatch.setattr(run_migrations, "engine", empty_engine)
    async with empty_engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE users (
                    id CHAR(32) NOT NULL PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    created_at DATETIME
                )
                """
            ),
        )

    with pytest.raises(run_migrations.MigrationStateError, match="users.password_hash"):
        await run_migrations.prepare_migrations()

    assert await _stamped_revision(empty_engine) is None


@pytest.mark.asyncio
async def test_prepare_migrations_refuses_newer_schema_without_older_revision(
    empty_engine, monkeypatch
):
    monkeypatch.setattr(run_migrations, "engine", empty_engine)
    tables = [
        Base.metadata.tables[name]
        for name in ("products", "product_aliases", "price_observations")
    ]
    async with empty_engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    with pytest.raises(run_migrations.MigrationStateError, match="003"):
        await run_migrations.prepare_migrations()

    assert await _stamped_revision(empty_engine) is None


@pytest.mark.asyncio
async def test_prepare_migrations_refuses_undeclared_migration_script(
    migration_engine, monkeypatch
):
    monkeypatch.setattr(run_migrations, "engine", migration_engine)
    monkeypatch.setattr(run_migrations, "DATA_ONLY_REVISIONS", frozenset())

    with pytest.raises(run_migrations.MigrationStateError, match="004"):
        await run_migrations.prepare_migrations()

    assert await _stamped_revision(migration_engine) is None

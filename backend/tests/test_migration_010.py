"""S10-B: migrering 010 legger til job_outbox og users.deleted_at uten å røre 009."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import run_migrations

BACKEND_DIR = Path(__file__).resolve().parents[1]

NEW_TABLES = ("job_outbox",)
OUTBOX_COLUMNS = (
    "id",
    "user_id",
    "aggregate_type",
    "aggregate_id",
    "job_type",
    "payload",
    "status",
    "attempt_id",
    "lease_expires_at",
    "attempt_count",
    "last_error_code",
    "created_at",
    "published_at",
)


def _alembic(database: Path, *arguments: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database}"},
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _query(database: Path, statement: str, parameters: tuple = ()) -> list[tuple]:
    with sqlite3.connect(database) as connection:
        return list(connection.execute(statement, parameters))


def _tables(database: Path) -> set[str]:
    return {
        row[0]
        for row in _query(database, "SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _columns(database: Path, table: str) -> set[str]:
    return {row[1] for row in _query(database, f"PRAGMA table_info({table})")}


def test_010_is_head_and_declared_for_schema_verification():
    assert run_migrations.migration_revisions()[-1] == "010"
    declared = {revision.revision for revision in run_migrations.SCHEMA_REVISIONS}
    assert "010" in declared


def test_upgrade_creates_job_outbox_and_user_deleted_at(tmp_path: Path):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "head")

    assert set(NEW_TABLES) <= _tables(database)
    assert set(OUTBOX_COLUMNS) <= _columns(database, "job_outbox")
    assert "deleted_at" in _columns(database, "users")


def test_downgrade_removes_outbox_and_keeps_auth_sessions(tmp_path: Path):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "010")
    _alembic(database, "downgrade", "009")

    assert set(NEW_TABLES).isdisjoint(_tables(database))
    assert "deleted_at" not in _columns(database, "users")
    assert "refresh_sessions" in _tables(database)
    assert "password_reset_tokens" in _tables(database)


@pytest.mark.asyncio
async def test_detection_recognises_009_before_outbox_tables(
    tmp_path: Path,
    monkeypatch,
):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "009")
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    monkeypatch.setattr(run_migrations, "engine", engine)

    try:
        assert await run_migrations.detect_schema_revision() == "009"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_detection_verifies_outbox_after_the_upgrade(
    tmp_path: Path,
    monkeypatch,
):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "010")
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    monkeypatch.setattr(run_migrations, "engine", engine)

    try:
        assert await run_migrations.detect_schema_revision() == "010"
    finally:
        await engine.dispose()

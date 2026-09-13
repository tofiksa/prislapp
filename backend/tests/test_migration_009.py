"""S09-A: migrering 009 legger til refresh-sesjoner og reset-tokens uten å røre 008."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import run_migrations

BACKEND_DIR = Path(__file__).resolve().parents[1]

NEW_TABLES = ("refresh_sessions", "password_reset_tokens")
REFRESH_COLUMNS = (
    "id",
    "user_id",
    "token_hash",
    "family_id",
    "revoked_at",
    "replaced_by",
    "expires_at",
)
RESET_COLUMNS = ("id", "user_id", "token_hash", "expires_at", "used_at")


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


def test_009_is_declared_for_schema_verification():
    revisions = run_migrations.migration_revisions()
    assert "009" in revisions
    assert revisions[revisions.index("009") + 1] == "010"
    declared = {revision.revision for revision in run_migrations.SCHEMA_REVISIONS}
    assert "009" in declared


def test_upgrade_creates_auth_session_tables(tmp_path: Path):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "head")

    assert set(NEW_TABLES) <= _tables(database)
    assert set(REFRESH_COLUMNS) <= _columns(database, "refresh_sessions")
    assert set(RESET_COLUMNS) <= _columns(database, "password_reset_tokens")


def test_downgrade_removes_auth_session_tables_and_keeps_lists(tmp_path: Path):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "009")
    _alembic(database, "downgrade", "008")

    assert set(NEW_TABLES).isdisjoint(_tables(database))
    assert "shopping_lists" in _tables(database)


@pytest.mark.asyncio
async def test_detection_recognises_008_before_auth_session_tables(
    tmp_path: Path,
    monkeypatch,
):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "008")
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    monkeypatch.setattr(run_migrations, "engine", engine)

    try:
        assert await run_migrations.detect_schema_revision() == "008"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_detection_verifies_auth_session_tables_after_the_upgrade(
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


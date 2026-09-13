"""S02-C: migrering 011 legger payload_hash og bildemetadata på receipts uten å røre 010."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import run_migrations

BACKEND_DIR = Path(__file__).resolve().parents[1]

RECEIPT_COLUMNS = ("payload_hash", "image_width", "image_height", "content_type")


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


def test_011_is_declared_for_schema_verification():
    declared = {revision.revision for revision in run_migrations.SCHEMA_REVISIONS}
    assert "011" in declared


def test_upgrade_adds_payload_hash_and_image_metadata(tmp_path: Path):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "head")

    assert set(RECEIPT_COLUMNS) <= _columns(database, "receipts")
    assert "job_outbox" in _tables(database)


def test_downgrade_removes_new_columns_and_keeps_outbox(tmp_path: Path):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "011")
    _alembic(database, "downgrade", "010")

    assert set(RECEIPT_COLUMNS).isdisjoint(_columns(database, "receipts"))
    assert "job_outbox" in _tables(database)
    assert "deleted_at" in _columns(database, "users")


@pytest.mark.asyncio
async def test_detection_recognises_010_before_payload_hash(
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


@pytest.mark.asyncio
async def test_detection_verifies_payload_hash_after_the_upgrade(
    tmp_path: Path,
    monkeypatch,
):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "011")
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    monkeypatch.setattr(run_migrations, "engine", engine)

    try:
        assert await run_migrations.detect_schema_revision() == "011"
    finally:
        await engine.dispose()

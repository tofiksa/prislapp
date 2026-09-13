"""S02-D: migrering 012 legger OCR-ekstraksjonsmetadata på receipts."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import run_migrations

BACKEND_DIR = Path(__file__).resolve().parents[1]
OCR_COLUMNS = ("ocr_extraction_json", "ocr_quality", "ocr_pipeline_version")


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


def _columns(database: Path, table: str) -> set[str]:
    with sqlite3.connect(database) as connection:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def test_012_is_head_and_declared():
    assert run_migrations.migration_revisions()[-1] == "012"
    declared = {revision.revision for revision in run_migrations.SCHEMA_REVISIONS}
    assert "012" in declared


def test_upgrade_adds_ocr_metadata_columns(tmp_path: Path):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "head")
    assert set(OCR_COLUMNS) <= _columns(database, "receipts")


def test_downgrade_removes_ocr_metadata_columns(tmp_path: Path):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "012")
    _alembic(database, "downgrade", "011")
    assert set(OCR_COLUMNS).isdisjoint(_columns(database, "receipts"))


@pytest.mark.asyncio
async def test_detection_verifies_ocr_metadata_after_upgrade(tmp_path: Path, monkeypatch):
    database = tmp_path / "prislapp.db"
    _alembic(database, "upgrade", "012")
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    monkeypatch.setattr(run_migrations, "engine", engine)
    try:
        assert await run_migrations.detect_schema_revision() == "012"
    finally:
        await engine.dispose()

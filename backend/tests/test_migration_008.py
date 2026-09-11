"""S06-A: migrering 008 legger til handlelister uten å røre kvitteringslaget.

SQLite beviser ikke låser eller Decimal-presisjon i SQL, men viser at
oppgraderingen er additiv, at slettemarkørene finnes, og at listetabellene ikke
fylles med noe backfill.
"""

import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import run_migrations

BACKEND_DIR = Path(__file__).resolve().parents[1]

NEW_TABLES = (
    "shopping_lists",
    "shopping_list_items",
    "shopping_list_mutations",
    "shopping_list_sync_state",
)
PRESERVED_TABLES = (
    "receipts",
    "receipt_items",
    "receipt_revisions",
    "receipt_mutations",
    "price_observations",
    "price_observations_v2",
    "user_products",
    "account_ledgers",
)


@pytest.fixture
def sqlite_database(tmp_path: Path) -> Path:
    return tmp_path / "prislapp.db"


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


def _seed_user(database: Path) -> str:
    user_id = uuid.uuid4().hex
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, 'hash')",
            (user_id, f"{user_id}@example.com"),
        )
    return user_id


def test_008_is_in_the_chain_and_declared_for_schema_verification():
    assert "008" in run_migrations.migration_revisions()
    declared = {revision.revision for revision in run_migrations.SCHEMA_REVISIONS}
    assert "008" in declared


def test_upgrade_creates_the_shopping_list_tables(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "head")

    assert set(NEW_TABLES) <= _tables(sqlite_database)


def test_the_list_and_line_carry_a_tombstone_and_a_version(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "head")

    assert {"version", "content_seq", "deleted_at", "status"} <= _columns(
        sqlite_database,
        "shopping_lists",
    )
    assert {
        "user_product_id",
        "free_text",
        "quantity",
        "quantity_unit",
        "checked",
        "position",
        "version",
        "sync_seq",
        "deleted_at",
    } <= _columns(sqlite_database, "shopping_list_items")


_MUTATION_INSERT = (
    "INSERT INTO shopping_list_mutations (id, user_id, operation, mutation_id, "
    "payload_hash, response) VALUES (?, ?, ?, ?, 'hash', '{}')"
)


def _insert_mutation(database: Path, user_id: str, operation: str, mutation_id: str) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            _MUTATION_INSERT,
            (uuid.uuid4().hex, user_id, operation, mutation_id),
        )


def test_the_same_mutation_key_cannot_be_stored_twice(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "head")
    user_id = _seed_user(sqlite_database)
    mutation_id = uuid.uuid4().hex
    _insert_mutation(sqlite_database, user_id, "list_create", mutation_id)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_mutation(sqlite_database, user_id, "list_create", mutation_id)


def test_the_same_mutation_id_is_free_for_another_operation(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "head")
    user_id = _seed_user(sqlite_database)
    mutation_id = uuid.uuid4().hex
    _insert_mutation(sqlite_database, user_id, "list_create", mutation_id)

    _insert_mutation(sqlite_database, user_id, "item_create", mutation_id)

    assert _query(sqlite_database, "SELECT COUNT(*) FROM shopping_list_mutations") == [(2,)]


def test_the_receipt_layer_is_untouched(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "head")

    assert set(PRESERVED_TABLES) <= _tables(sqlite_database)
    assert "version" in _columns(sqlite_database, "receipts")
    assert {"unit_price", "line_total"} <= _columns(sqlite_database, "receipt_items")


def test_an_existing_account_gets_no_list_from_the_migration(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "007")
    _seed_user(sqlite_database)

    _alembic(sqlite_database, "upgrade", "008")

    assert _query(sqlite_database, "SELECT COUNT(*) FROM shopping_lists") == [(0,)]
    assert _query(sqlite_database, "SELECT COUNT(*) FROM shopping_list_sync_state") == [(0,)]


def test_downgrade_removes_the_list_tables_and_keeps_the_receipts(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "008")

    _alembic(sqlite_database, "downgrade", "007")

    assert set(NEW_TABLES).isdisjoint(_tables(sqlite_database))
    assert set(PRESERVED_TABLES) <= _tables(sqlite_database)


@pytest.mark.asyncio
async def test_detection_recognises_007_before_the_list_tables(
    sqlite_database: Path,
    monkeypatch,
):
    _alembic(sqlite_database, "upgrade", "007")
    engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_database}")
    monkeypatch.setattr(run_migrations, "engine", engine)

    try:
        assert await run_migrations.detect_schema_revision() == "007"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_detection_verifies_the_list_tables_after_the_upgrade(
    sqlite_database: Path,
    monkeypatch,
):
    _alembic(sqlite_database, "upgrade", "008")
    engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_database}")
    monkeypatch.setattr(run_migrations, "engine", engine)

    try:
        assert await run_migrations.detect_schema_revision() == "008"
    finally:
        await engine.dispose()

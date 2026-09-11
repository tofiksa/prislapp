"""S05-A: migrering 007 legger til revisjoner uten å slette v1-linjer.

SQLite beviser ikke låser eller Decimal-presisjon i SQL, men viser at
oppgraderingen er additiv, at bekreftede kvitteringer får revisjon 1 som
gjeldende, og at backfillen ikke gjetter enhet, identitet eller dato.
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
    "receipt_revisions",
    "receipt_revision_lines",
    "price_observations_v2",
    "receipt_mutations",
)
PRESERVED_ITEM_COLUMNS = ("unit_price", "line_total", "net_line_total")


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


def _seed_receipt(
    database: Path,
    *,
    status: str = "CONFIRMED",
    purchase_date: str | None = "2026-09-01 10:00:00.000000",
    total: str | None = "25.00",
) -> dict[str, str]:
    ids = {"user": uuid.uuid4().hex, "store": uuid.uuid4().hex, "receipt": uuid.uuid4().hex}
    ids["item"] = uuid.uuid4().hex
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, 'hash')",
            (ids["user"], f"{ids['user']}@example.com"),
        )
        connection.execute(
            "INSERT INTO stores (id, name, normalized_name, chain) "
            "VALUES (?, 'Rema 1000 Torshov', 'rema 1000 torshov', 'rema1000')",
            (ids["store"],),
        )
        connection.execute(
            "INSERT INTO receipts (id, user_id, store_id, purchase_date, total, status, "
            "image_path, image_expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, "
            "'eier/kvittering.jpg', '2026-10-01 10:00:00.000000', "
            "'2026-09-11 08:00:00.000000')",
            (ids["receipt"], ids["user"], ids["store"], purchase_date, total, status),
        )
        connection.execute(
            "INSERT INTO receipt_items (id, receipt_id, raw_product_name, quantity, "
            "unit_price, line_total) VALUES (?, ?, 'MELK LETT 1L', 1.0, 25.00, 25.00)",
            (ids["item"], ids["receipt"]),
        )
    return ids


def test_007_is_head_and_declared_for_schema_verification():
    assert run_migrations.migration_revisions()[-1] == "007"
    declared = {revision.revision for revision in run_migrations.SCHEMA_REVISIONS}
    assert "007" in declared


def test_upgrade_adds_the_revision_tables_and_the_receipt_version(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "head")

    assert set(NEW_TABLES) <= _tables(sqlite_database)
    assert "version" in _columns(sqlite_database, "receipts")
    assert set(PRESERVED_ITEM_COLUMNS) <= _columns(sqlite_database, "receipt_items")


def test_confirmed_receipt_gets_revision_one_as_current(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "006")
    ids = _seed_receipt(sqlite_database)

    _alembic(sqlite_database, "upgrade", "007")

    assert _query(sqlite_database, "SELECT version FROM receipts") == [(1,)]
    assert _query(
        sqlite_database,
        "SELECT revision, status, operation FROM receipt_revisions WHERE receipt_id = ?",
        (ids["receipt"],),
    ) == [(1, "confirmed", "receipt_confirm")]


def test_unconfirmed_receipt_gets_no_revision(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "006")
    _seed_receipt(sqlite_database, status="READY_FOR_REVIEW")

    _alembic(sqlite_database, "upgrade", "007")

    assert _query(sqlite_database, "SELECT version FROM receipts") == [(0,)]
    assert _query(sqlite_database, "SELECT COUNT(*) FROM receipt_revisions") == [(0,)]


def test_backfill_keeps_the_v1_lines_and_reuses_their_ids(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "006")
    ids = _seed_receipt(sqlite_database)

    _alembic(sqlite_database, "upgrade", "007")

    assert _query(sqlite_database, "SELECT COUNT(*) FROM receipt_items") == [(1,)]
    assert _query(
        sqlite_database,
        "SELECT line_id, position, raw_product_name FROM receipt_revision_lines",
    ) == [(ids["item"], 0, "MELK LETT 1L")]


def test_backfilled_line_is_not_rankable_because_the_unit_is_unknown(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "006")
    _seed_receipt(sqlite_database)

    _alembic(sqlite_database, "upgrade", "007")

    rows = _query(
        sqlite_database,
        "SELECT eligible, eligible_for_dated_ranking, comparison_price, exclusion_reasons "
        "FROM receipt_revision_lines",
    )
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    assert rows[0][2] is None
    assert "unknown_unit" in rows[0][3]
    assert _query(sqlite_database, "SELECT COUNT(*) FROM price_observations_v2") == [(0,)]


def test_backfilled_revision_is_not_claimed_to_be_reconciled(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "006")
    _seed_receipt(sqlite_database)

    _alembic(sqlite_database, "upgrade", "007")

    assert _query(
        sqlite_database,
        "SELECT reconciliation_status, reconciliation_reason, gap_accepted "
        "FROM receipt_revisions",
    ) == [("unverifiable", "legacy_confirmation", 0)]


def test_undated_confirmed_receipt_keeps_an_unknown_revision_date(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "006")
    _seed_receipt(sqlite_database, purchase_date=None)

    _alembic(sqlite_database, "upgrade", "007")

    assert _query(
        sqlite_database,
        "SELECT purchase_date, purchase_time, date_precision FROM receipt_revisions",
    ) == [(None, None, "unknown")]


def test_dated_receipt_copies_the_date_without_adding_a_time(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "006")
    _seed_receipt(sqlite_database)

    _alembic(sqlite_database, "upgrade", "007")

    assert _query(
        sqlite_database,
        "SELECT purchase_date, purchase_time, date_precision FROM receipt_revisions",
    ) == [("2026-09-01", None, "date")]


def test_rerunning_the_backfill_does_not_duplicate_revisions(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "006")
    _seed_receipt(sqlite_database)
    _alembic(sqlite_database, "upgrade", "007")

    _alembic(sqlite_database, "downgrade", "006")
    _alembic(sqlite_database, "upgrade", "007")

    assert _query(sqlite_database, "SELECT COUNT(*) FROM receipt_revisions") == [(1,)]


def test_downgrade_removes_the_new_tables_and_keeps_the_raw_lines(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "007")
    _seed_receipt(sqlite_database)

    _alembic(sqlite_database, "downgrade", "006")

    assert set(NEW_TABLES).isdisjoint(_tables(sqlite_database))
    assert "version" not in _columns(sqlite_database, "receipts")
    assert _query(sqlite_database, "SELECT line_total FROM receipt_items") == [(25.00,)]


@pytest.mark.asyncio
async def test_detection_recognises_006_before_the_revision_tables(
    sqlite_database: Path, monkeypatch
):
    _alembic(sqlite_database, "upgrade", "006")
    engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_database}")
    monkeypatch.setattr(run_migrations, "engine", engine)

    try:
        assert await run_migrations.detect_schema_revision() == "006"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_detection_verifies_the_revision_tables_after_the_upgrade(
    sqlite_database: Path, monkeypatch
):
    _alembic(sqlite_database, "upgrade", "007")
    engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_database}")
    monkeypatch.setattr(run_migrations, "engine", engine)

    try:
        assert await run_migrations.detect_schema_revision() == "007"
    finally:
        await engine.dispose()

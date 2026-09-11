"""S04-A: migrering 006 legger til kolonner uten å gjette verdier for gamle rader.

SQLite beviser ikke Decimal-presisjon i SQL eller samtidig migrering, men viser at
oppgraderingen er additiv og at ukjente felter forblir `unknown` og null.
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

RECEIPT_COLUMNS = ("purchase_time", "date_precision", "date_source")
RECEIPT_ITEM_COLUMNS = (
    "line_type",
    "net_line_total",
    "printed_unit_price",
    "quantity_unit",
    "price_basis",
    "condition",
)
PRESERVED_ITEM_COLUMNS = ("unit_price", "line_total")


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


def _columns(database: Path, table: str) -> set[str]:
    return {row[1] for row in _query(database, f"PRAGMA table_info({table})")}


def _seed_receipt(
    database: Path,
    *,
    purchase_date: str | None,
    status: str = "CONFIRMED",
    lines: tuple[tuple[str, float, float | None], ...] = (("MELK LETT 1L", 25.00, 25.00),),
) -> dict[str, str]:
    """En kvittering med linjer som `(navn, line_total, unit_price)`."""
    ids = {"user": uuid.uuid4().hex, "store": uuid.uuid4().hex, "receipt": uuid.uuid4().hex}
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, 'hash')",
            (ids["user"], f"{ids['user']}@example.com"),
        )
        connection.execute(
            "INSERT INTO stores (id, name, normalized_name, chain) "
            "VALUES (?, 'Rema 1000 Grunerlokka', 'rema 1000 grunerlokka', 'Rema 1000')",
            (ids["store"],),
        )
        connection.execute(
            "INSERT INTO receipts (id, user_id, store_id, purchase_date, total, status, "
            "image_path, image_expires_at, created_at) VALUES (?, ?, ?, ?, 50.00, ?, "
            "'eier/kvittering.jpg', '2026-10-01 10:00:00.000000', "
            "'2026-09-11 08:00:00.000000')",
            (ids["receipt"], ids["user"], ids["store"], purchase_date, status),
        )
        for index, (name, line_total, unit_price) in enumerate(lines):
            item_id = uuid.uuid4().hex
            ids[f"item{index}"] = item_id
            connection.execute(
                "INSERT INTO receipt_items (id, receipt_id, raw_product_name, quantity, "
                "unit_price, line_total) VALUES (?, ?, ?, 1.0, ?, ?)",
                (item_id, ids["receipt"], name, unit_price, line_total),
            )
    return ids


def test_006_is_head_and_declared_for_schema_verification():
    assert run_migrations.migration_revisions()[-1] == "006"
    declared = {revision.revision for revision in run_migrations.SCHEMA_REVISIONS}
    assert "006" in declared


def test_upgrade_adds_the_new_columns_without_dropping_the_old_ones(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "head")

    assert set(RECEIPT_COLUMNS) <= _columns(sqlite_database, "receipts")
    item_columns = _columns(sqlite_database, "receipt_items")
    assert set(RECEIPT_ITEM_COLUMNS) <= item_columns
    assert set(PRESERVED_ITEM_COLUMNS) <= item_columns


def test_existing_line_gets_unknown_unit_and_type_instead_of_a_guess(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "005")
    _seed_receipt(sqlite_database, purchase_date="2026-09-01 10:00:00.000000")

    _alembic(sqlite_database, "upgrade", "006")

    rows = _query(
        sqlite_database,
        "SELECT quantity_unit, line_type, price_basis, condition FROM receipt_items",
    )
    assert rows == [("unknown", "unknown", "unknown", "unknown")]


def test_receipt_without_purchase_date_is_not_dated_by_the_upgrade(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "005")
    _seed_receipt(sqlite_database, purchase_date=None)

    _alembic(sqlite_database, "upgrade", "006")

    rows = _query(
        sqlite_database,
        "SELECT purchase_date, purchase_time, date_precision, date_source FROM receipts",
    )
    assert rows == [(None, None, "unknown", "unknown")]


def test_known_date_is_not_upgraded_to_a_certain_time(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "005")
    _seed_receipt(sqlite_database, purchase_date="2026-09-01 00:00:00.000000")

    _alembic(sqlite_database, "upgrade", "006")

    rows = _query(
        sqlite_database,
        "SELECT purchase_time, date_precision, date_source FROM receipts",
    )
    assert rows == [(None, "date", "unknown")]


def test_confirmed_line_without_discount_line_gets_net_line_total(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "005")
    _seed_receipt(sqlite_database, purchase_date="2026-09-01 10:00:00.000000")

    _alembic(sqlite_database, "upgrade", "006")

    rows = _query(sqlite_database, "SELECT net_line_total, printed_unit_price FROM receipt_items")
    assert rows == [(25.00, 25.00)]


def test_line_sharing_a_receipt_with_a_discount_line_has_no_net_total(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "005")
    _seed_receipt(
        sqlite_database,
        purchase_date="2026-09-01 10:00:00.000000",
        lines=(("MELK LETT 1L", 40.00, 40.00), ("RABATT", -10.00, None)),
    )

    _alembic(sqlite_database, "upgrade", "006")

    rows = _query(
        sqlite_database,
        "SELECT net_line_total FROM receipt_items ORDER BY raw_product_name",
    )
    assert rows == [(None,), (None,)]


def test_line_on_an_unconfirmed_receipt_has_no_net_total(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "005")
    _seed_receipt(
        sqlite_database,
        purchase_date="2026-09-01 10:00:00.000000",
        status="READY_FOR_REVIEW",
    )

    _alembic(sqlite_database, "upgrade", "006")

    assert _query(sqlite_database, "SELECT net_line_total FROM receipt_items") == [(None,)]


def test_downgrade_removes_the_new_columns_and_keeps_the_raw_line(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "006")
    _seed_receipt(sqlite_database, purchase_date="2026-09-01 10:00:00.000000")

    _alembic(sqlite_database, "downgrade", "005")

    assert set(RECEIPT_COLUMNS).isdisjoint(_columns(sqlite_database, "receipts"))
    item_columns = _columns(sqlite_database, "receipt_items")
    assert set(RECEIPT_ITEM_COLUMNS).isdisjoint(item_columns)
    assert set(PRESERVED_ITEM_COLUMNS) <= item_columns
    assert _query(sqlite_database, "SELECT line_total FROM receipt_items") == [(25.00,)]


@pytest.mark.asyncio
async def test_detection_recognises_005_before_the_column_only_upgrade(
    sqlite_database: Path, monkeypatch
):
    _alembic(sqlite_database, "upgrade", "005")
    engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_database}")
    monkeypatch.setattr(run_migrations, "engine", engine)

    try:
        assert await run_migrations.detect_schema_revision() == "005"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_detection_verifies_the_new_columns_after_the_upgrade(
    sqlite_database: Path, monkeypatch
):
    _alembic(sqlite_database, "upgrade", "006")
    engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_database}")
    monkeypatch.setattr(run_migrations, "engine", engine)

    try:
        assert await run_migrations.detect_schema_revision() == "006"
    finally:
        await engine.dispose()

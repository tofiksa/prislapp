"""S03-A: migrering 005 er additiv og backfiller den private katalogen.

SQLite beviser ikke låser eller Decimal i SQL, men viser at Alembic-oppgraderingen
oppretter de nye tabellene uten å røre de globale.
"""

import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from scripts import run_migrations

BACKEND_DIR = Path(__file__).resolve().parents[1]
LEGACY_TABLES = ("products", "product_aliases", "price_observations", "receipts", "receipt_items")
PRIVATE_TABLES = ("user_products", "user_product_aliases", "user_stores", "account_ledgers")


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


def _table_names(database: Path) -> set[str]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {row[0] for row in rows}


def _query(database: Path, statement: str) -> list[tuple]:
    with sqlite3.connect(database) as connection:
        return list(connection.execute(statement))


def _seed_confirmed_receipt(database: Path) -> dict[str, str]:
    ids = {name: uuid.uuid4().hex for name in ("user", "store", "product", "receipt", "item")}
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, 'eier@example.com', 'hash')",
            (ids["user"],),
        )
        connection.execute(
            "INSERT INTO stores (id, name, normalized_name, chain) "
            "VALUES (?, 'Rema 1000 Grunerlokka', 'rema 1000 grunerlokka', 'Rema 1000')",
            (ids["store"],),
        )
        connection.execute(
            "INSERT INTO products (id, canonical_name) VALUES (?, 'MELK LETT 1L')",
            (ids["product"],),
        )
        connection.execute(
            "INSERT INTO receipts (id, user_id, store_id, purchase_date, total, status, "
            "image_path, image_expires_at) VALUES (?, ?, ?, '2026-09-01 10:00:00.000000', "
            "50.00, 'CONFIRMED', 'eier/kvittering.jpg', '2026-10-01 10:00:00.000000')",
            (ids["receipt"], ids["user"], ids["store"]),
        )
        connection.execute(
            "INSERT INTO receipt_items (id, receipt_id, product_id, raw_product_name, "
            "quantity, line_total) VALUES (?, ?, ?, 'MELK LETT 1L', 1.0, 25.00)",
            (ids["item"], ids["receipt"], ids["product"]),
        )
    return ids


def test_005_is_declared_for_schema_verification():
    assert "005" in run_migrations.migration_revisions()
    declared = {revision.revision for revision in run_migrations.SCHEMA_REVISIONS}
    assert "005" in declared


def test_upgrade_creates_private_tables_without_dropping_the_global_ones(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "head")

    tables = _table_names(sqlite_database)
    assert set(PRIVATE_TABLES) <= tables
    assert set(LEGACY_TABLES) <= tables


def test_downgrade_drops_only_the_new_tables(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "head")
    _seed_confirmed_receipt(sqlite_database)
    assert set(PRIVATE_TABLES) <= _table_names(sqlite_database)

    _alembic(sqlite_database, "downgrade", "004")

    tables = _table_names(sqlite_database)
    assert set(PRIVATE_TABLES).isdisjoint(tables)
    assert set(LEGACY_TABLES) <= tables
    assert _query(sqlite_database, "SELECT COUNT(*) FROM products")[0][0] == 1
    assert _query(sqlite_database, "SELECT COUNT(*) FROM receipt_items")[0][0] == 1


def test_upgrade_backfills_the_owners_confirmed_lines(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "004")
    ids = _seed_confirmed_receipt(sqlite_database)

    _alembic(sqlite_database, "upgrade", "005")

    products = _query(
        sqlite_database,
        "SELECT user_id, display_name, identity_status, purchase_count FROM user_products",
    )
    assert products == [(ids["user"], "MELK LETT 1L", "inherited", 1)]
    aliases = _query(
        sqlite_database,
        "SELECT user_id, raw_text, source, match_method FROM user_product_aliases",
    )
    assert aliases == [(ids["user"], "MELK LETT 1L", "backfill", "inherited")]
    stores = _query(sqlite_database, "SELECT user_id, identity_level FROM user_stores")
    assert stores == [(ids["user"], "chain_only")]
    ledgers = _query(sqlite_database, "SELECT user_id, price_data_version FROM account_ledgers")
    assert ledgers == [(ids["user"], 1)]


def test_upgrade_backfill_is_idempotent_when_rerun(sqlite_database: Path):
    _alembic(sqlite_database, "upgrade", "004")
    _seed_confirmed_receipt(sqlite_database)
    _alembic(sqlite_database, "upgrade", "005")

    _alembic(sqlite_database, "downgrade", "004")
    _alembic(sqlite_database, "upgrade", "005")

    assert _query(sqlite_database, "SELECT COUNT(*) FROM user_products")[0][0] == 1
    assert _query(sqlite_database, "SELECT COUNT(*) FROM user_product_aliases")[0][0] == 1

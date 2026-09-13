"""S05-A: migrering 007 mot ekte PostgreSQL, der Decimal, JSON og defaults er reelle."""

from decimal import Decimal

import pytest
from postgres_helpers import (
    alembic_upgrade,
    execute,
    fetch_all,
    fetch_scalar,
    metadata_differences,
    run_backend,
    run_migrations_cli,
    table_names,
)

pytestmark = pytest.mark.postgres

USER_ID = "11111111-1111-1111-1111-111111111111"
STORE_ID = "22222222-2222-2222-2222-222222222222"
CONFIRMED_RECEIPT_ID = "33333333-3333-3333-3333-333333333333"
REVIEW_RECEIPT_ID = "44444444-4444-4444-4444-444444444444"
CONFIRMED_ITEM_ID = "55555555-5555-5555-5555-555555555555"
REVIEW_ITEM_ID = "66666666-6666-6666-6666-666666666666"

NEW_TABLES = (
    "price_observations_v2",
    "receipt_mutations",
    "receipt_revision_lines",
    "receipt_revisions",
)


def _receipt(receipt_id: str, status: str, purchase_date: str | None) -> str:
    date_value = "NULL" if purchase_date is None else f"'{purchase_date}'"
    return (
        f"INSERT INTO receipts (id, user_id, store_id, purchase_date, total, status, "
        f"image_path, image_expires_at, created_at) VALUES ('{receipt_id}', '{USER_ID}', "
        f"'{STORE_ID}', {date_value}, 25.00, '{status}', 'receipts/p0.png', "
        f"'2026-10-01 10:00:00+00', '2026-09-11 08:00:00+00')"
    )


def _item(item_id: str, receipt_id: str) -> str:
    return (
        f"INSERT INTO receipt_items (id, receipt_id, raw_product_name, quantity, "
        f"unit_price, line_total) VALUES ('{item_id}', '{receipt_id}', 'MELK LETT 1L', "
        f"1.000, 25.00, 25.00)"
    )


SEED = (
    f"INSERT INTO users (id, email, password_hash) "
    f"VALUES ('{USER_ID}', 'p0@example.com', 'hash')",
    f"INSERT INTO stores (id, name, normalized_name, chain) "
    f"VALUES ('{STORE_ID}', 'Rema 1000 Torshov', 'rema 1000 torshov', 'rema1000')",
    _receipt(CONFIRMED_RECEIPT_ID, "CONFIRMED", "2026-09-01 00:00:00+00"),
    _receipt(REVIEW_RECEIPT_ID, "READY_FOR_REVIEW", "2026-09-02 00:00:00+00"),
    _item(CONFIRMED_ITEM_ID, CONFIRMED_RECEIPT_ID),
    _item(REVIEW_ITEM_ID, REVIEW_RECEIPT_ID),
)


@pytest.fixture
def upgraded_database(postgres_url: str) -> str:
    """Data som fins før 006, slik at 006 rekker å sette `net_line_total`."""
    alembic_upgrade(postgres_url, "005")
    execute(postgres_url, list(SEED))
    alembic_upgrade(postgres_url, "007")
    return postgres_url


def test_upgrade_creates_the_revision_tables(upgraded_database: str):
    assert set(NEW_TABLES) <= set(table_names(upgraded_database))


def test_confirmed_receipt_gets_revision_one_as_current(upgraded_database: str):
    rows = fetch_all(
        upgraded_database,
        "SELECT r.version, v.revision, v.status, v.operation FROM receipts r "
        "JOIN receipt_revisions v ON v.receipt_id = r.id "
        f"WHERE r.id = '{CONFIRMED_RECEIPT_ID}'",
    )

    assert rows == [(1, 1, "confirmed", "receipt_confirm")]


def test_receipt_under_review_gets_no_revision(upgraded_database: str):
    assert fetch_scalar(
        upgraded_database,
        f"SELECT version FROM receipts WHERE id = '{REVIEW_RECEIPT_ID}'",
    ) == 0
    assert fetch_scalar(
        upgraded_database,
        "SELECT COUNT(*) FROM receipt_revisions WHERE receipt_id = "
        f"'{REVIEW_RECEIPT_ID}'",
    ) == 0


def test_backfill_keeps_the_v1_lines_and_their_ids(upgraded_database: str):
    assert fetch_scalar(upgraded_database, "SELECT COUNT(*) FROM receipt_items") == 2
    rows = fetch_all(
        upgraded_database,
        "SELECT line_id::text, position, net_line_total FROM receipt_revision_lines",
    )

    assert rows == [(CONFIRMED_ITEM_ID, 0, Decimal("25.00"))]


def test_backfilled_line_is_not_rankable_and_publishes_no_price(upgraded_database: str):
    rows = fetch_all(
        upgraded_database,
        "SELECT eligible, eligible_for_dated_ranking, comparison_price, currency, "
        "exclusion_reasons FROM receipt_revision_lines",
    )

    assert rows[0][:4] == (False, False, None, None)
    assert "unknown_unit" in rows[0][4]
    assert fetch_scalar(upgraded_database, "SELECT COUNT(*) FROM price_observations_v2") == 0


def test_backfilled_revision_is_not_claimed_to_be_reconciled(upgraded_database: str):
    rows = fetch_all(
        upgraded_database,
        "SELECT reconciliation_status, reconciliation_reason, gap_accepted, "
        "printed_total, computed_total, confirmed_at FROM receipt_revisions",
    )

    assert rows == [("unverifiable", "legacy_confirmation", False, Decimal("25.00"), None, None)]


def test_v1_price_observations_and_raw_amounts_are_untouched(upgraded_database: str):
    columns = {
        row[0]
        for row in fetch_all(
            upgraded_database,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name IN ('receipt_items', 'receipts', 'price_observations')",
        )
    }

    assert {"unit_price", "line_total", "purchase_date", "observed_at"} <= columns
    assert fetch_scalar(
        upgraded_database,
        f"SELECT line_total FROM receipt_items WHERE id = '{CONFIRMED_ITEM_ID}'",
    ) == Decimal("25.00")


def test_the_mutation_key_is_unique_per_owner_and_operation(upgraded_database: str):
    rows = fetch_all(
        upgraded_database,
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'receipt_mutations' "
        "AND indexdef LIKE '%UNIQUE%'",
    )

    assert any(
        "user_id" in row[0] and "operation" in row[0] and "mutation_id" in row[0]
        for row in rows
    )


def test_a_receipt_cannot_have_two_rows_for_the_same_revision(upgraded_database: str):
    revision_id = fetch_scalar(upgraded_database, "SELECT id::text FROM receipt_revisions")

    with pytest.raises(Exception):
        execute(
            upgraded_database,
            [
                "INSERT INTO receipt_revisions (id, receipt_id, user_id, revision, status, "
                f"operation) VALUES ('{revision_id}'::uuid, '{CONFIRMED_RECEIPT_ID}', "
                f"'{USER_ID}', 1, 'confirmed', 'receipt_confirm')",
            ],
        )


def test_comparison_price_keeps_six_decimals_in_sql(upgraded_database: str):
    revision_id = fetch_scalar(upgraded_database, "SELECT id::text FROM receipt_revisions")
    execute(
        upgraded_database,
        [
            "UPDATE receipt_revision_lines SET comparison_price = 82.857143 "
            f"WHERE revision_id = '{revision_id}'::uuid",
        ],
    )

    assert fetch_scalar(
        upgraded_database,
        "SELECT comparison_price FROM receipt_revision_lines",
    ) == Decimal("82.857143")


def test_downgrade_removes_the_new_layer_and_keeps_the_raw_lines(upgraded_database: str):
    result = run_backend(["-m", "alembic", "downgrade", "006"], upgraded_database)

    assert result.returncode == 0, result.stdout + result.stderr
    assert set(NEW_TABLES).isdisjoint(set(table_names(upgraded_database)))
    columns = {
        row[0]
        for row in fetch_all(
            upgraded_database,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'receipts'",
        )
    }
    assert "version" not in columns
    assert fetch_scalar(upgraded_database, "SELECT COUNT(*) FROM receipt_items") == 2


def test_rerunning_the_backfill_does_not_duplicate_revisions(upgraded_database: str):
    run_backend(["-m", "alembic", "downgrade", "006"], upgraded_database)
    alembic_upgrade(upgraded_database, "007")

    assert fetch_scalar(upgraded_database, "SELECT COUNT(*) FROM receipt_revisions") == 1


def test_migrated_schema_matches_the_models(postgres_url: str):
    assert run_migrations_cli(postgres_url).returncode == 0

    assert metadata_differences(postgres_url) == []

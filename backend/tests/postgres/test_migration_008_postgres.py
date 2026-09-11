"""S06-A: migrering 008 mot ekte PostgreSQL, der Decimal, defaults og nøkler er reelle."""

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
LIST_ID = "22222222-2222-2222-2222-222222222222"
ITEM_ID = "33333333-3333-3333-3333-333333333333"

NEW_TABLES = (
    "shopping_list_items",
    "shopping_list_mutations",
    "shopping_list_sync_state",
    "shopping_lists",
)

SEED = (
    f"INSERT INTO users (id, email, password_hash) "
    f"VALUES ('{USER_ID}', 'p0@example.com', 'hash')",
)


@pytest.fixture
def upgraded_database(postgres_url: str) -> str:
    alembic_upgrade(postgres_url, "007")
    execute(postgres_url, list(SEED))
    alembic_upgrade(postgres_url, "008")
    return postgres_url


def _insert_list(url: str) -> None:
    execute(
        url,
        [
            "INSERT INTO shopping_lists (id, user_id, name, status, version, content_seq) "
            f"VALUES ('{LIST_ID}', '{USER_ID}', 'Ukeshandel', 'active', 1, 1)",
        ],
    )


def test_upgrade_creates_the_shopping_list_tables(upgraded_database: str):
    assert set(NEW_TABLES) <= set(table_names(upgraded_database))


def test_the_migration_adds_no_rows(upgraded_database: str):
    assert fetch_scalar(upgraded_database, "SELECT COUNT(*) FROM shopping_lists") == 0
    assert fetch_scalar(upgraded_database, "SELECT COUNT(*) FROM shopping_list_items") == 0


def test_a_list_row_defaults_to_active_and_no_tombstone(upgraded_database: str):
    execute(
        upgraded_database,
        [
            "INSERT INTO shopping_lists (id, user_id, name) "
            f"VALUES ('{LIST_ID}', '{USER_ID}', 'Ukeshandel')",
        ],
    )

    assert fetch_all(
        upgraded_database,
        "SELECT status, version, content_seq, deleted_at FROM shopping_lists",
    ) == [("active", 1, 0, None)]


def test_a_quantity_keeps_three_decimals_in_sql(upgraded_database: str):
    _insert_list(upgraded_database)
    execute(
        upgraded_database,
        [
            "INSERT INTO shopping_list_items (id, user_id, list_id, free_text, quantity, "
            f"quantity_unit, position, version, sync_seq) VALUES ('{ITEM_ID}', '{USER_ID}', "
            f"'{LIST_ID}', 'Kaffe', 0.125, 'kg', 0, 1, 1)",
        ],
    )

    assert fetch_scalar(upgraded_database, "SELECT quantity FROM shopping_list_items") == Decimal(
        "0.125",
    )


def test_a_line_defaults_to_unchecked_and_no_tombstone(upgraded_database: str):
    _insert_list(upgraded_database)
    execute(
        upgraded_database,
        [
            "INSERT INTO shopping_list_items (id, user_id, list_id, free_text, quantity, "
            f"position, version, sync_seq) VALUES ('{ITEM_ID}', '{USER_ID}', '{LIST_ID}', "
            "'Kaffe', 1.000, 0, 1, 1)",
        ],
    )

    assert fetch_all(
        upgraded_database,
        "SELECT checked, quantity_unit, deleted_at FROM shopping_list_items",
    ) == [(False, "unknown", None)]


def test_the_mutation_key_is_unique_per_owner_and_operation(upgraded_database: str):
    rows = fetch_all(
        upgraded_database,
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'shopping_list_mutations' "
        "AND indexdef LIKE '%UNIQUE%'",
    )

    assert any(
        "user_id" in row[0] and "operation" in row[0] and "mutation_id" in row[0]
        for row in rows
    )


def test_the_same_mutation_key_cannot_be_stored_twice(upgraded_database: str):
    _insert_list(upgraded_database)
    insert = (
        "INSERT INTO shopping_list_mutations (id, user_id, operation, mutation_id, "
        "payload_hash, list_id, response) VALUES (gen_random_uuid(), "
        f"'{USER_ID}', 'list_create', '{ITEM_ID}', 'hash', '{LIST_ID}', '{{}}'::json)"
    )
    execute(upgraded_database, [insert])

    with pytest.raises(Exception):
        execute(upgraded_database, [insert])


def test_a_line_cannot_point_at_an_unknown_list(upgraded_database: str):
    with pytest.raises(Exception):
        execute(
            upgraded_database,
            [
                "INSERT INTO shopping_list_items (id, user_id, list_id, free_text, quantity, "
                f"position, version, sync_seq) VALUES ('{ITEM_ID}', '{USER_ID}', '{LIST_ID}', "
                "'Kaffe', 1.000, 0, 1, 1)",
            ],
        )


def test_the_receipt_layer_is_untouched(upgraded_database: str):
    tables = set(table_names(upgraded_database))

    assert {
        "receipts",
        "receipt_items",
        "receipt_revisions",
        "receipt_mutations",
        "price_observations",
        "price_observations_v2",
    } <= tables


def test_downgrade_removes_the_list_tables(upgraded_database: str):
    result = run_backend(["-m", "alembic", "downgrade", "007"], upgraded_database)

    assert result.returncode == 0, result.stdout + result.stderr
    assert set(NEW_TABLES).isdisjoint(set(table_names(upgraded_database)))
    assert "receipt_revisions" in set(table_names(upgraded_database))


def test_migrated_schema_matches_the_models(postgres_url: str):
    assert run_migrations_cli(postgres_url).returncode == 0

    assert metadata_differences(postgres_url) == []

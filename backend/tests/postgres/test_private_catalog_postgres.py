"""S03-A mot ekte PostgreSQL: additiv 005, eieravgrenset backfill og reelle unike nøkler.

SQLite avviser ikke duplikater med NULL-kontekst på samme måte, så aliasnøkkelen
må bevises her.
"""

import asyncio
import uuid

import pytest
from postgres_helpers import alembic_upgrade, execute, fetch_all, fetch_scalar, run_migrations_cli
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.services.private_catalog_backfill import backfill_private_catalog

pytestmark = pytest.mark.postgres

USER_A = "aaaaaaaa-0000-0000-0000-000000000001"
USER_B = "bbbbbbbb-0000-0000-0000-000000000002"
STORE_ID = "cccccccc-0000-0000-0000-000000000003"
PRODUCT_ID = "dddddddd-0000-0000-0000-000000000004"


def _seed_statements() -> list[str]:
    statements = [
        f"INSERT INTO users (id, email, password_hash) VALUES "
        f"('{USER_A}', 'a@example.com', 'hash'), ('{USER_B}', 'b@example.com', 'hash')",
        f"INSERT INTO stores (id, name, normalized_name, chain) VALUES "
        f"('{STORE_ID}', 'Rema 1000 Grunerlokka', 'rema 1000 grunerlokka', 'Rema 1000')",
        f"INSERT INTO products (id, canonical_name) VALUES ('{PRODUCT_ID}', 'MELK LETT 1L')",
    ]
    for index, (user_id, raw_name) in enumerate(
        ((USER_A, "MELK LETT 1L"), (USER_B, "MELK LETT 1L")),
    ):
        receipt_id = f"eeeeeeee-0000-0000-0000-00000000000{index}"
        item_id = f"ffffffff-0000-0000-0000-00000000000{index}"
        statements.append(
            f"INSERT INTO receipts (id, user_id, store_id, purchase_date, total, status, "
            f"image_path, image_expires_at) VALUES ('{receipt_id}', '{user_id}', "
            f"'{STORE_ID}', '2026-09-01 10:00:00+00', 50.00, 'CONFIRMED', "
            f"'{user_id}/kvittering.png', '2026-10-01 10:00:00+00')",
        )
        statements.append(
            f"INSERT INTO receipt_items (id, receipt_id, product_id, raw_product_name, "
            f"quantity, line_total) VALUES ('{item_id}', '{receipt_id}', '{PRODUCT_ID}', "
            f"'{raw_name}', 1.000, 25.00)",
        )
    return statements


def _undated_receipt_statements() -> list[str]:
    receipt_id = "12121212-0000-0000-0000-000000000009"
    item_id = "34343434-0000-0000-0000-000000000009"
    return [
        f"INSERT INTO receipts (id, user_id, store_id, purchase_date, total, status, "
        f"image_path, image_expires_at) VALUES ('{receipt_id}', '{USER_A}', '{STORE_ID}', "
        f"NULL, 25.00, 'CONFIRMED', '{USER_A}/udatert.png', '2026-10-01 10:00:00+00')",
        f"INSERT INTO receipt_items (id, receipt_id, product_id, raw_product_name, quantity, "
        f"line_total) VALUES ('{item_id}', '{receipt_id}', '{PRODUCT_ID}', 'MELK GAMMEL', "
        f"1.000, 25.00)",
    ]


def _rerun_backfill(url: str) -> None:
    async def run() -> None:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(backfill_private_catalog)
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.fixture
def backfilled_url(postgres_url: str) -> str:
    alembic_upgrade(postgres_url, "004")
    execute(postgres_url, _seed_statements())
    result = run_migrations_cli(postgres_url)
    assert result.returncode == 0, result.stdout + result.stderr
    return postgres_url


def test_each_owner_gets_a_private_product_for_the_same_raw_text(backfilled_url: str):
    rows = fetch_all(
        backfilled_url,
        "SELECT user_id, display_name, identity_status, legacy_product_id, purchase_count "
        "FROM user_products ORDER BY user_id",
    )

    assert [str(row[0]) for row in rows] == [USER_A, USER_B]
    assert {row[1] for row in rows} == {"MELK LETT 1L"}
    assert {row[2] for row in rows} == {"inherited"}
    assert {str(row[3]) for row in rows} == {PRODUCT_ID}
    assert {row[4] for row in rows} == {1}


def test_alias_never_points_at_the_other_owners_product(backfilled_url: str):
    rows = fetch_all(
        backfilled_url,
        "SELECT a.user_id, p.user_id FROM user_product_aliases a "
        "JOIN user_products p ON p.id = a.user_product_id",
    )

    assert len(rows) == 2
    assert all(alias_owner == product_owner for alias_owner, product_owner in rows)


def test_global_tables_survive_the_additive_migration(backfilled_url: str):
    assert fetch_scalar(backfilled_url, "SELECT COUNT(*) FROM products") == 1
    assert fetch_scalar(backfilled_url, "SELECT COUNT(*) FROM receipt_items") == 2
    assert fetch_scalar(backfilled_url, "SELECT canonical_name FROM products") == "MELK LETT 1L"


def test_account_ledger_starts_at_one_per_owner(backfilled_url: str):
    rows = fetch_all(
        backfilled_url,
        "SELECT user_id, price_data_version FROM account_ledgers ORDER BY user_id",
    )

    assert [(str(row[0]), row[1]) for row in rows] == [(USER_A, 1), (USER_B, 1)]


def test_rerunning_the_backfill_changes_nothing(backfilled_url: str):
    _rerun_backfill(backfilled_url)

    assert fetch_scalar(backfilled_url, "SELECT COUNT(*) FROM user_products") == 2
    assert fetch_scalar(backfilled_url, "SELECT COUNT(*) FROM user_product_aliases") == 2
    assert fetch_scalar(backfilled_url, "SELECT COUNT(*) FROM user_stores") == 2
    assert fetch_scalar(backfilled_url, "SELECT COUNT(*) FROM account_ledgers") == 2


def _context_free_alias(user_id, user_product_id) -> str:
    return (
        "INSERT INTO user_product_aliases (id, user_id, user_product_id, normalized_text, "
        "store_id, chain, context_key, source, match_method) VALUES "
        f"('{uuid.uuid4()}', '{user_id}', '{user_product_id}', 'melk lett 1l', "
        "NULL, NULL, '', 'user', 'user_confirmed')"
    )


def test_duplicate_alias_without_store_context_is_rejected(backfilled_url: str):
    user_id, user_product_id = fetch_all(
        backfilled_url,
        "SELECT user_id, id FROM user_products LIMIT 1",
    )[0]
    execute(backfilled_url, [_context_free_alias(user_id, user_product_id)])

    with pytest.raises(IntegrityError):
        execute(backfilled_url, [_context_free_alias(user_id, user_product_id)])


def test_line_without_purchase_date_does_not_block_the_dated_display_name(postgres_url: str):
    alembic_upgrade(postgres_url, "004")
    # Den udaterte linjen kommer først, så backfillen må tåle å sammenligne
    # ukjent dato med en tidssonebevisst kjøpsdato.
    execute(postgres_url, _seed_statements()[:3] + _undated_receipt_statements())
    execute(postgres_url, _seed_statements()[3:])

    result = run_migrations_cli(postgres_url)

    assert result.returncode == 0, result.stdout + result.stderr
    rows = fetch_all(
        postgres_url,
        f"SELECT display_name, purchase_count, last_purchased_at FROM user_products "
        f"WHERE user_id = '{USER_A}'",
    )
    assert [(row[0], row[1]) for row in rows] == [("MELK LETT 1L", 2)]
    assert rows[0][2] is not None


def test_store_without_documented_branch_is_not_marked_as_branch(backfilled_url: str):
    rows = fetch_all(
        backfilled_url,
        "SELECT identity_level, chain, branch_name FROM user_stores",
    )

    assert len(rows) == 2
    assert {row[0] for row in rows} == {"chain_only"}
    assert {row[1] for row in rows} == {"Rema 1000"}
    assert {row[2] for row in rows} == {None}

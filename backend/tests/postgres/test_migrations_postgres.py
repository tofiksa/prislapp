"""Migreringstester mot ekte PostgreSQL: frisk database og oppgradering fra hver revisjon."""

from decimal import Decimal

import pytest
from postgres_helpers import (
    alembic_upgrade,
    create_all_schema,
    execute,
    fetch_scalar,
    metadata_differences,
    run_migrations_cli,
)

from scripts import run_migrations

pytestmark = pytest.mark.postgres

HEAD_REVISION = run_migrations.migration_revisions()[-1]

USER_ID = "11111111-1111-1111-1111-111111111111"
STORE_ID = "22222222-2222-2222-2222-222222222222"
RECEIPT_ID = "33333333-3333-3333-3333-333333333333"
ITEM_ID = "44444444-4444-4444-4444-444444444444"
PRODUCT_ID = "55555555-5555-5555-5555-555555555555"
OBSERVATION_ID = "66666666-6666-6666-6666-666666666666"

USER_STATEMENTS = (
    f"INSERT INTO users (id, email, password_hash) "
    f"VALUES ('{USER_ID}', 'p0@example.com', 'hash')",
)
RECEIPT_STATEMENTS = (
    f"INSERT INTO stores (id, name, normalized_name, chain) "
    f"VALUES ('{STORE_ID}', 'Rema 1000 Metro', 'rema 1000 metro', 'rema1000')",
    f"INSERT INTO receipts (id, user_id, store_id, purchase_date, total, status, "
    f"image_path, image_expires_at) VALUES ('{RECEIPT_ID}', '{USER_ID}', '{STORE_ID}', "
    f"'2026-09-01 10:00:00+00', 99.00, 'confirmed', 'receipts/p0.png', "
    f"'2026-10-01 10:00:00+00')",
    f"INSERT INTO receipt_items (id, receipt_id, raw_product_name, quantity, line_total) "
    f"VALUES ('{ITEM_ID}', '{RECEIPT_ID}', 'MELK LETT 1L', 2.000, 50.00)",
)


def _observation_statements(price: str) -> tuple[str, ...]:
    return (
        f"INSERT INTO products (id, canonical_name) "
        f"VALUES ('{PRODUCT_ID}', 'melk lett 1l')",
        f"INSERT INTO price_observations (id, user_id, product_id, store_id, "
        f"receipt_item_id, price) VALUES ('{OBSERVATION_ID}', '{USER_ID}', "
        f"'{PRODUCT_ID}', '{STORE_ID}', '{ITEM_ID}', {price})",
    )


def _stamped_revision(url: str) -> str:
    return fetch_scalar(url, "SELECT version_num FROM alembic_version")


def _assert_user_and_receipt_intact(url: str, with_receipt: bool) -> None:
    assert fetch_scalar(url, "SELECT email FROM users") == "p0@example.com"
    if not with_receipt:
        return
    assert fetch_scalar(url, "SELECT total FROM receipts") == Decimal("99.00")
    assert fetch_scalar(url, "SELECT line_total FROM receipt_items") == Decimal("50.00")


def test_fresh_database_migrates_to_head_with_schema_matching_models(postgres_url):
    result = run_migrations_cli(postgres_url)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "004" in run_migrations.migration_revisions()
    assert _stamped_revision(postgres_url) == HEAD_REVISION
    assert metadata_differences(postgres_url) == []


@pytest.mark.parametrize(
    ("stamped_revision", "seeded_price", "expected_price"),
    [
        ("001", None, None),
        ("002", None, None),
        ("003", "50.00", "25.00"),
        ("004", "25.00", "25.00"),
    ],
)
def test_upgrade_from_stamped_revision_keeps_users_and_receipts(
    postgres_url, stamped_revision, seeded_price, expected_price
):
    alembic_upgrade(postgres_url, stamped_revision)
    statements = list(USER_STATEMENTS)
    if stamped_revision != "001":
        statements += RECEIPT_STATEMENTS
    if seeded_price is not None:
        statements += _observation_statements(seeded_price)
    execute(postgres_url, statements)

    result = run_migrations_cli(postgres_url)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _stamped_revision(postgres_url) == HEAD_REVISION
    assert metadata_differences(postgres_url) == []
    _assert_user_and_receipt_intact(postgres_url, with_receipt=stamped_revision != "001")
    if expected_price is not None:
        price = fetch_scalar(postgres_url, "SELECT price FROM price_observations")
        assert str(price) == expected_price


def test_create_all_database_reaches_head_without_rewriting_normalized_prices(postgres_url):
    create_all_schema(postgres_url)
    execute(
        postgres_url,
        [*USER_STATEMENTS, *RECEIPT_STATEMENTS, *_observation_statements("25.00")],
    )

    result = run_migrations_cli(postgres_url)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _stamped_revision(postgres_url) == HEAD_REVISION
    assert metadata_differences(postgres_url) == []
    _assert_user_and_receipt_intact(postgres_url, with_receipt=True)
    assert str(fetch_scalar(postgres_url, "SELECT price FROM price_observations")) == "25.00"

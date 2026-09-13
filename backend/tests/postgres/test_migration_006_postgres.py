"""S04-A: migrering 006 mot ekte PostgreSQL, der Decimal og defaults er reelle."""

from decimal import Decimal

import pytest
from postgres_helpers import alembic_upgrade, execute, fetch_all, fetch_scalar, run_backend

pytestmark = pytest.mark.postgres

USER_ID = "11111111-1111-1111-1111-111111111111"
STORE_ID = "22222222-2222-2222-2222-222222222222"
DATED_RECEIPT_ID = "33333333-3333-3333-3333-333333333333"
UNDATED_RECEIPT_ID = "44444444-4444-4444-4444-444444444444"
DISCOUNTED_RECEIPT_ID = "55555555-5555-5555-5555-555555555555"


def _receipt(receipt_id: str, purchase_date: str | None, status: str = "CONFIRMED") -> str:
    date_value = "NULL" if purchase_date is None else f"'{purchase_date}'"
    return (
        f"INSERT INTO receipts (id, user_id, store_id, purchase_date, total, status, "
        f"image_path, image_expires_at, created_at) VALUES ('{receipt_id}', '{USER_ID}', "
        f"'{STORE_ID}', {date_value}, 99.00, '{status}', 'receipts/p0.png', "
        f"'2026-10-01 10:00:00+00', '2026-09-11 08:00:00+00')"
    )


def _item(item_id: str, receipt_id: str, name: str, line_total: str, unit_price: str) -> str:
    return (
        f"INSERT INTO receipt_items (id, receipt_id, raw_product_name, quantity, "
        f"unit_price, line_total) VALUES ('{item_id}', '{receipt_id}', '{name}', 1.000, "
        f"{unit_price}, {line_total})"
    )


SEED = (
    f"INSERT INTO users (id, email, password_hash) "
    f"VALUES ('{USER_ID}', 'p0@example.com', 'hash')",
    f"INSERT INTO stores (id, name, normalized_name, chain) "
    f"VALUES ('{STORE_ID}', 'Rema 1000 Metro', 'rema 1000 metro', 'rema1000')",
    _receipt(DATED_RECEIPT_ID, "2026-09-01 00:00:00+00"),
    _receipt(UNDATED_RECEIPT_ID, None),
    _receipt(DISCOUNTED_RECEIPT_ID, "2026-09-02 10:00:00+00"),
    _item(
        "66666666-6666-6666-6666-666666666666",
        DATED_RECEIPT_ID,
        "MELK LETT 1L",
        "25.00",
        "25.00",
    ),
    _item(
        "77777777-7777-7777-7777-777777777777",
        UNDATED_RECEIPT_ID,
        "BRØD GROVT",
        "35.00",
        "35.00",
    ),
    _item(
        "88888888-8888-8888-8888-888888888888",
        DISCOUNTED_RECEIPT_ID,
        "YOGHURT",
        "40.00",
        "40.00",
    ),
    _item(
        "99999999-9999-9999-9999-999999999999",
        DISCOUNTED_RECEIPT_ID,
        "RABATT",
        "-10.00",
        "NULL",
    ),
)


@pytest.fixture
def upgraded_database(postgres_url: str) -> str:
    alembic_upgrade(postgres_url, "005")
    execute(postgres_url, list(SEED))
    alembic_upgrade(postgres_url, "006")
    return postgres_url


def test_existing_lines_get_unknown_enums_not_guessed_ones(upgraded_database: str):
    rows = fetch_all(
        upgraded_database,
        "SELECT DISTINCT line_type, quantity_unit, price_basis, condition FROM receipt_items",
    )

    assert rows == [("unknown", "unknown", "unknown", "unknown")]


def test_undated_receipt_keeps_a_null_purchase_date_after_the_upgrade(upgraded_database: str):
    rows = fetch_all(
        upgraded_database,
        "SELECT purchase_date, purchase_time, date_precision, date_source FROM receipts "
        f"WHERE id = '{UNDATED_RECEIPT_ID}'",
    )

    assert rows == [(None, None, "unknown", "unknown")]


def test_midnight_purchase_date_is_not_promoted_to_datetime(upgraded_database: str):
    rows = fetch_all(
        upgraded_database,
        "SELECT purchase_time, date_precision FROM receipts "
        f"WHERE id = '{DATED_RECEIPT_ID}'",
    )

    assert rows == [(None, "date")]


def test_confirmed_line_without_discount_line_gets_an_exact_net_total(upgraded_database: str):
    net_total = fetch_scalar(
        upgraded_database,
        "SELECT net_line_total FROM receipt_items "
        "WHERE receipt_id = '" + DATED_RECEIPT_ID + "'",
    )

    assert net_total == Decimal("25.00")


def test_receipt_with_a_discount_line_leaves_every_net_total_unknown(upgraded_database: str):
    rows = fetch_all(
        upgraded_database,
        "SELECT net_line_total FROM receipt_items "
        f"WHERE receipt_id = '{DISCOUNTED_RECEIPT_ID}'",
    )

    assert rows == [(None,), (None,)]


def test_printed_unit_price_mirrors_the_read_unit_price(upgraded_database: str):
    rows = fetch_all(
        upgraded_database,
        "SELECT unit_price, printed_unit_price FROM receipt_items ORDER BY line_total",
    )

    assert rows == [
        (None, None),
        (Decimal("25.00"), Decimal("25.00")),
        (Decimal("35.00"), Decimal("35.00")),
        (Decimal("40.00"), Decimal("40.00")),
    ]


def test_downgrade_removes_the_new_columns_and_keeps_the_raw_amounts(upgraded_database: str):
    result = run_backend(["-m", "alembic", "downgrade", "005"], upgraded_database)

    assert result.returncode == 0, result.stdout + result.stderr
    columns = {
        row[0]
        for row in fetch_all(
            upgraded_database,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name IN ('receipts', 'receipt_items')",
        )
    }
    assert {"purchase_time", "date_precision", "date_source"}.isdisjoint(columns)
    assert {"line_type", "net_line_total", "printed_unit_price"}.isdisjoint(columns)
    assert {"unit_price", "line_total", "purchase_date"} <= columns
    assert fetch_scalar(
        upgraded_database,
        f"SELECT line_total FROM receipt_items WHERE receipt_id = '{DATED_RECEIPT_ID}'",
    ) == Decimal("25.00")


def test_new_rows_default_to_unknown_without_explicit_values(upgraded_database: str):
    execute(
        upgraded_database,
        [
            _receipt("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "2026-09-03 10:00:00+00"),
            _item(
                "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "NY LINJE",
                "10.00",
                "10.00",
            ),
        ],
    )

    rows = fetch_all(
        upgraded_database,
        "SELECT r.date_precision, r.date_source, i.line_type, i.quantity_unit, "
        "i.price_basis, i.condition FROM receipts r JOIN receipt_items i "
        "ON i.receipt_id = r.id WHERE r.id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'",
    )

    assert rows == [("unknown", "unknown", "unknown", "unknown", "unknown", "unknown")]

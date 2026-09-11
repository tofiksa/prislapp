"""S06-D: ren mapping fra liste- og kvitteringslinjer — uten HTTP."""

import uuid
from decimal import Decimal

from app.domain.list_copy import (
    MappedListLine,
    SourceListLine,
    SourceReceiptLine,
    copy_list_lines,
    map_receipt_lines,
    resolve_wanted_quantity,
)

PRODUCT = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER = uuid.UUID("22222222-2222-4222-8222-222222222222")


def _list_line(**overrides) -> SourceListLine:
    values = {
        "id": uuid.uuid4(),
        "user_product_id": PRODUCT,
        "free_text": None,
        "quantity": Decimal("2.000"),
        "quantity_unit": "each",
        "checked": False,
        "position": 0,
        "deleted": False,
    }
    values.update(overrides)
    return SourceListLine(**values)


def _receipt_line(**overrides) -> SourceReceiptLine:
    values = {
        "line_type": "product",
        "raw_product_name": "MELK LETT 1L",
        "user_product_id": PRODUCT,
        "quantity": Decimal("2"),
        "quantity_unit": "l",
        "deleted": False,
        "position": 0,
    }
    values.update(overrides)
    return SourceReceiptLine(**values)


def test_copy_assigns_no_checked_flags_and_keeps_duplicate_product_lines():
    first = _list_line(position=0, checked=True)
    second = _list_line(position=1, checked=True)
    deleted = _list_line(position=2, deleted=True, free_text="Borte", user_product_id=None)

    copied = copy_list_lines([second, deleted, first])

    assert copied == [
        MappedListLine(PRODUCT, None, Decimal("2.000"), "each"),
        MappedListLine(PRODUCT, None, Decimal("2.000"), "each"),
    ]


def test_unchecked_only_skips_checked_and_deleted_source_lines():
    keep = _list_line(position=0, checked=False, free_text="Brød", user_product_id=None)
    skip_checked = _list_line(position=1, checked=True)
    skip_deleted = _list_line(position=2, deleted=True, checked=False)

    copied = copy_list_lines([keep, skip_checked, skip_deleted], unchecked_only=True)

    assert copied == [MappedListLine(None, "Brød", Decimal("2.000"), "each")]


def test_known_receipt_quantity_and_unit_are_copied():
    quantity, unit = resolve_wanted_quantity(Decimal("1.5"), "kg")
    assert quantity == Decimal("1.5")
    assert unit == "kg"


def test_unknown_or_missing_receipt_unit_becomes_one_each():
    assert resolve_wanted_quantity(Decimal("3"), "unknown") == (Decimal("1"), "each")
    assert resolve_wanted_quantity(None, "kg") == (Decimal("1"), "each")
    assert resolve_wanted_quantity(None, None) == (Decimal("1"), "each")


def test_receipt_mapping_keeps_products_skips_fees_and_falls_back_to_free_text():
    owned = {PRODUCT}
    lines = [
        _receipt_line(position=0),
        _receipt_line(
            position=1,
            line_type="deposit",
            raw_product_name="PANT",
            user_product_id=None,
        ),
        _receipt_line(
            position=2,
            line_type="fee",
            raw_product_name="POSE",
            user_product_id=None,
        ),
        _receipt_line(
            position=3,
            line_type="discount",
            raw_product_name="RABATT",
            user_product_id=None,
        ),
        _receipt_line(
            position=4,
            line_type="return",
            raw_product_name="RETUR",
            user_product_id=None,
        ),
        _receipt_line(
            position=5,
            line_type="unknown",
            raw_product_name="UKJENT",
            user_product_id=None,
        ),
        _receipt_line(
            position=6,
            user_product_id=None,
            raw_product_name="FRITEKST",
            quantity=None,
            quantity_unit="unknown",
        ),
        _receipt_line(position=7, user_product_id=OTHER, raw_product_name="SLETTET"),
        _receipt_line(position=8, deleted=True, raw_product_name="SLETTET LINJE"),
    ]

    mapped = map_receipt_lines(lines, owned)

    assert mapped == [
        MappedListLine(PRODUCT, None, Decimal("2"), "l"),
        MappedListLine(None, "FRITEKST", Decimal("1"), "each"),
        MappedListLine(None, "SLETTET", Decimal("2"), "l"),
    ]

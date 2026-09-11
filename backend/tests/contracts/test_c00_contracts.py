"""C00: shared contract fixtures, money rules, and OpenAPI surface."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.domain.money import COMPARISON_QUANTUM, display_nok, per_package_price, per_quantity_price
from app.domain.units import QuantityUnit, normalize_quantity

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "docs" / "contracts" / "fixtures"
OPENAPI_PATH = REPO_ROOT / "docs" / "contracts" / "openapi-v2.json"

REQUIRED_FIXTURES = (
    "two-packages.json",
    "kg-item.json",
    "pack-size-mismatch.json",
    "discount-allocated.json",
    "discount-unresolved.json",
    "rounding.json",
    "old-and-newer-price.json",
    "unknown-date.json",
    "tied-lowest.json",
    "partial-coverage.json",
    "price-correction-invalidates-cache.json",
    "error-409-version.json",
    "shopping-list-price-summary.json",
)

REQUIRED_OPENAPI_PATHS = (
    "/v2/me/products",
    "/v2/me/products/{id}",
    "/v2/me/products/{id}/merge",
    "/v2/me/products/{id}/prices",
    "/v2/me/stores",
    "/v2/receipts/{id}/draft",
    "/v2/receipts/{id}/confirm",
    "/v2/receipts/{id}/revisions",
    "/v2/shopping-lists",
    "/v2/shopping-lists/{id}",
    "/v2/shopping-lists/{id}/items",
    "/v2/shopping-lists/{id}/price-summary",
    "/v2/sync",
    "/v2/me",
    "/v2/me/exports",
    "/auth/password-reset/request",
    "/auth/password-reset/complete",
    "/auth/logout",
    "/auth/logout-all",
)


def _load_fixture(name: str) -> dict:
    path = FIXTURE_DIR / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_required_contract_fixtures_exist():
    missing = [name for name in REQUIRED_FIXTURES if not (FIXTURE_DIR / name).is_file()]
    assert missing == []


def test_two_packages_give_twenty_per_package():
    fixture = _load_fixture("two-packages.json")
    assert fixture["comparison_price"] == "20.000000"
    assert fixture["price_basis"] == "per_package"
    assert fixture["eligible"] is True


def test_kg_item_compares_per_kg_never_each():
    fixture = _load_fixture("kg-item.json")
    assert fixture["price_basis"] == "per_kg"
    assert fixture["comparison_price"] == "82.857143"
    assert fixture["warnings"] == []


def test_pack_sizes_are_not_the_same_product_minimum():
    fixture = _load_fixture("pack-size-mismatch.json")
    assert fixture["same_package_minimum"] is False
    assert fixture["left"]["pack_content"] != fixture["right"]["pack_content"]


def test_allocated_discount_reduces_net_line():
    fixture = _load_fixture("discount-allocated.json")
    assert fixture["net_line_total"] == "30.00"
    assert fixture["eligible"] is True


def test_unresolved_discount_is_not_ranked():
    fixture = _load_fixture("discount-unresolved.json")
    assert fixture["eligible"] is False
    assert "unknown_discount" in fixture["exclusion_reasons"]


def test_rounding_fixture_matches_domain_rules():
    fixture = _load_fixture("rounding.json")
    internal = Decimal(fixture["internal"])
    assert internal == Decimal("1.005000")
    assert fixture["display"] == "1.01"


def test_old_and_newer_prices_are_separate_facts():
    fixture = _load_fixture("old-and-newer-price.json")
    assert fixture["historical_lowest"]["amount"] == "19.90"
    assert fixture["latest_by_store"][0]["amount"] == "29.90"
    assert fixture["historical_lowest"]["age_label"] == "gammel observasjon"


def test_unknown_date_is_not_todays_purchase():
    fixture = _load_fixture("unknown-date.json")
    assert fixture["date_precision"] == "unknown"
    assert fixture["eligible_for_dated_ranking"] is False
    assert fixture["purchase_date"] is None


def test_tied_lowest_shows_all_first_places():
    fixture = _load_fixture("tied-lowest.json")
    assert len(fixture["historical_lowest"]["tied_stores"]) == 2
    assert fixture["historical_lowest"]["amount"] == "24.90"


def test_partial_coverage_does_not_treat_unknown_as_zero():
    fixture = _load_fixture("partial-coverage.json")
    assert fixture["priced_lines"] == 1
    assert fixture["active_unchecked_lines"] == 2
    assert fixture["coverage"] == "1/2"
    assert fixture["store_b"]["winner"] is False
    assert "0.00" not in json.dumps(fixture["store_b"]["missing_lines"])


def test_price_correction_invalidates_cached_minimum():
    fixture = _load_fixture("price-correction-invalidates-cache.json")
    assert fixture["before"]["historical_lowest"] == "2.50"
    assert fixture["after"]["historical_lowest"] == "25.00"
    assert fixture["after"]["price_data_version"] > fixture["before"]["price_data_version"]


def test_version_conflict_error_shape():
    fixture = _load_fixture("error-409-version.json")
    for key in ("code", "message", "field_errors", "retryable", "request_id"):
        assert key in fixture
    assert fixture["code"] == "VERSION_CONFLICT"
    assert fixture["retryable"] is False
    assert "ocr" not in fixture["message"].lower()
    assert "stack" not in json.dumps(fixture).lower()


def test_shopping_list_price_summary_versions():
    fixture = _load_fixture("shopping-list-price-summary.json")
    for key in ("list_version", "price_data_version", "calculated_at", "policy_version"):
        assert key in fixture
    assert len(fixture["lines"]) == 2
    assert all("status" in line for line in fixture["lines"])


def test_openapi_documents_v2_and_auth_extensions():
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = spec["paths"]
    missing = [path for path in REQUIRED_OPENAPI_PATHS if path not in paths]
    assert missing == []
    error = spec["components"]["schemas"]["ErrorResponse"]
    assert set(error["required"]) >= {"code", "message", "retryable", "request_id"}


def test_display_nok_uses_half_up_two_decimals():
    assert display_nok(Decimal("1.005")) == "1.01"
    assert display_nok(Decimal("1.004")) == "1.00"


def test_per_package_price_keeps_comparison_precision():
    price = per_package_price(Decimal("40.00"), Decimal("2"))
    assert price == Decimal("20.000000")
    assert price == price.quantize(COMPARISON_QUANTUM)


def test_kg_price_from_net_and_quantity():
    price = per_quantity_price(Decimal("31.90"), Decimal("0.385"))
    assert price == Decimal("82.857143")


def test_normalize_g_to_kg_and_ml_to_l():
    assert normalize_quantity(Decimal("400"), QuantityUnit.G) == (
        Decimal("0.400"),
        QuantityUnit.KG,
    )
    assert normalize_quantity(Decimal("500"), QuantityUnit.ML) == (
        Decimal("0.500"),
        QuantityUnit.L,
    )
    each = normalize_quantity(Decimal("2"), QuantityUnit.EACH)
    assert each == (Decimal("2"), QuantityUnit.EACH)

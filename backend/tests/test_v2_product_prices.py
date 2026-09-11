"""S04-B: GET /v2/me/products/{id}/prices — kvalifisering, proveniens og cacheversjon."""

import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt, ReceiptStatus
from app.models.user import User
from app.models.user_product import IdentityStatus, UserProduct
from app.models.user_store import StoreIdentityLevel, UserStore

pytestmark = pytest.mark.asyncio

PASSWORD = "TestPass123!"
OSLO = ZoneInfo("Europe/Oslo")
DISCLAIMER = "Dagens pris kan være annerledes"
CONTRACTS = Path(__file__).resolve().parents[2] / "docs" / "contracts"


def _today() -> date:
    return datetime.now(OSLO).date()


def _days_ago(days: int) -> str:
    return (_today() - timedelta(days=days)).isoformat()


async def _register(client: AsyncClient, db: AsyncSession, email: str) -> tuple[User, dict]:
    response = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code in (200, 201), response.text
    token = response.json()["access_token"]
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    return user, {"Authorization": f"Bearer {token}"}


async def _store(
    db: AsyncSession,
    user: User,
    display_name: str = "Rema 1000 Torshov",
    identity_level: str = StoreIdentityLevel.BRANCH.value,
) -> UserStore:
    store = UserStore(
        user_id=user.id,
        display_name=display_name,
        chain="rema1000",
        branch_name=display_name,
        identity_level=identity_level,
        version=1,
    )
    db.add(store)
    await db.flush()
    return store


async def _product(
    db: AsyncSession,
    user: User,
    display_name: str = "Melk lett 1L",
    identity_status: str = IdentityStatus.CONFIRMED.value,
) -> UserProduct:
    product = UserProduct(
        user_id=user.id,
        display_name=display_name,
        pack_unit="l",
        pack_content=Decimal("1.000"),
        identity_status=identity_status,
        purchase_count=1,
        version=1,
    )
    db.add(product)
    await db.flush()
    return product


async def _receipt(db: AsyncSession, user: User) -> Receipt:
    receipt = Receipt(
        user_id=user.id,
        status=ReceiptStatus.READY_FOR_REVIEW.value,
        image_path=f"{user.id}/receipt.jpg",
        image_expires_at=datetime(2026, 12, 1, tzinfo=OSLO),
    )
    db.add(receipt)
    await db.flush()
    return receipt


def _line(product: UserProduct | None, price: str, **overrides) -> dict:
    line = {
        "id": str(uuid.uuid4()),
        "raw_product_name": "MELK LETT 1L",
        "user_product_id": str(product.id) if product else None,
        "quantity": "1",
        "quantity_unit": "each",
        "line_type": "product",
        "net_line_total": price,
        "printed_unit_price": price,
        "condition": "none",
    }
    line.update(overrides)
    return line


async def _confirm(
    client: AsyncClient,
    db: AsyncSession,
    user: User,
    headers: dict,
    *,
    store: UserStore | None,
    lines: list[dict],
    purchase_date: str | None,
    date_precision: str = "date",
    purchase_time: str | None = None,
) -> Receipt:
    receipt = await _receipt(db, user)
    total = sum(
        (Decimal(line["net_line_total"]) for line in lines if line["net_line_total"]),
        Decimal("0"),
    )
    response = await client.post(
        f"/v2/receipts/{receipt.id}/confirm",
        json={
            "expected_version": 0,
            "mutation_id": str(uuid.uuid4()),
            "store_id": str(store.id) if store else None,
            "purchase_date": purchase_date,
            "purchase_time": purchase_time,
            "date_precision": date_precision,
            "printed_total": str(total),
            "lines": lines,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return receipt


async def _observe(
    client: AsyncClient,
    db: AsyncSession,
    user: User,
    headers: dict,
    *,
    store: UserStore | None,
    product: UserProduct,
    price: str,
    purchase_date: str | None,
    date_precision: str = "date",
    purchase_time: str | None = None,
    **line_overrides,
) -> Receipt:
    """Én bekreftet kvittering med én linje for varen."""
    return await _confirm(
        client,
        db,
        user,
        headers,
        store=store,
        lines=[_line(product, price, **line_overrides)],
        purchase_date=purchase_date,
        date_precision=date_precision,
        purchase_time=purchase_time,
    )


async def _prices(client: AsyncClient, product: UserProduct, headers: dict, **params):
    return await client.get(
        f"/v2/me/products/{product.id}/prices",
        params=params,
        headers=headers,
    )


def _fixture(name: str) -> dict:
    with (CONTRACTS / "fixtures" / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _contract_required() -> list[str]:
    with (CONTRACTS / "openapi-v2.json").open(encoding="utf-8") as handle:
        spec = json.load(handle)
    return spec["components"]["schemas"]["ProductPriceResponse"]["required"]


async def test_a_cheaper_unresolved_product_has_no_lowest(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    unresolved = await _product(
        db_session,
        owner,
        "Melk ukjent",
        identity_status=IdentityStatus.UNRESOLVED.value,
    )
    await _observe(
        client,
        db_session,
        owner,
        headers,
        store=store,
        product=unresolved,
        price="19.90",
        purchase_date=_days_ago(5),
    )

    response = await _prices(client, unresolved, headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["historical_lowest"] is None
    assert body["eligible_store_count"] == 0
    assert body["excluded_observation_count"] == 1
    assert body["excluded_reasons"]["unresolved_identity"] == 1


async def test_a_cheaper_unresolved_line_is_not_another_products_lowest(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    confirmed = await _product(db_session, owner)
    inherited = await _product(
        db_session,
        owner,
        "Melk arvet",
        identity_status=IdentityStatus.INHERITED.value,
    )
    await _confirm(
        client,
        db_session,
        owner,
        headers,
        store=store,
        lines=[_line(confirmed, "29.90"), _line(inherited, "19.90")],
        purchase_date=_days_ago(5),
    )

    response = await _prices(client, confirmed, headers)

    assert response.status_code == 200, response.text
    assert response.json()["historical_lowest"]["amount"] == "29.90"


async def test_two_stores_with_the_same_lowest_are_both_first_places(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    rema = await _store(db_session, owner, "Rema 1000 Majorstuen")
    kiwi = await _store(db_session, owner, "Kiwi Frogner")
    product = await _product(db_session, owner)
    await _observe(
        client, db_session, owner, headers,
        store=rema, product=product, price="24.90", purchase_date=_days_ago(40),
    )
    await _observe(
        client, db_session, owner, headers,
        store=kiwi, product=product, price="24.90", purchase_date=_days_ago(22),
    )

    response = await _prices(client, product, headers)

    lowest = response.json()["historical_lowest"]
    assert lowest["amount"] == "24.90"
    assert [tied["name"] for tied in lowest["tied_stores"]] == [
        "Rema 1000 Majorstuen",
        "Kiwi Frogner",
    ]
    assert {tied["identity_level"] for tied in lowest["tied_stores"]} == {"branch"}


async def test_an_old_low_price_and_a_newer_high_price_are_two_facts(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner, "Rema 1000 Majorstuen")
    product = await _product(db_session, owner)
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="19.90", purchase_date=_days_ago(152),
    )
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="29.90", purchase_date=_days_ago(3),
    )

    body = (await _prices(client, product, headers)).json()

    lowest = body["historical_lowest"]
    assert lowest["amount"] == "19.90"
    assert lowest["age_label"] == "gammel observasjon"
    assert lowest["disclaimer"] == DISCLAIMER
    assert lowest["store_identity"] == "branch"
    assert [(latest["amount"], latest["age_label"]) for latest in body["latest_by_store"]] == [
        ("29.90", "registrert nylig"),
    ]


async def test_an_observation_between_31_and_90_days_is_an_older_observation(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="19.90", purchase_date=_days_ago(45),
    )

    body = (await _prices(client, product, headers)).json()

    assert body["historical_lowest"]["age_label"] == "eldre observasjon"


async def test_two_prices_on_the_same_undated_day_are_uncertain(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    same_day = _days_ago(4)
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="19.90", purchase_date=same_day,
    )
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="29.90", purchase_date=same_day,
    )

    body = (await _prices(client, product, headers)).json()

    latest = body["latest_by_store"][0]
    assert latest["certainty"] == "same_day_uncertain"
    assert latest["amount"] is None
    assert latest["amount_range"] == {"min": "19.90", "max": "29.90"}
    assert latest["observation_count"] == 2
    assert len(latest["sources"]) == 2


async def test_a_known_time_resolves_the_latest_on_the_same_day(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    same_day = _days_ago(4)
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="19.90", purchase_date=same_day,
        date_precision="datetime", purchase_time="10:15:00",
    )
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="29.90", purchase_date=same_day,
        date_precision="datetime", purchase_time="18:40:00",
    )

    body = (await _prices(client, product, headers)).json()

    latest = body["latest_by_store"][0]
    assert latest["certainty"] == "certain"
    assert latest["amount"] == "29.90"
    assert latest["amount_range"] is None


async def test_an_undated_observation_is_not_in_the_dated_lowest(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="5.00",
        purchase_date=None, date_precision="unknown",
    )
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="25.00", purchase_date=_days_ago(6),
    )

    body = (await _prices(client, product, headers)).json()

    assert body["historical_lowest"]["amount"] == "25.00"
    assert body["excluded_reasons"]["unknown_date"] == 1
    undated = [item for item in body["history"]["items"] if item["purchase_date"] is None]
    assert [item["amount"] for item in undated] == ["5.00"]
    assert undated[0]["ranked"] is False


async def test_a_coupon_price_is_not_the_lowest_by_default(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="10.00", purchase_date=_days_ago(8),
        condition="coupon",
    )
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="25.00", purchase_date=_days_ago(6),
    )

    body = (await _prices(client, product, headers)).json()

    assert body["historical_lowest"]["amount"] == "25.00"
    assert body["excluded_reasons"]["conditional"] == 1
    coupon = [item for item in body["history"]["items"] if item["condition"] == "coupon"]
    assert [item["amount"] for item in coupon] == ["10.00"]


async def test_include_conditional_ranks_the_coupon_price(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="10.00", purchase_date=_days_ago(8),
        condition="coupon",
    )
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="25.00", purchase_date=_days_ago(6),
    )

    body = (await _prices(client, product, headers, include_conditional="true")).json()

    lowest = body["historical_lowest"]
    assert lowest["amount"] == "10.00"
    assert lowest["condition"] == "coupon"


async def test_include_conditional_still_does_not_rank_an_unknown_condition(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="1.00", purchase_date=_days_ago(8),
        condition="unknown",
    )
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="25.00", purchase_date=_days_ago(6),
    )

    body = (await _prices(client, product, headers, include_conditional="true")).json()

    assert body["historical_lowest"]["amount"] == "25.00"
    assert body["excluded_reasons"]["unknown_condition"] == 1


async def test_a_chain_only_store_never_wins_and_is_not_an_eligible_store(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    branch = await _store(db_session, owner, "Rema 1000 Torshov")
    chain_only = await _store(
        db_session,
        owner,
        "Rema 1000",
        identity_level=StoreIdentityLevel.CHAIN_ONLY.value,
    )
    product = await _product(db_session, owner)
    await _observe(
        client, db_session, owner, headers,
        store=branch, product=product, price="25.00", purchase_date=_days_ago(6),
    )
    await _observe(
        client, db_session, owner, headers,
        store=chain_only, product=product, price="19.90", purchase_date=_days_ago(4),
    )

    body = (await _prices(client, product, headers)).json()

    assert body["eligible_store_count"] == 1
    lowest = body["historical_lowest"]
    assert lowest["amount"] == "25.00"
    assert [tied["store_id"] for tied in lowest["tied_stores"]] == [str(branch.id)]
    assert [store["store_id"] for store in body["latest_by_store"]] == [str(branch.id)]
    assert body["excluded_reasons"]["store_not_branch"] == 1
    cheap = [item for item in body["history"]["items"] if item["amount"] == "19.90"]
    assert cheap[0]["ranked"] is False
    assert cheap[0]["store_id"] == str(chain_only.id)


async def test_price_bases_are_not_compared_against_each_other(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    for price in ("50.00", "40.00"):
        await _observe(
            client, db_session, owner, headers,
            store=store, product=product, price=price, purchase_date=_days_ago(6),
            quantity="2", quantity_unit="kg",
        )
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="5.00", purchase_date=_days_ago(6),
    )

    body = (await _prices(client, product, headers)).json()

    assert body["price_basis"] == "per_kg"
    assert body["historical_lowest"]["amount"] == "20.00"
    assert body["excluded_reasons"]["price_basis_mismatch"] == 1


async def test_history_is_paginated_while_the_summary_covers_everything(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    for days, price in ((3, "30.00"), (10, "28.00"), (40, "12.00")):
        await _observe(
            client, db_session, owner, headers,
            store=store, product=product, price=price, purchase_date=_days_ago(days),
        )

    first = (await _prices(client, product, headers, limit=2)).json()

    assert [item["amount"] for item in first["history"]["items"]] == ["30.00", "28.00"]
    assert first["history"]["total_count"] == 3
    assert first["next_cursor"] is not None
    # Minimumet ligger på side to, men oppsummeringen dekker hele grunnlaget.
    assert first["historical_lowest"]["amount"] == "12.00"

    second = (
        await _prices(client, product, headers, limit=2, cursor=first["next_cursor"])
    ).json()

    assert [item["amount"] for item in second["history"]["items"]] == ["12.00"]
    assert second["next_cursor"] is None


async def test_history_carries_the_source_reference_of_every_purchase(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    receipt = await _observe(
        client, db_session, owner, headers,
        store=store, product=product, price="25.00", purchase_date=_days_ago(6),
    )

    body = (await _prices(client, product, headers)).json()

    source = body["history"]["items"][0]["source"]
    assert source["receipt_id"] == str(receipt.id)
    assert source["revision"] == 1
    assert uuid.UUID(source["line_id"])
    assert uuid.UUID(source["revision_id"])


async def test_correcting_a_price_raises_the_lowest_and_the_cache_version(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    line = _line(product, "2.50")
    receipt = await _confirm(
        client, db_session, owner, headers,
        store=store, lines=[line], purchase_date=_days_ago(6),
    )
    before = (await _prices(client, product, headers)).json()
    assert before["historical_lowest"]["amount"] == "2.50"

    correction = await client.post(
        f"/v2/receipts/{receipt.id}/revisions",
        json={
            "expected_version": 1,
            "mutation_id": str(uuid.uuid4()),
            "store_id": str(store.id),
            "purchase_date": _days_ago(6),
            "date_precision": "date",
            "printed_total": "25.00",
            "lines": [dict(line, net_line_total="25.00", printed_unit_price="25.00")],
        },
        headers=headers,
    )
    assert correction.status_code == 200, correction.text

    after = (await _prices(client, product, headers)).json()

    assert after["historical_lowest"]["amount"] == "25.00"
    assert after["price_data_version"] > before["price_data_version"]
    assert after["history"]["total_count"] == 1


async def test_another_owners_product_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "owner@example.com")
    other, _ = await _register(client, db_session, "other@example.com")
    foreign = await _product(db_session, other)

    response = await _prices(client, foreign, headers)

    assert response.status_code == 404, response.text
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert str(foreign.id) not in body["message"]


async def test_an_unknown_product_id_is_not_found(client: AsyncClient, db_session: AsyncSession):
    _, headers = await _register(client, db_session, "owner@example.com")

    response = await client.get(f"/v2/me/products/{uuid.uuid4()}/prices", headers=headers)

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


async def test_prices_require_authentication(client: AsyncClient, db_session: AsyncSession):
    owner, _ = await _register(client, db_session, "owner@example.com")
    product = await _product(db_session, owner)

    response = await client.get(f"/v2/me/products/{product.id}/prices")

    assert response.status_code in (401, 403)


async def test_a_product_without_purchases_has_no_lowest(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    product = await _product(db_session, owner)

    body = (await _prices(client, product, headers)).json()

    assert body["product_id"] == str(product.id)
    assert body["currency"] == "NOK"
    assert body["price_basis"] == "unknown"
    assert body["historical_lowest"] is None
    assert body["latest_by_store"] == []
    assert body["eligible_store_count"] == 0
    assert body["excluded_observation_count"] == 0
    assert body["history"] == {"items": [], "total_count": 0}
    assert body["pack_content"] == "1.000"
    assert body["pack_unit"] == "l"


async def test_a_cursor_from_another_listing_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    product = await _product(db_session, owner)

    response = await _prices(client, product, headers, cursor="ikke-en-markor")

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "INVALID_CURSOR"


async def test_two_receipts_sharing_a_line_id_are_two_purchases(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    shared = str(uuid.uuid4())
    await _confirm(
        client, db_session, owner, headers,
        store=store,
        lines=[_line(product, "25.00", id=shared)],
        purchase_date=_days_ago(6),
    )
    await _confirm(
        client, db_session, owner, headers,
        store=store,
        lines=[_line(product, "19.90", id=shared, condition="unknown")],
        purchase_date=_days_ago(4),
    )

    body = (await _prices(client, product, headers)).json()

    assert body["history"]["total_count"] == 2
    assert body["historical_lowest"]["amount"] == "25.00"


async def test_the_response_carries_every_contract_field(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    product = await _product(db_session, owner)

    body = (await _prices(client, product, headers)).json()

    assert [field for field in _contract_required() if field not in body] == []


async def test_the_response_reproduces_the_old_and_newer_price_fixture(
    client: AsyncClient,
    db_session: AsyncSession,
):
    fixture = _fixture("old-and-newer-price.json")
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner, fixture["historical_lowest"]["store_name"])
    product = await _product(db_session, owner)
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product,
        price=fixture["historical_lowest"]["amount"], purchase_date=_days_ago(152),
    )
    await _observe(
        client, db_session, owner, headers,
        store=store, product=product,
        price=fixture["latest_by_store"][0]["amount"], purchase_date=_days_ago(3),
    )

    body = (await _prices(client, product, headers)).json()

    lowest = fixture["historical_lowest"]
    assert body["currency"] == fixture["currency"]
    assert body["price_basis"] == fixture["price_basis"]
    assert {key: body["historical_lowest"][key] for key in lowest} == lowest
    assert [
        {key: store_price[key] for key in fixture["latest_by_store"][0]}
        for store_price in body["latest_by_store"]
    ] == fixture["latest_by_store"]


async def test_the_response_reproduces_the_tied_lowest_fixture(
    client: AsyncClient,
    db_session: AsyncSession,
):
    fixture = _fixture("tied-lowest.json")["historical_lowest"]
    owner, headers = await _register(client, db_session, "owner@example.com")
    product = await _product(db_session, owner)
    expected = []
    for tied in fixture["tied_stores"]:
        store = await _store(db_session, owner, tied["name"], tied["identity_level"])
        days = (_today() - date.fromisoformat(tied["purchase_date"])).days
        await _observe(
            client, db_session, owner, headers,
            store=store, product=product,
            price=fixture["amount"], purchase_date=tied["purchase_date"],
        )
        expected.append(dict(tied, store_id=str(store.id)))
        assert days > 0, "fixturedatoene må ligge bak dagens dato"

    body = (await _prices(client, product, headers)).json()

    assert body["historical_lowest"]["amount"] == fixture["amount"]
    assert body["historical_lowest"]["tied_stores"] == expected

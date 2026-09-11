"""S07-A: GET /v2/shopping-lists/{id}/price-summary — batchprising av handlelisten."""

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt, ReceiptStatus
from app.models.user import User
from app.models.user_product import IdentityStatus, UserProduct
from app.models.user_store import StoreIdentityLevel, UserStore
from app.services import shopping_list_price_summary_service as summary_service

pytestmark = pytest.mark.asyncio

PASSWORD = "TestPass123!"
OSLO = ZoneInfo("Europe/Oslo")
DISCLAIMER = "Dagens pris kan være annerledes"
POLICY_VERSION = "p0-2026-09-11"
CONTRACTS = Path(__file__).resolve().parents[2] / "docs" / "contracts"
LINE_COUNT = 100
# Budsjettet må ligge langt under linjeantallet. Ett oppslag per linje ville
# vært 100, og et budsjett som vokser med listen er ikke et budsjett.
QUERY_BUDGET = 15


@contextmanager
def _counted_statements(db: AsyncSession) -> Iterator[list[str]]:
    """Teller SQL-setninger på den motoren forespørselen faktisk bruker."""
    engine = db.bind.sync_engine
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


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
    display_name: str = "Rema 1000 Majorstuen",
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
        image_path=f"{user.id}/{uuid.uuid4()}.jpg",
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
) -> None:
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
            "purchase_time": None,
            "date_precision": date_precision,
            "printed_total": str(total),
            "lines": lines,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text


async def _new_list(client: AsyncClient, headers: dict, name: str = "Ukeshandel") -> str:
    response = await client.post(
        "/v2/shopping-lists",
        json={"mutation_id": str(uuid.uuid4()), "name": name},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _add_item(client: AsyncClient, headers: dict, list_id: str, **overrides) -> dict:
    payload = {
        "mutation_id": str(uuid.uuid4()),
        "quantity": "1",
        "quantity_unit": "each",
    }
    payload.update(overrides)
    response = await client.post(
        f"/v2/shopping-lists/{list_id}/items",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _summary(client: AsyncClient, headers: dict, list_id: str, **params):
    return await client.get(
        f"/v2/shopping-lists/{list_id}/price-summary",
        params=params,
        headers=headers,
    )


def _fixture(name: str) -> dict:
    with (CONTRACTS / "fixtures" / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _contract_required() -> list[str]:
    with (CONTRACTS / "openapi-v2.json").open(encoding="utf-8") as handle:
        spec = json.load(handle)
    return spec["components"]["schemas"]["ShoppingListPriceSummary"]["required"]


async def test_each_line_gets_its_own_lowest_across_the_users_stores(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Butikk A har begge varer til 20 og 30, B har bare den første til 15."""
    owner, headers = await _register(client, db_session, "owner@example.com")
    rema = await _store(db_session, owner, "Rema 1000 Majorstuen")
    kiwi = await _store(db_session, owner, "Kiwi Frogner")
    first = await _product(db_session, owner, "Melk lett 1L")
    second = await _product(db_session, owner, "Brød grovt")
    await _confirm(
        client,
        db_session,
        owner,
        headers,
        store=rema,
        lines=[_line(first, "20.00"), _line(second, "30.00")],
        purchase_date=_days_ago(10),
    )
    await _confirm(
        client,
        db_session,
        owner,
        headers,
        store=kiwi,
        lines=[_line(first, "15.00")],
        purchase_date=_days_ago(5),
    )

    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, user_product_id=str(first.id))
    await _add_item(client, headers, list_id, user_product_id=str(second.id))

    response = await _summary(client, headers, list_id)

    assert response.status_code == 200, response.text
    lines = response.json()["lines"]
    assert [line["status"] for line in lines] == ["historical_lowest", "historical_lowest"]
    assert lines[0]["historical_lowest"]["amount"] == "15.00"
    assert lines[0]["historical_lowest"]["store_name"] == "Kiwi Frogner"
    assert lines[0]["eligible_store_count"] == 2
    assert lines[1]["historical_lowest"]["amount"] == "30.00"
    assert lines[1]["historical_lowest"]["store_name"] == "Rema 1000 Majorstuen"
    assert lines[1]["eligible_store_count"] == 1


async def test_a_free_text_line_says_why_it_has_no_price_and_never_says_zero(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "owner@example.com")
    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, free_text="Melk")

    response = await _summary(client, headers, list_id)

    assert response.status_code == 200, response.text
    line = response.json()["lines"][0]
    assert line["product_id"] is None
    assert line["free_text"] == "Melk"
    assert line["status"] == "no_comparable_price"
    assert line["reason"] == "free_text_no_history"
    assert line["historical_lowest"] is None


async def test_a_product_that_was_never_bought_is_explicit_about_it(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    product = await _product(db_session, owner)
    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, user_product_id=str(product.id))

    response = await _summary(client, headers, list_id)

    line = response.json()["lines"][0]
    assert line["status"] == "no_comparable_price"
    assert line["reason"] == "never_observed"
    assert line["historical_lowest"] is None
    assert line["eligible_store_count"] == 0


async def test_a_purchase_in_a_chain_without_a_branch_is_not_a_comparable_price(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    chain_only = await _store(
        db_session,
        owner,
        "Rema 1000",
        identity_level=StoreIdentityLevel.CHAIN_ONLY.value,
    )
    product = await _product(db_session, owner)
    await _confirm(
        client,
        db_session,
        owner,
        headers,
        store=chain_only,
        lines=[_line(product, "19.90")],
        purchase_date=_days_ago(4),
    )

    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, user_product_id=str(product.id))

    line = (await _summary(client, headers, list_id)).json()["lines"][0]

    assert line["status"] == "no_comparable_price"
    assert line["reason"] == "no_qualified_observation"
    assert line["historical_lowest"] is None


async def test_an_empty_list_has_no_lines(client: AsyncClient, db_session: AsyncSession):
    _, headers = await _register(client, db_session, "owner@example.com")
    list_id = await _new_list(client, headers)

    response = await _summary(client, headers, list_id)

    assert response.status_code == 200, response.text
    assert response.json()["lines"] == []


async def test_a_deleted_line_is_left_out_of_the_summary(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "owner@example.com")
    list_id = await _new_list(client, headers)
    kept = await _add_item(client, headers, list_id, free_text="Melk")
    removed = await _add_item(client, headers, list_id, free_text="Brød")
    deleted = await client.patch(
        f"/v2/shopping-lists/{list_id}/items/{removed['id']}",
        json={
            "mutation_id": str(uuid.uuid4()),
            "expected_version": removed["version"],
            "deleted": True,
        },
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text

    response = await _summary(client, headers, list_id)

    assert [line["item_id"] for line in response.json()["lines"]] == [kept["id"]]


async def test_the_summary_carries_the_same_versions_as_the_list_itself(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Cachen nøkles på `content_revision`; `version` alene overser linjeendringer."""
    _, headers = await _register(client, db_session, "owner@example.com")
    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, free_text="Melk")

    shopping_list = (await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)).json()
    body = (await _summary(client, headers, list_id)).json()

    assert body["list_id"] == list_id
    assert body["list_version"] == shopping_list["version"]
    assert body["content_revision"] == shopping_list["content_revision"]
    assert body["policy_version"] == POLICY_VERSION
    assert body["include_conditional"] is False
    assert isinstance(body["price_data_version"], int)
    assert datetime.fromisoformat(body["calculated_at"]).tzinfo is not None


async def test_adding_a_line_moves_the_content_revision_but_not_the_list_version(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "owner@example.com")
    list_id = await _new_list(client, headers)
    before = (await _summary(client, headers, list_id)).json()

    await _add_item(client, headers, list_id, free_text="Melk")
    after = (await _summary(client, headers, list_id)).json()

    assert after["list_version"] == before["list_version"]
    assert after["content_revision"] > before["content_revision"]


async def test_a_hundred_lines_are_priced_without_a_query_per_line(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Budsjettet er det som skiller batching fra 100 prisoppslag."""
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    products = [
        await _product(db_session, owner, f"Vare {index}") for index in range(LINE_COUNT)
    ]
    await _confirm(
        client,
        db_session,
        owner,
        headers,
        store=store,
        lines=[_line(product, "19.90") for product in products],
        purchase_date=_days_ago(3),
    )

    list_id = await _new_list(client, headers)
    synced = await client.post(
        "/v2/sync",
        json={
            "cursor": None,
            "mutations": [
                {
                    "operation": "item_create",
                    "mutation_id": str(uuid.uuid4()),
                    "list_id": list_id,
                    "user_product_id": str(product.id),
                    "quantity": "1",
                    "quantity_unit": "each",
                }
                for product in products
            ],
        },
        headers=headers,
    )
    assert synced.status_code == 200, synced.text
    assert synced.json()["conflicts"] == []

    with _counted_statements(db_session) as statements:
        response = await _summary(client, headers, list_id)

    assert response.status_code == 200, response.text
    lines = response.json()["lines"]
    assert len(lines) == LINE_COUNT
    assert {line["status"] for line in lines} == {"historical_lowest"}
    # Uten dette ville et budsjett på 15 vært oppfylt av en teller som står stille.
    assert statements, "ingen SQL ble observert; telleren måler ikke noe"
    assert len(statements) < QUERY_BUDGET, "\n".join(statements)


async def test_a_priced_line_says_how_old_the_price_is_and_that_it_may_have_changed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Samme aldersmerking og forbehold som S04-B, og samme minimum."""
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    purchased = _days_ago(40)
    await _confirm(
        client,
        db_session,
        owner,
        headers,
        store=store,
        lines=[_line(product, "24.90")],
        purchase_date=purchased,
    )

    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, user_product_id=str(product.id))

    lowest = (await _summary(client, headers, list_id)).json()["lines"][0]["historical_lowest"]
    detail = (
        await client.get(f"/v2/me/products/{product.id}/prices", headers=headers)
    ).json()["historical_lowest"]

    assert lowest["age_label"] == "eldre observasjon"
    assert lowest["disclaimer"] == DISCLAIMER
    assert lowest["purchase_date"] == purchased
    assert lowest["price_basis"] == "per_package"
    assert lowest["identity_level"] == "branch"
    assert lowest["store_id"] == detail["store_id"]
    assert lowest["amount"] == detail["amount"]
    assert lowest["age_label"] == detail["age_label"]


async def test_free_text_and_products_on_the_same_list_each_get_a_status(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    priced = await _product(db_session, owner, "Melk lett 1L")
    unpriced = await _product(db_session, owner, "Kaffe 500g")
    await _confirm(
        client,
        db_session,
        owner,
        headers,
        store=store,
        lines=[_line(priced, "24.90")],
        purchase_date=_days_ago(3),
    )

    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, user_product_id=str(priced.id), position=0)
    await _add_item(client, headers, list_id, free_text="Bæreposer", position=1)
    await _add_item(client, headers, list_id, user_product_id=str(unpriced.id), position=2)

    lines = (await _summary(client, headers, list_id)).json()["lines"]

    assert [line["status"] for line in lines] == [
        "historical_lowest",
        "no_comparable_price",
        "no_comparable_price",
    ]
    assert [line["reason"] for line in lines] == [
        None,
        "free_text_no_history",
        "never_observed",
    ]
    # Ingen linje uten pris får et beløp, og ingen får null kroner.
    assert "0.00" not in json.dumps([line["historical_lowest"] for line in lines[1:]])


async def test_the_response_carries_every_field_the_contract_promises(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    await _confirm(
        client,
        db_session,
        owner,
        headers,
        store=store,
        lines=[_line(product, "24.90")],
        purchase_date=_days_ago(3),
    )

    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, user_product_id=str(product.id), position=0)
    await _add_item(client, headers, list_id, free_text="Melk", position=1)

    body = (await _summary(client, headers, list_id)).json()

    assert set(_contract_required()) <= set(body)
    fixture = _fixture("shopping-list-price-summary.json")
    for expected, actual in zip(fixture["lines"], body["lines"]):
        assert set(expected) <= set(actual)
        if expected["historical_lowest"] is not None:
            assert set(expected["historical_lowest"]) <= set(actual["historical_lowest"])


async def test_a_conditional_price_is_left_out_unless_it_is_asked_for(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    await _confirm(
        client,
        db_session,
        owner,
        headers,
        store=store,
        lines=[_line(product, "10.00", condition="coupon")],
        purchase_date=_days_ago(8),
    )
    await _confirm(
        client,
        db_session,
        owner,
        headers,
        store=store,
        lines=[_line(product, "25.00")],
        purchase_date=_days_ago(6),
    )

    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, user_product_id=str(product.id))

    default = (await _summary(client, headers, list_id)).json()
    included = (await _summary(client, headers, list_id, include_conditional="true")).json()

    assert default["include_conditional"] is False
    assert default["lines"][0]["historical_lowest"]["amount"] == "25.00"
    assert included["include_conditional"] is True
    assert included["lines"][0]["historical_lowest"]["amount"] == "10.00"


async def test_a_purchase_that_only_exists_on_a_condition_is_not_never_observed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Kjøpet finnes. Grunnen må si at det ikke kan rangeres, ikke at det mangler."""
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _store(db_session, owner)
    product = await _product(db_session, owner)
    await _confirm(
        client,
        db_session,
        owner,
        headers,
        store=store,
        lines=[_line(product, "10.00", condition="coupon")],
        purchase_date=_days_ago(8),
    )

    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, user_product_id=str(product.id))

    line = (await _summary(client, headers, list_id)).json()["lines"][0]

    assert line["status"] == "no_comparable_price"
    assert line["reason"] == "no_qualified_observation"
    assert line["historical_lowest"] is None


async def test_a_pricing_failure_is_a_retryable_error_and_not_an_empty_list(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """En feilet utregning er ikke «ingen data». Listen selv blir ikke utilgjengelig."""
    owner, headers = await _register(client, db_session, "owner@example.com")
    product = await _product(db_session, owner)
    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, user_product_id=str(product.id))

    def broken(*args, **kwargs):
        raise RuntimeError("minimumsberegningen feilet")

    monkeypatch.setattr(summary_service, "historical_lowest", broken)

    response = await _summary(client, headers, list_id)

    assert response.status_code >= 500, response.text
    body = response.json()
    assert body["code"] == "PRICE_SUMMARY_UNAVAILABLE"
    assert body["retryable"] is True
    assert "minimumsberegningen" not in body["message"]

    # Handlelisten står på CRUD-rutene og er upåvirket av at prisen feilet.
    assert (await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)).status_code == 200


async def test_another_users_list_is_not_found(client: AsyncClient, db_session: AsyncSession):
    _, owner_headers = await _register(client, db_session, "owner@example.com")
    list_id = await _new_list(client, owner_headers)
    _, stranger_headers = await _register(client, db_session, "stranger@example.com")

    response = await _summary(client, stranger_headers, list_id)

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


async def test_a_deleted_list_is_not_found(client: AsyncClient, db_session: AsyncSession):
    _, headers = await _register(client, db_session, "owner@example.com")
    list_id = await _new_list(client, headers)
    deleted = await client.patch(
        f"/v2/shopping-lists/{list_id}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "deleted": True},
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text

    response = await _summary(client, headers, list_id)

    assert response.status_code == 404, response.text


async def test_an_unknown_list_is_not_found(client: AsyncClient, db_session: AsyncSession):
    _, headers = await _register(client, db_session, "owner@example.com")

    response = await _summary(client, headers, str(uuid.uuid4()))

    assert response.status_code == 404, response.text

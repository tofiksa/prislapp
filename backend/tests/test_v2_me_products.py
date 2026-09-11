"""S03-A: GET /v2/me/products lister eierens egne varer med stabil paginering."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_product import (
    AliasMatchMethod,
    AliasSource,
    IdentityStatus,
    UserProduct,
    UserProductAlias,
)

pytestmark = pytest.mark.asyncio

PASSWORD = "TestPass123!"
ERROR_KEYS = ("code", "message", "field_errors", "retryable", "request_id")


async def _register(client: AsyncClient, db: AsyncSession, email: str) -> tuple[User, dict]:
    response = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code in (200, 201), response.text
    token = response.json()["access_token"]
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    return user, {"Authorization": f"Bearer {token}"}


async def _product(db: AsyncSession, user: User, display_name: str, **overrides) -> UserProduct:
    product = UserProduct(
        user_id=user.id,
        display_name=display_name,
        pack_unit=overrides.pop("pack_unit", "unknown"),
        identity_status=overrides.pop("identity_status", IdentityStatus.INHERITED.value),
        purchase_count=overrides.pop("purchase_count", 0),
        version=1,
        **overrides,
    )
    db.add(product)
    await db.flush()
    return product


async def _alias(db: AsyncSession, user: User, product: UserProduct, text: str) -> None:
    db.add(
        UserProductAlias(
            user_id=user.id,
            user_product_id=product.id,
            normalized_text=text,
            raw_text=text,
            context_key="",
            source=AliasSource.BACKFILL.value,
            match_method=AliasMatchMethod.INHERITED.value,
        ),
    )
    await db.flush()


async def test_lists_only_the_owners_products(client: AsyncClient, db_session: AsyncSession):
    owner, headers = await _register(client, db_session, "owner@example.com")
    other, _ = await _register(client, db_session, "other@example.com")
    mine = await _product(db_session, owner, "Melk lett 1L")
    await _product(db_session, other, "Melk lett 1L")

    response = await client.get("/v2/me/products", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [str(mine.id)]
    assert body["next_cursor"] is None


async def test_lists_without_search_text(client: AsyncClient, db_session: AsyncSession):
    owner, headers = await _register(client, db_session, "owner@example.com")
    await _product(db_session, owner, "Melk lett 1L")
    await _product(db_session, owner, "Brød grovt")

    response = await client.get("/v2/me/products?q=", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


async def test_query_matches_display_name_and_own_alias(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    milk = await _product(db_session, owner, "Melk lett 1L")
    await _alias(db_session, owner, milk, "melk lett 1l")
    bread = await _product(db_session, owner, "Grovbrød")
    await _alias(db_session, owner, bread, "polarbrod grov")

    by_name = await client.get("/v2/me/products?q=melk", headers=headers)
    by_alias = await client.get("/v2/me/products?q=polarbrod", headers=headers)

    assert [item["id"] for item in by_name.json()["items"]] == [str(milk.id)]
    assert [item["id"] for item in by_alias.json()["items"]] == [str(bread.id)]


async def test_product_fields_follow_the_contract(client: AsyncClient, db_session: AsyncSession):
    owner, headers = await _register(client, db_session, "owner@example.com")
    await _product(
        db_session,
        owner,
        "Melk lett 1L",
        brand="Tine",
        variant="Lett",
        pack_content=Decimal("0.400"),
        pack_unit="kg",
        pack_count=Decimal("2.000"),
        purchase_count=3,
        last_purchased_at=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
    )

    response = await client.get("/v2/me/products", headers=headers)

    (item,) = response.json()["items"]
    assert item["display_name"] == "Melk lett 1L"
    assert item["brand"] == "Tine"
    assert item["variant"] == "Lett"
    assert item["pack_content"] == "0.400"
    assert item["pack_unit"] == "kg"
    assert item["pack_count"] == "2.000"
    assert item["identity_status"] == IdentityStatus.INHERITED.value
    assert item["last_purchased_at"] == "2026-09-01"
    assert item["purchase_count"] == 3
    assert item["version"] == 1


async def test_unknown_pack_values_stay_null(client: AsyncClient, db_session: AsyncSession):
    owner, headers = await _register(client, db_session, "owner@example.com")
    await _product(db_session, owner, "YOGHURT", identity_status=IdentityStatus.UNRESOLVED.value)

    response = await client.get("/v2/me/products", headers=headers)

    (item,) = response.json()["items"]
    assert item["pack_content"] is None
    assert item["pack_count"] is None
    assert item["pack_unit"] == "unknown"
    assert item["last_purchased_at"] is None
    assert item["identity_status"] == IdentityStatus.UNRESOLVED.value


async def test_cursor_pages_fifty_by_default_with_id_as_secondary_sort(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    for _ in range(60):
        await _product(db_session, owner, "Samme navn")

    first = await client.get("/v2/me/products?sort=name", headers=headers)
    first_body = first.json()
    assert len(first_body["items"]) == 50
    assert first_body["next_cursor"]

    second = await client.get(
        f"/v2/me/products?sort=name&cursor={first_body['next_cursor']}",
        headers=headers,
    )
    second_body = second.json()

    assert len(second_body["items"]) == 10
    assert second_body["next_cursor"] is None
    ids = [item["id"] for item in first_body["items"] + second_body["items"]]
    assert len(set(ids)) == 60
    assert ids == sorted(ids)


async def test_page_size_is_capped_at_one_hundred(client: AsyncClient, db_session: AsyncSession):
    owner, headers = await _register(client, db_session, "owner@example.com")
    for index in range(105):
        await _product(db_session, owner, f"Vare {index:03d}")

    response = await client.get("/v2/me/products?sort=name&limit=500", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 100


async def test_sort_recent_puts_newest_first_and_unknown_last(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    old = await _product(
        db_session,
        owner,
        "Gammel",
        last_purchased_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    new = await _product(
        db_session,
        owner,
        "Ny",
        last_purchased_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    unknown = await _product(db_session, owner, "Ukjent dato")

    response = await client.get("/v2/me/products?sort=recent", headers=headers)

    assert [item["id"] for item in response.json()["items"]] == [
        str(new.id),
        str(old.id),
        str(unknown.id),
    ]


async def test_sort_frequent_orders_by_purchase_count(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    rare = await _product(db_session, owner, "Sjelden", purchase_count=1)
    often = await _product(db_session, owner, "Ofte", purchase_count=9)

    response = await client.get("/v2/me/products?sort=frequent", headers=headers)

    assert [item["id"] for item in response.json()["items"]] == [str(often.id), str(rare.id)]


async def test_recent_sort_pages_without_repeating_products(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    for index in range(55):
        await _product(
            db_session,
            owner,
            f"Vare {index:03d}",
            last_purchased_at=datetime(2026, 9, 1, tzinfo=timezone.utc) if index % 2 else None,
        )

    first = await client.get("/v2/me/products?sort=recent", headers=headers)
    cursor = first.json()["next_cursor"]
    second = await client.get(f"/v2/me/products?sort=recent&cursor={cursor}", headers=headers)

    ids = [item["id"] for item in first.json()["items"] + second.json()["items"]]
    assert len(ids) == 55
    assert len(set(ids)) == 55


async def test_another_owners_product_is_not_found(client: AsyncClient, db_session: AsyncSession):
    owner, headers = await _register(client, db_session, "owner@example.com")
    other, _ = await _register(client, db_session, "other@example.com")
    foreign = await _product(db_session, other, "Melk lett 1L")

    response = await client.get(f"/v2/me/products/{foreign.id}", headers=headers)

    assert response.status_code == 404
    body = response.json()
    assert all(key in body for key in ERROR_KEYS)
    assert body["code"] == "NOT_FOUND"
    assert body["retryable"] is False
    assert body["request_id"]
    assert str(foreign.id) not in body["message"]


async def test_own_product_is_returned_by_id(client: AsyncClient, db_session: AsyncSession):
    owner, headers = await _register(client, db_session, "owner@example.com")
    mine = await _product(db_session, owner, "Melk lett 1L")

    response = await client.get(f"/v2/me/products/{mine.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(mine.id)


async def test_unknown_product_id_is_not_found(client: AsyncClient, db_session: AsyncSession):
    _, headers = await _register(client, db_session, "owner@example.com")

    response = await client.get(f"/v2/me/products/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_malformed_product_id_is_not_found(client: AsyncClient, db_session: AsyncSession):
    _, headers = await _register(client, db_session, "owner@example.com")

    response = await client.get("/v2/me/products/ikke-en-uuid", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_invalid_cursor_is_rejected_with_contract_error(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "owner@example.com")

    response = await client.get("/v2/me/products?cursor=tullball", headers=headers)

    assert response.status_code == 400
    body = response.json()
    assert all(key in body for key in ERROR_KEYS)
    assert body["code"] == "INVALID_CURSOR"
    assert [error["field"] for error in body["field_errors"]] == ["cursor"]


async def test_cursor_from_another_sort_order_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    for index in range(55):
        await _product(db_session, owner, f"Vare {index:03d}")

    cursor = (await client.get("/v2/me/products?sort=name", headers=headers)).json()["next_cursor"]
    response = await client.get(f"/v2/me/products?sort=frequent&cursor={cursor}", headers=headers)

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_CURSOR"


async def test_unknown_sort_is_rejected_with_contract_error(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "owner@example.com")

    response = await client.get("/v2/me/products?sort=billigst", headers=headers)

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_SORT"
    assert [error["field"] for error in body["field_errors"]] == ["sort"]


async def test_listing_requires_authentication(client: AsyncClient):
    response = await client.get("/v2/me/products")

    assert response.status_code in (401, 403)

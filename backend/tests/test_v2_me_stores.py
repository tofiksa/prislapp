"""S03-A: GET /v2/me/stores lister eierens egne butikker med filialstatus."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_store import StoreIdentityLevel, UserStore

pytestmark = pytest.mark.asyncio

PASSWORD = "TestPass123!"


async def _register(client: AsyncClient, db: AsyncSession, email: str) -> tuple[User, dict]:
    response = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code in (200, 201), response.text
    token = response.json()["access_token"]
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    return user, {"Authorization": f"Bearer {token}"}


async def _store(db: AsyncSession, user: User, display_name: str, **overrides) -> UserStore:
    store = UserStore(
        user_id=user.id,
        display_name=display_name,
        identity_level=overrides.pop("identity_level", StoreIdentityLevel.UNKNOWN.value),
        version=1,
        **overrides,
    )
    db.add(store)
    await db.flush()
    return store


async def test_lists_only_the_owners_stores(client: AsyncClient, db_session: AsyncSession):
    owner, headers = await _register(client, db_session, "owner@example.com")
    other, _ = await _register(client, db_session, "other@example.com")
    mine = await _store(db_session, owner, "Rema 1000 Grunerlokka")
    await _store(db_session, other, "Rema 1000 Grunerlokka")

    response = await client.get("/v2/me/stores", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [str(mine.id)]
    assert body["next_cursor"] is None


async def test_store_fields_follow_the_contract(client: AsyncClient, db_session: AsyncSession):
    owner, headers = await _register(client, db_session, "owner@example.com")
    await _store(
        db_session,
        owner,
        "Rema 1000 Grunerlokka",
        chain="Rema 1000",
        identity_level=StoreIdentityLevel.CHAIN_ONLY.value,
    )

    response = await client.get("/v2/me/stores", headers=headers)

    (item,) = response.json()["items"]
    assert item["display_name"] == "Rema 1000 Grunerlokka"
    assert item["chain"] == "Rema 1000"
    assert item["branch_name"] is None
    assert item["identity_level"] == StoreIdentityLevel.CHAIN_ONLY.value
    assert item["version"] == 1


async def test_private_ocr_text_is_never_exposed(client: AsyncClient, db_session: AsyncSession):
    owner, headers = await _register(client, db_session, "owner@example.com")
    await _store(db_session, owner, "Rema 1000", raw_ocr_text="REMA 1000 ORG.NR 123")

    response = await client.get("/v2/me/stores", headers=headers)

    assert "raw_ocr_text" not in response.json()["items"][0]
    assert "ORG.NR" not in response.text


async def test_stores_page_with_cursor(client: AsyncClient, db_session: AsyncSession):
    owner, headers = await _register(client, db_session, "owner@example.com")
    for index in range(55):
        await _store(db_session, owner, f"Butikk {index:03d}")

    first = await client.get("/v2/me/stores", headers=headers)
    first_body = first.json()
    assert len(first_body["items"]) == 50

    second = await client.get(
        f"/v2/me/stores?cursor={first_body['next_cursor']}",
        headers=headers,
    )
    second_body = second.json()

    assert len(second_body["items"]) == 5
    assert second_body["next_cursor"] is None
    ids = [item["id"] for item in first_body["items"] + second_body["items"]]
    assert len(set(ids)) == 55


async def test_listing_stores_requires_authentication(client: AsyncClient):
    response = await client.get("/v2/me/stores")

    assert response.status_code in (401, 403)

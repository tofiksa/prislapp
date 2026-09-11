"""S06-A: handlelister på /v2 — eierskap, idempotens, arkiv, slettemarkør og grenser."""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_ledger import AccountLedger
from app.models.user import User
from app.models.user_product import IdentityStatus, UserProduct

pytestmark = pytest.mark.asyncio

PASSWORD = "TestPass123!"
ERROR_KEYS = ("code", "message", "field_errors", "retryable", "request_id")


async def _register(client: AsyncClient, db: AsyncSession, email: str) -> tuple[User, dict]:
    response = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code in (200, 201), response.text
    token = response.json()["access_token"]
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    db.add(AccountLedger(user_id=user.id, price_data_version=1))
    await db.flush()
    return user, {"Authorization": f"Bearer {token}"}


async def _user_product(db: AsyncSession, user: User, name: str = "Melk lett 1L") -> UserProduct:
    product = UserProduct(
        user_id=user.id,
        display_name=name,
        pack_unit="l",
        pack_content=Decimal("1.000"),
        identity_status=IdentityStatus.CONFIRMED.value,
        purchase_count=1,
        version=1,
    )
    db.add(product)
    await db.flush()
    return product


def _list_payload(**overrides) -> dict:
    payload = {"mutation_id": str(uuid.uuid4()), "name": "Ukeshandel"}
    payload.update(overrides)
    return payload


async def _create_list(client: AsyncClient, headers: dict, **overrides):
    return await client.post("/v2/shopping-lists", json=_list_payload(**overrides), headers=headers)


async def test_create_returns_the_list_with_version_one_and_no_items(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")

    response = await _create_list(client, headers, name="Ukeshandel")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Ukeshandel"
    assert body["status"] == "active"
    assert body["version"] == 1
    assert body["deleted"] is False
    assert body["items"] == []


async def test_create_accepts_a_client_generated_id_for_offline_use(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = str(uuid.uuid4())

    response = await _create_list(client, headers, id=list_id)

    assert response.status_code == 201, response.text
    assert response.json()["id"] == list_id


async def test_the_same_mutation_creates_one_list_and_replays_the_first_response(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    payload = _list_payload()

    first = await client.post("/v2/shopping-lists", json=payload, headers=headers)
    second = await client.post("/v2/shopping-lists", json=payload, headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json() == first.json()
    collection = await client.get("/v2/shopping-lists", headers=headers)
    assert len(collection.json()["items"]) == 1


async def test_reusing_a_mutation_id_with_another_name_is_a_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    mutation_id = str(uuid.uuid4())
    await _create_list(client, headers, mutation_id=mutation_id, name="Ukeshandel")

    response = await _create_list(client, headers, mutation_id=mutation_id, name="Helgehandel")

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "MUTATION_CONFLICT"
    assert all(key in body for key in ERROR_KEYS)


async def test_another_owners_mutation_id_does_not_collide(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers_a = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    mutation_id = str(uuid.uuid4())

    await _create_list(client, headers_a, mutation_id=mutation_id, name="A sin liste")
    response = await _create_list(client, headers_b, mutation_id=mutation_id, name="B sin liste")

    assert response.status_code == 201, response.text
    assert response.json()["name"] == "B sin liste"


async def test_user_b_cannot_read_user_a_s_list(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers_a = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    created = await _create_list(client, headers_a)
    list_id = created.json()["id"]

    response = await client.get(f"/v2/shopping-lists/{list_id}", headers=headers_b)

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


async def test_user_b_cannot_write_to_user_a_s_list(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers_a = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    created = await _create_list(client, headers_a)
    list_id = created.json()["id"]

    response = await client.patch(
        f"/v2/shopping-lists/{list_id}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "name": "Kapret"},
        headers=headers_b,
    )

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


async def test_a_list_owned_by_nobody_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")

    response = await client.get(f"/v2/shopping-lists/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


async def test_creating_a_list_requires_a_name(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")

    response = await _create_list(client, headers, name="   ")

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert [error["field"] for error in body["field_errors"]] == ["name"]


async def test_a_taken_list_id_with_a_new_mutation_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = str(uuid.uuid4())
    await _create_list(client, headers, id=list_id)

    response = await _create_list(client, headers, id=list_id, name="Igjen")

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "DUPLICATE_ID"


async def test_listing_lists_is_owner_scoped(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers_a = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    await _create_list(client, headers_a, name="A sin liste")

    response = await client.get("/v2/shopping-lists", headers=headers_b)

    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "next_cursor": None}


async def _patch_list(client: AsyncClient, headers: dict, list_id: str, **fields):
    payload = {"mutation_id": str(uuid.uuid4())}
    payload.update(fields)
    return await client.patch(f"/v2/shopping-lists/{list_id}", json=payload, headers=headers)


async def test_renaming_a_list_bumps_the_version(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = (await _create_list(client, headers)).json()["id"]

    response = await _patch_list(client, headers, list_id, expected_version=1, name="Helgehandel")

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Helgehandel"
    assert response.json()["version"] == 2


async def test_an_archived_list_is_still_readable_with_its_status(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = (await _create_list(client, headers)).json()["id"]

    archived = await _patch_list(client, headers, list_id, expected_version=1, status="archived")

    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"
    fetched = await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "archived"
    collection = await client.get("/v2/shopping-lists", headers=headers)
    assert [item["id"] for item in collection.json()["items"]] == [list_id]


async def test_a_deleted_list_becomes_a_tombstone_that_rest_hides(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = (await _create_list(client, headers)).json()["id"]

    deleted = await _patch_list(client, headers, list_id, expected_version=1, deleted=True)

    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True
    assert deleted.json()["version"] == 2
    assert (await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)).status_code == 404
    collection = await client.get("/v2/shopping-lists", headers=headers)
    assert collection.json()["items"] == []


async def test_a_stale_expected_version_is_a_conflict_with_the_current_version(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = (await _create_list(client, headers)).json()["id"]
    await _patch_list(client, headers, list_id, expected_version=1, name="Helgehandel")

    response = await _patch_list(client, headers, list_id, expected_version=1, name="Tredje")

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "VERSION_CONFLICT"
    assert body["current_version"] == 2
    fetched = await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)
    assert fetched.json()["name"] == "Helgehandel"


async def test_the_same_patch_mutation_is_applied_once(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = (await _create_list(client, headers)).json()["id"]
    payload = {
        "mutation_id": str(uuid.uuid4()),
        "expected_version": 1,
        "name": "Helgehandel",
    }

    first = await client.patch(f"/v2/shopping-lists/{list_id}", json=payload, headers=headers)
    second = await client.patch(f"/v2/shopping-lists/{list_id}", json=payload, headers=headers)

    assert first.status_code == 200, first.text
    assert second.json() == first.json()
    assert second.json()["version"] == 2


async def test_the_default_page_holds_fifty_lists_and_the_next_page_the_rest(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    created = [(await _create_list(client, headers, name=f"Liste {index}")).json()["id"] for index in range(51)]

    first = await client.get("/v2/shopping-lists", headers=headers)
    body = first.json()
    second = await client.get(
        "/v2/shopping-lists",
        params={"cursor": body["next_cursor"]},
        headers=headers,
    )

    assert [item["id"] for item in body["items"]] == created[:50]
    assert body["next_cursor"] is not None
    assert [item["id"] for item in second.json()["items"]] == created[50:]
    assert second.json()["next_cursor"] is None


async def test_the_page_size_is_capped_at_a_hundred(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    for index in range(3):
        await _create_list(client, headers, name=f"Liste {index}")

    response = await client.get("/v2/shopping-lists", params={"limit": 500}, headers=headers)

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 3


async def test_a_garbled_pagination_cursor_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")

    response = await client.get(
        "/v2/shopping-lists",
        params={"cursor": "ikke-en-cursor"},
        headers=headers,
    )

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "INVALID_CURSOR"

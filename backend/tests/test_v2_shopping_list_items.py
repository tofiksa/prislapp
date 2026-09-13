"""S06-A: listelinjer — eierskap, fritekst, eksplisitte felt, grensen på 200 og ingen pris."""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_ledger import AccountLedger
from app.models.product import PriceObservation
from app.models.receipt_revision import PriceObservationV2
from app.models.shopping_list import ShoppingListItem
from app.models.user import User
from app.models.user_product import IdentityStatus, UserProduct

pytestmark = pytest.mark.asyncio

PASSWORD = "TestPass123!"


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


async def _new_list(client: AsyncClient, headers: dict, name: str = "Ukeshandel") -> str:
    response = await client.post(
        "/v2/shopping-lists",
        json={"mutation_id": str(uuid.uuid4()), "name": name},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _item_payload(**overrides) -> dict:
    payload = {
        "mutation_id": str(uuid.uuid4()),
        "free_text": "Melk",
        "quantity": "1",
        "quantity_unit": "each",
    }
    payload.update(overrides)
    return payload


async def _add_item(client: AsyncClient, headers: dict, list_id: str, **overrides):
    return await client.post(
        f"/v2/shopping-lists/{list_id}/items",
        json=_item_payload(**overrides),
        headers=headers,
    )


async def _patch_item(client: AsyncClient, headers: dict, list_id: str, item_id: str, **fields):
    payload = {"mutation_id": str(uuid.uuid4())}
    payload.update(fields)
    return await client.patch(
        f"/v2/shopping-lists/{list_id}/items/{item_id}",
        json=payload,
        headers=headers,
    )


async def test_adding_a_known_product_keeps_the_quantity_as_a_decimal_string(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    product = await _user_product(db_session, user)
    list_id = await _new_list(client, headers)

    response = await _add_item(
        client,
        headers,
        list_id,
        free_text=None,
        user_product_id=str(product.id),
        quantity="2",
        quantity_unit="each",
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user_product_id"] == str(product.id)
    assert body["free_text"] is None
    assert body["quantity"] == "2.000"
    assert body["quantity_unit"] == "each"
    assert body["checked"] is False
    assert body["position"] == 0
    assert body["version"] == 1
    assert body["deleted"] is False


async def test_a_free_text_line_needs_no_price_history(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)

    response = await _add_item(client, headers, list_id, free_text="Melk til lørdag")

    assert response.status_code == 201, response.text
    assert response.json()["user_product_id"] is None
    assert response.json()["free_text"] == "Melk til lørdag"


async def test_free_text_is_not_merged_into_a_known_product_line(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    product = await _user_product(db_session, user, name="Melk")
    list_id = await _new_list(client, headers)
    await _add_item(
        client,
        headers,
        list_id,
        free_text=None,
        user_product_id=str(product.id),
    )

    response = await _add_item(client, headers, list_id, free_text="Melk")

    assert response.status_code == 201, response.text
    fetched = await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)
    items = fetched.json()["items"]
    assert len(items) == 2
    assert [item["position"] for item in items] == [0, 1]


async def test_a_line_cannot_be_both_a_product_and_free_text(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    product = await _user_product(db_session, user)
    list_id = await _new_list(client, headers)

    response = await _add_item(
        client,
        headers,
        list_id,
        user_product_id=str(product.id),
        free_text="Melk",
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["field_errors"][0]["code"] == "product_or_free_text"


async def test_a_line_needs_either_a_product_or_free_text(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)

    response = await _add_item(client, headers, list_id, free_text=None)

    assert response.status_code == 400, response.text
    assert response.json()["field_errors"][0]["code"] == "product_or_free_text"


async def test_another_owners_product_id_in_the_body_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user_a, headers_a = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    product_of_a = await _user_product(db_session, user_a)
    list_of_b = await _new_list(client, headers_b)

    response = await _add_item(
        client,
        headers_b,
        list_of_b,
        free_text=None,
        user_product_id=str(product_of_a.id),
    )

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"
    count = await db_session.scalar(select(func.count()).select_from(ShoppingListItem))
    assert count == 0


async def test_an_unknown_product_id_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)

    response = await _add_item(
        client,
        headers,
        list_id,
        free_text=None,
        user_product_id=str(uuid.uuid4()),
    )

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


async def test_adding_to_another_owners_list_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers_a = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    list_of_a = await _new_list(client, headers_a)

    response = await _add_item(client, headers_b, list_of_a)

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


async def test_the_same_add_mutation_creates_one_line(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    payload = _item_payload()

    first = await client.post(
        f"/v2/shopping-lists/{list_id}/items",
        json=payload,
        headers=headers,
    )
    second = await client.post(
        f"/v2/shopping-lists/{list_id}/items",
        json=payload,
        headers=headers,
    )

    assert first.status_code == 201, first.text
    assert second.json() == first.json()
    fetched = await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)
    assert len(fetched.json()["items"]) == 1


async def test_the_same_add_mutation_on_another_list_is_a_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    first_list = await _new_list(client, headers, name="Ukeshandel")
    second_list = await _new_list(client, headers, name="Helgehandel")
    payload = _item_payload()
    await client.post(f"/v2/shopping-lists/{first_list}/items", json=payload, headers=headers)

    response = await client.post(
        f"/v2/shopping-lists/{second_list}/items",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "MUTATION_CONFLICT"


async def test_an_archived_list_does_not_take_new_lines(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    await client.patch(
        f"/v2/shopping-lists/{list_id}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "status": "archived"},
        headers=headers,
    )

    response = await _add_item(client, headers, list_id)

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "LIST_ARCHIVED"


async def test_a_deleted_list_is_not_revived_by_a_new_line(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    await client.patch(
        f"/v2/shopping-lists/{list_id}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "deleted": True},
        headers=headers,
    )

    response = await _add_item(client, headers, list_id)

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "LIST_DELETED"
    count = await db_session.scalar(select(func.count()).select_from(ShoppingListItem))
    assert count == 0


async def test_changing_the_quantity_bumps_the_line_version(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    item_id = (await _add_item(client, headers, list_id)).json()["id"]

    response = await _patch_item(
        client,
        headers,
        list_id,
        item_id,
        expected_version=1,
        quantity="2.5",
    )

    assert response.status_code == 200, response.text
    assert response.json()["quantity"] == "2.500"
    assert response.json()["version"] == 2


async def test_checking_a_line_is_an_explicit_value_not_a_toggle(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    item_id = (await _add_item(client, headers, list_id)).json()["id"]
    await _patch_item(client, headers, list_id, item_id, expected_version=1, checked=True)

    retried = await _patch_item(
        client,
        headers,
        list_id,
        item_id,
        expected_version=2,
        checked=True,
    )

    assert retried.status_code == 200, retried.text
    assert retried.json()["checked"] is True


async def test_deleting_a_line_hides_it_from_the_list(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    item_id = (await _add_item(client, headers, list_id)).json()["id"]

    response = await _patch_item(
        client,
        headers,
        list_id,
        item_id,
        expected_version=1,
        deleted=True,
    )

    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True
    fetched = await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)
    assert fetched.json()["items"] == []
    # Slettemarkøren blir stående, slik at sync kan fortelle om sletting.
    stored = await db_session.scalar(
        select(ShoppingListItem.deleted_at).where(ShoppingListItem.id == uuid.UUID(item_id)),
    )
    assert stored is not None


async def test_a_deleted_line_is_not_revived_by_a_later_edit(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    item_id = (await _add_item(client, headers, list_id)).json()["id"]
    await _patch_item(client, headers, list_id, item_id, expected_version=1, deleted=True)

    response = await _patch_item(
        client,
        headers,
        list_id,
        item_id,
        expected_version=2,
        quantity="5",
    )

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "ITEM_DELETED"
    fetched = await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)
    assert fetched.json()["items"] == []


async def test_a_line_can_be_moved_to_an_explicit_position(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    first = (await _add_item(client, headers, list_id, free_text="Melk")).json()["id"]
    await _add_item(client, headers, list_id, free_text="Brød")

    response = await _patch_item(client, headers, list_id, first, expected_version=1, position=5)

    assert response.status_code == 200, response.text
    assert response.json()["position"] == 5
    fetched = await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)
    assert [item["free_text"] for item in fetched.json()["items"]] == ["Brød", "Melk"]


async def test_a_stale_line_version_does_not_overwrite_the_server_quantity(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    item_id = (await _add_item(client, headers, list_id)).json()["id"]
    await _patch_item(client, headers, list_id, item_id, expected_version=1, quantity="4")

    response = await _patch_item(
        client,
        headers,
        list_id,
        item_id,
        expected_version=1,
        quantity="9",
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "VERSION_CONFLICT"
    assert body["current_version"] == 2
    fetched = await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)
    assert fetched.json()["items"][0]["quantity"] == "4.000"


async def test_another_owner_cannot_patch_a_line(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers_a = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    list_of_a = await _new_list(client, headers_a)
    item_of_a = (await _add_item(client, headers_a, list_of_a)).json()["id"]

    response = await _patch_item(
        client,
        headers_b,
        list_of_a,
        item_of_a,
        expected_version=1,
        checked=True,
    )

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


async def test_a_quantity_must_be_positive(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)

    response = await _add_item(client, headers, list_id, quantity="0")

    assert response.status_code == 400, response.text
    assert response.json()["field_errors"][0]["code"] == "not_positive"


async def test_a_quantity_keeps_at_most_three_decimals(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)

    response = await _add_item(client, headers, list_id, quantity="0.0005")

    assert response.status_code == 400, response.text
    assert response.json()["field_errors"][0]["code"] == "too_many_decimals"


async def test_a_quantity_must_be_a_decimal_string(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)

    response = await client.post(
        f"/v2/shopping-lists/{list_id}/items",
        json={
            "mutation_id": str(uuid.uuid4()),
            "free_text": "Melk",
            "quantity": 1.5,
            "quantity_unit": "each",
        },
        headers=headers,
    )

    assert response.status_code == 422, response.text


async def _seed_items(db: AsyncSession, user: User, list_id: str, count: int) -> None:
    for position in range(count):
        db.add(
            ShoppingListItem(
                user_id=user.id,
                list_id=uuid.UUID(list_id),
                free_text=f"Vare {position}",
                quantity=Decimal("1.000"),
                quantity_unit="each",
                position=position,
                version=1,
                sync_seq=0,
            ),
        )
    await db.commit()


async def test_the_two_hundred_and_first_active_line_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    await _seed_items(db_session, user, list_id, 200)

    response = await _add_item(client, headers, list_id, free_text="Vare 200")

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "LIST_ITEM_LIMIT"
    assert body["field_errors"][0]["field"] == "items"
    # Utkastet til brukeren er ikke skrevet, og de 200 linjene står urørt.
    count = await db_session.scalar(select(func.count()).select_from(ShoppingListItem))
    assert count == 200


async def test_a_deleted_line_frees_room_under_the_limit(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    await _seed_items(db_session, user, list_id, 200)
    first = await db_session.scalar(
        select(ShoppingListItem.id).where(ShoppingListItem.position == 0),
    )
    await _patch_item(client, headers, list_id, str(first), expected_version=1, deleted=True)

    response = await _add_item(client, headers, list_id, free_text="Vare 200")

    assert response.status_code == 201, response.text


async def test_checking_a_line_creates_no_price_observation(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    product = await _user_product(db_session, user)
    list_id = await _new_list(client, headers)
    item_id = (
        await _add_item(
            client,
            headers,
            list_id,
            free_text=None,
            user_product_id=str(product.id),
        )
    ).json()["id"]

    await _patch_item(client, headers, list_id, item_id, expected_version=1, checked=True)

    assert await db_session.scalar(select(func.count()).select_from(PriceObservation)) == 0
    assert await db_session.scalar(select(func.count()).select_from(PriceObservationV2)) == 0
    ledger = await db_session.scalar(
        select(AccountLedger.price_data_version).where(AccountLedger.user_id == user.id),
    )
    assert ledger == 1

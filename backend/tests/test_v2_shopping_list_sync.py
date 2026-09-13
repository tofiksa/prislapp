"""S06-A: /v2/sync — inkrementell sync, slettemarkører, konflikter og utløpt markør."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_ledger import AccountLedger
from app.models.product import PriceObservation
from app.models.receipt_revision import PriceObservationV2
from app.models.shopping_list import ShoppingList, ShoppingListItem, ShoppingListStatus
from app.models.user import User
from app.models.user_product import IdentityStatus, UserProduct
from app.services.shopping_list_service import ShoppingListService, encode_sync_cursor

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


async def _add_item(client: AsyncClient, headers: dict, list_id: str, text: str = "Melk") -> str:
    response = await client.post(
        f"/v2/shopping-lists/{list_id}/items",
        json={
            "mutation_id": str(uuid.uuid4()),
            "free_text": text,
            "quantity": "1",
            "quantity_unit": "each",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _sync(client: AsyncClient, headers: dict, cursor: str | None = None, mutations=None):
    response = await client.post(
        "/v2/sync",
        json={"cursor": cursor, "mutations": mutations or []},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _item_patch(list_id: str, item_id: str, expected_version: int, **fields) -> dict:
    mutation = {
        "operation": "item_patch",
        "mutation_id": str(uuid.uuid4()),
        "list_id": list_id,
        "item_id": item_id,
        "expected_version": expected_version,
    }
    mutation.update(fields)
    return mutation


async def test_the_first_sync_without_a_cursor_is_a_full_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id)

    body = await _sync(client, headers)

    assert body["full_snapshot"] is True
    assert body["cursor"]
    assert body["price_data_version"] == 1
    assert body["replaced_product_ids"] == []
    assert body["conflicts"] == []
    assert [item["id"] for item in body["lists"]] == [list_id]
    assert len(body["lists"][0]["items"]) == 1


async def test_an_incremental_sync_returns_only_what_changed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    await _new_list(client, headers, name="Ukeshandel")
    cursor = (await _sync(client, headers))["cursor"]
    second = await _new_list(client, headers, name="Helgehandel")

    body = await _sync(client, headers, cursor=cursor)

    assert body["full_snapshot"] is False
    assert [item["id"] for item in body["lists"]] == [second]


async def test_a_sync_without_changes_returns_no_lists(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    await _new_list(client, headers)
    cursor = (await _sync(client, headers))["cursor"]

    body = await _sync(client, headers, cursor=cursor)

    assert body["lists"] == []
    assert body["full_snapshot"] is False


async def test_a_changed_line_brings_its_list_with_only_that_line(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, text="Melk")
    second_item = await _add_item(client, headers, list_id, text="Brød")
    cursor = (await _sync(client, headers))["cursor"]

    body = await _sync(
        client,
        headers,
        cursor=cursor,
        mutations=[_item_patch(list_id, second_item, 1, checked=True)],
    )

    assert [item["id"] for item in body["lists"]] == [list_id]
    items = body["lists"][0]["items"]
    assert [item["id"] for item in items] == [second_item]
    assert items[0]["checked"] is True


async def test_sync_applies_patches_to_two_different_lines(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    first = await _add_item(client, headers, list_id, text="Melk")
    second = await _add_item(client, headers, list_id, text="Brød")
    cursor = (await _sync(client, headers))["cursor"]

    body = await _sync(
        client,
        headers,
        cursor=cursor,
        mutations=[
            _item_patch(list_id, first, 1, quantity="3"),
            _item_patch(list_id, second, 1, checked=True),
        ],
    )

    assert body["conflicts"] == []
    items = {item["id"]: item for item in body["lists"][0]["items"]}
    assert items[first]["quantity"] == "3.000"
    assert items[first]["version"] == 2
    assert items[second]["checked"] is True


async def test_a_conflicting_line_does_not_overwrite_the_server_quantity(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    item_id = await _add_item(client, headers, list_id)
    cursor = (await _sync(client, headers))["cursor"]
    await client.patch(
        f"/v2/shopping-lists/{list_id}/items/{item_id}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "quantity": "4"},
        headers=headers,
    )

    body = await _sync(
        client,
        headers,
        cursor=cursor,
        mutations=[_item_patch(list_id, item_id, 1, quantity="9")],
    )

    assert len(body["conflicts"]) == 1
    conflict = body["conflicts"][0]
    assert conflict["code"] == "VERSION_CONFLICT"
    assert conflict["operation"] == "item_patch"
    assert conflict["local"]["quantity"] == "9"
    assert conflict["server"]["quantity"] == "4.000"
    assert conflict["server"]["version"] == 2
    stored = await db_session.scalar(
        select(ShoppingListItem.quantity).where(ShoppingListItem.id == uuid.UUID(item_id)),
    )
    assert stored == Decimal("4.000")


async def test_a_conflict_does_not_block_the_rest_of_the_batch(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    stale = await _add_item(client, headers, list_id, text="Melk")
    fresh = await _add_item(client, headers, list_id, text="Brød")
    cursor = (await _sync(client, headers))["cursor"]
    await client.patch(
        f"/v2/shopping-lists/{list_id}/items/{stale}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "quantity": "4"},
        headers=headers,
    )

    body = await _sync(
        client,
        headers,
        cursor=cursor,
        mutations=[
            _item_patch(list_id, stale, 1, quantity="9"),
            _item_patch(list_id, fresh, 1, checked=True),
        ],
    )

    assert [conflict["code"] for conflict in body["conflicts"]] == ["VERSION_CONFLICT"]
    applied = await db_session.scalar(
        select(ShoppingListItem.checked).where(ShoppingListItem.id == uuid.UUID(fresh)),
    )
    assert applied is True


async def test_an_expired_cursor_gives_a_full_snapshot_without_replaying(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    item_id = await _add_item(client, headers, list_id)
    expired = encode_sync_cursor(
        user.id,
        1,
        issued_at=datetime.now(timezone.utc) - timedelta(days=91),
    )

    body = await _sync(
        client,
        headers,
        cursor=expired,
        mutations=[_item_patch(list_id, item_id, 1, checked=True)],
    )

    assert body["full_snapshot"] is True
    assert [conflict["code"] for conflict in body["conflicts"]] == ["CURSOR_EXPIRED"]
    # Ingenting avspilles før klienten har avklart de lokale endringene.
    checked = await db_session.scalar(
        select(ShoppingListItem.checked).where(ShoppingListItem.id == uuid.UUID(item_id)),
    )
    assert checked is False


async def test_a_garbled_cursor_gives_a_full_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    await _new_list(client, headers)

    body = await _sync(client, headers, cursor="ikke-en-cursor")

    assert body["full_snapshot"] is True
    assert len(body["lists"]) == 1


async def test_another_accounts_cursor_gives_a_full_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers_a = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    await _new_list(client, headers_a, name="A sin liste")
    cursor_of_b = (await _sync(client, headers_b))["cursor"]

    body = await _sync(client, headers_a, cursor=cursor_of_b)

    assert body["full_snapshot"] is True
    assert len(body["lists"]) == 1


async def test_a_deleted_list_is_delivered_as_a_tombstone(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    cursor = (await _sync(client, headers))["cursor"]
    await client.patch(
        f"/v2/shopping-lists/{list_id}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "deleted": True},
        headers=headers,
    )

    body = await _sync(client, headers, cursor=cursor)

    assert [item["id"] for item in body["lists"]] == [list_id]
    assert body["lists"][0]["deleted"] is True


async def test_a_deleted_line_is_delivered_as_a_tombstone(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    item_id = await _add_item(client, headers, list_id)
    cursor = (await _sync(client, headers))["cursor"]
    await client.patch(
        f"/v2/shopping-lists/{list_id}/items/{item_id}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "deleted": True},
        headers=headers,
    )

    body = await _sync(client, headers, cursor=cursor)

    items = body["lists"][0]["items"]
    assert [item["id"] for item in items] == [item_id]
    assert items[0]["deleted"] is True


async def test_an_archived_list_keeps_its_status_in_sync(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    cursor = (await _sync(client, headers))["cursor"]
    await client.patch(
        f"/v2/shopping-lists/{list_id}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "status": "archived"},
        headers=headers,
    )

    body = await _sync(client, headers, cursor=cursor)

    assert body["lists"][0]["status"] == "archived"
    assert body["lists"][0]["deleted"] is False


async def test_a_local_edit_does_not_revive_a_deleted_server_list(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    item_id = await _add_item(client, headers, list_id)
    cursor = (await _sync(client, headers))["cursor"]
    await client.patch(
        f"/v2/shopping-lists/{list_id}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "deleted": True},
        headers=headers,
    )

    body = await _sync(
        client,
        headers,
        cursor=cursor,
        mutations=[_item_patch(list_id, item_id, 1, quantity="7")],
    )

    conflict = body["conflicts"][0]
    assert conflict["code"] == "LIST_DELETED"
    assert conflict["local"]["quantity"] == "7"
    assert conflict["server"]["deleted"] is True
    stored = await db_session.scalar(
        select(ShoppingList.deleted_at).where(ShoppingList.id == uuid.UUID(list_id)),
    )
    assert stored is not None


async def test_a_local_edit_on_an_archived_list_is_a_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    item_id = await _add_item(client, headers, list_id)
    cursor = (await _sync(client, headers))["cursor"]
    await client.patch(
        f"/v2/shopping-lists/{list_id}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "status": "archived"},
        headers=headers,
    )

    body = await _sync(
        client,
        headers,
        cursor=cursor,
        mutations=[_item_patch(list_id, item_id, 1, quantity="7")],
    )

    assert body["conflicts"][0]["code"] == "LIST_ARCHIVED"
    stored = await db_session.scalar(
        select(ShoppingListItem.quantity).where(ShoppingListItem.id == uuid.UUID(item_id)),
    )
    assert stored == Decimal("1.000")


async def test_sync_creates_a_list_offline_and_only_once(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = str(uuid.uuid4())
    mutation = {
        "operation": "list_create",
        "mutation_id": str(uuid.uuid4()),
        "id": list_id,
        "name": "Offline-liste",
    }

    first = await _sync(client, headers, mutations=[mutation])
    second = await _sync(client, headers, cursor=first["cursor"], mutations=[mutation])

    assert [item["id"] for item in first["lists"]] == [list_id]
    assert first["conflicts"] == []
    assert second["conflicts"] == []
    count = await db_session.scalar(select(func.count()).select_from(ShoppingList))
    assert count == 1


async def test_sync_adds_a_line_with_a_client_id(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    product = await _user_product(db_session, user)
    list_id = await _new_list(client, headers)
    cursor = (await _sync(client, headers))["cursor"]
    item_id = str(uuid.uuid4())

    body = await _sync(
        client,
        headers,
        cursor=cursor,
        mutations=[
            {
                "operation": "item_create",
                "mutation_id": str(uuid.uuid4()),
                "list_id": list_id,
                "id": item_id,
                "user_product_id": str(product.id),
                "quantity": "2",
                "quantity_unit": "each",
            },
        ],
    )

    assert body["conflicts"] == []
    items = body["lists"][0]["items"]
    assert [item["id"] for item in items] == [item_id]
    assert items[0]["quantity"] == "2.000"


async def test_reusing_a_mutation_id_for_other_content_is_a_conflict_in_sync(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    first_item = await _add_item(client, headers, list_id, text="Melk")
    second_item = await _add_item(client, headers, list_id, text="Brød")
    cursor = (await _sync(client, headers))["cursor"]
    mutation_id = str(uuid.uuid4())
    await _sync(
        client,
        headers,
        cursor=cursor,
        mutations=[
            {
                "operation": "item_patch",
                "mutation_id": mutation_id,
                "list_id": list_id,
                "item_id": first_item,
                "expected_version": 1,
                "quantity": "3",
            },
        ],
    )

    body = await _sync(
        client,
        headers,
        cursor=cursor,
        mutations=[
            {
                "operation": "item_patch",
                "mutation_id": mutation_id,
                "list_id": list_id,
                "item_id": second_item,
                "expected_version": 1,
                "quantity": "3",
            },
        ],
    )

    assert body["conflicts"][0]["code"] == "MUTATION_CONFLICT"
    untouched = await db_session.scalar(
        select(ShoppingListItem.quantity).where(ShoppingListItem.id == uuid.UUID(second_item)),
    )
    assert untouched == Decimal("1.000")


async def test_another_owners_product_in_a_sync_mutation_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user_a, _ = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    product_of_a = await _user_product(db_session, user_a)
    list_of_b = await _new_list(client, headers_b)
    cursor = (await _sync(client, headers_b))["cursor"]

    body = await _sync(
        client,
        headers_b,
        cursor=cursor,
        mutations=[
            {
                "operation": "item_create",
                "mutation_id": str(uuid.uuid4()),
                "list_id": list_of_b,
                "user_product_id": str(product_of_a.id),
                "quantity": "1",
                "quantity_unit": "each",
            },
        ],
    )

    assert body["conflicts"][0]["code"] == "NOT_FOUND"
    count = await db_session.scalar(select(func.count()).select_from(ShoppingListItem))
    assert count == 0


async def test_another_owners_list_in_a_sync_mutation_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers_a = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    list_of_a = await _new_list(client, headers_a)
    cursor = (await _sync(client, headers_b))["cursor"]

    body = await _sync(
        client,
        headers_b,
        cursor=cursor,
        mutations=[
            {
                "operation": "list_patch",
                "mutation_id": str(uuid.uuid4()),
                "list_id": list_of_a,
                "expected_version": 1,
                "name": "Kapret",
            },
        ],
    )

    assert body["conflicts"][0]["code"] == "NOT_FOUND"
    assert body["lists"] == []
    name = await db_session.scalar(
        select(ShoppingList.name).where(ShoppingList.id == uuid.UUID(list_of_a)),
    )
    assert name == "Ukeshandel"


async def test_the_line_limit_holds_in_sync_too(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    for position in range(200):
        db_session.add(
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
    await db_session.commit()
    cursor = (await _sync(client, headers))["cursor"]

    body = await _sync(
        client,
        headers,
        cursor=cursor,
        mutations=[
            {
                "operation": "item_create",
                "mutation_id": str(uuid.uuid4()),
                "list_id": list_id,
                "free_text": "Vare 200",
                "quantity": "1",
                "quantity_unit": "each",
            },
        ],
    )

    assert body["conflicts"][0]["code"] == "LIST_ITEM_LIMIT"
    count = await db_session.scalar(select(func.count()).select_from(ShoppingListItem))
    assert count == 200


async def test_syncing_a_checked_line_creates_no_price_observation(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    product = await _user_product(db_session, user)
    list_id = await _new_list(client, headers)
    cursor = (await _sync(client, headers))["cursor"]

    body = await _sync(
        client,
        headers,
        cursor=cursor,
        mutations=[
            {
                "operation": "item_create",
                "mutation_id": str(uuid.uuid4()),
                "list_id": list_id,
                "user_product_id": str(product.id),
                "quantity": "1",
                "quantity_unit": "each",
                "checked": True,
            },
        ],
    )

    assert body["price_data_version"] == 1
    assert await db_session.scalar(select(func.count()).select_from(PriceObservation)) == 0
    assert await db_session.scalar(select(func.count()).select_from(PriceObservationV2)) == 0
    ledger = await db_session.scalar(
        select(AccountLedger.price_data_version).where(AccountLedger.user_id == user.id),
    )
    assert ledger == 1


def _commit_from_another_device(monkeypatch, name: str) -> uuid.UUID:
    """Lar en annen enhet committe rett etter at denne synken har lest listene.

    Markøren som svaret bærer må derfor ikke dekke den sekvensen: den ble aldri
    levert. Å levere for mye neste gang er ufarlig, å hoppe over er det ikke.
    """
    other_id = uuid.uuid4()
    original = ShoppingListService._sync_lists
    done = False

    async def racing_sync_lists(self, user_id, changed_since):
        nonlocal done
        lists = await original(self, user_id, changed_since)
        if not done:
            done = True
            sequence = await self._next_sequence(user_id)
            now = datetime.now(timezone.utc)
            self.db.add(
                ShoppingList(
                    id=other_id,
                    user_id=user_id,
                    name=name,
                    status=ShoppingListStatus.ACTIVE.value,
                    version=1,
                    content_seq=sequence,
                    created_at=now,
                    updated_at=now,
                ),
            )
            await self.db.commit()
        return lists

    monkeypatch.setattr(ShoppingListService, "_sync_lists", racing_sync_lists)
    return other_id


async def test_a_cursor_never_covers_a_change_the_client_did_not_get(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _, headers = await _register(client, db_session, "a@example.com")
    await _new_list(client, headers)
    cursor = (await _sync(client, headers))["cursor"]
    other_id = _commit_from_another_device(monkeypatch, "Fra en annen enhet")

    raced = await _sync(client, headers, cursor=cursor)
    monkeypatch.undo()
    body = await _sync(client, headers, cursor=raced["cursor"])

    # Den andre enhetens liste kom ikke med i `raced`, så neste sync må ha den.
    assert [item["id"] for item in raced["lists"]] == []
    assert [item["id"] for item in body["lists"]] == [str(other_id)]


async def test_a_full_snapshot_cursor_never_covers_an_undelivered_change(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _, headers = await _register(client, db_session, "a@example.com")
    first = await _new_list(client, headers)
    other_id = _commit_from_another_device(monkeypatch, "Fra en annen enhet")

    snapshot = await _sync(client, headers)
    monkeypatch.undo()
    body = await _sync(client, headers, cursor=snapshot["cursor"])

    assert [item["id"] for item in snapshot["lists"]] == [first]
    assert [item["id"] for item in body["lists"]] == [str(other_id)]

"""S06-D: kopier liste og kvittering-til-liste på /v2."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_ledger import AccountLedger
from app.models.product import PriceObservation
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_item import ReceiptItem
from app.models.receipt_revision import PriceObservationV2
from app.models.shopping_list import ShoppingListItem
from app.models.user import User
from app.models.user_product import IdentityStatus, UserProduct
from app.models.user_store import StoreIdentityLevel, UserStore
from app.models.store import Store

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


async def _user_store(db: AsyncSession, user: User) -> UserStore:
    store = Store(name="Rema 1000 Torshov", normalized_name="rema 1000 torshov", chain="rema1000")
    db.add(store)
    await db.flush()
    user_store = UserStore(
        user_id=user.id,
        legacy_store_id=store.id,
        display_name="Rema 1000 Torshov",
        chain="rema1000",
        branch_name="Torshov",
        identity_level=StoreIdentityLevel.BRANCH.value,
        version=1,
    )
    db.add(user_store)
    await db.flush()
    return user_store


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


async def _copy(client: AsyncClient, headers: dict, list_id: str, **overrides):
    payload = {"mutation_id": str(uuid.uuid4())}
    payload.update(overrides)
    return await client.post(f"/v2/shopping-lists/{list_id}/copy", json=payload, headers=headers)


async def _from_receipt(client: AsyncClient, headers: dict, **overrides):
    payload = {"mutation_id": str(uuid.uuid4())}
    payload.update(overrides)
    return await client.post("/v2/shopping-lists/from-receipt", json=payload, headers=headers)


async def _ready_receipt(db: AsyncSession, user: User) -> Receipt:
    receipt = Receipt(
        user_id=user.id,
        status=ReceiptStatus.READY_FOR_REVIEW.value,
        image_path=f"{user.id}/receipt.jpg",
        image_expires_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
    )
    db.add(receipt)
    await db.flush()
    return receipt


def _line(**overrides) -> dict:
    line = {
        "id": str(uuid.uuid4()),
        "raw_product_name": "MELK LETT 1L",
        "quantity": "1",
        "quantity_unit": "each",
        "line_type": "product",
        "net_line_total": "25.00",
        "printed_unit_price": "25.00",
        "condition": "none",
    }
    line.update(overrides)
    return line


def _confirm_payload(**overrides) -> dict:
    payload = {
        "expected_version": 0,
        "mutation_id": str(uuid.uuid4()),
        "purchase_date": "2026-09-01",
        "date_precision": "date",
        "printed_total": "25.00",
        "lines": [_line()],
    }
    payload.update(overrides)
    return payload


async def _observation_counts(db: AsyncSession) -> tuple[int, int]:
    v1 = await db.scalar(select(func.count()).select_from(PriceObservation))
    v2 = await db.scalar(select(func.count()).select_from(PriceObservationV2))
    return int(v1 or 0), int(v2 or 0)


async def test_copy_creates_new_ids_unchecked_and_leaves_the_source_untouched(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    product = await _user_product(db_session, user)
    list_id = await _new_list(client, headers)
    first = await _add_item(
        client,
        headers,
        list_id,
        free_text=None,
        user_product_id=str(product.id),
        quantity="2",
        quantity_unit="each",
    )
    second = await _add_item(client, headers, list_id, free_text="Brød", quantity="1")
    await client.patch(
        f"/v2/shopping-lists/{list_id}/items/{first.json()['id']}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "checked": True},
        headers=headers,
    )
    await client.patch(
        f"/v2/shopping-lists/{list_id}/items/{second.json()['id']}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "deleted": True},
        headers=headers,
    )
    source_before = (await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)).json()

    response = await _copy(client, headers, list_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] != list_id
    assert body["status"] == "active"
    assert [item["checked"] for item in body["items"]] == [False]
    assert [item["id"] for item in body["items"]] != [first.json()["id"]]
    assert body["items"][0]["user_product_id"] == str(product.id)
    assert body["items"][0]["quantity"] == "2.000"
    assert all(item["id"] != first.json()["id"] for item in body["items"])
    source_after = (await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)).json()
    assert source_after["items"] == source_before["items"]
    assert source_after["id"] == list_id


async def test_copy_unchecked_only_skips_checked_source_lines(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    keep = await _add_item(client, headers, list_id, free_text="Brød")
    drop = await _add_item(client, headers, list_id, free_text="Melk")
    await client.patch(
        f"/v2/shopping-lists/{list_id}/items/{drop.json()['id']}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "checked": True},
        headers=headers,
    )

    response = await _copy(client, headers, list_id, unchecked_only=True)

    assert response.status_code == 201, response.text
    items = response.json()["items"]
    assert [item["free_text"] for item in items] == ["Brød"]
    assert items[0]["id"] != keep.json()["id"]
    assert items[0]["checked"] is False


async def test_copy_of_an_archived_list_works(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, free_text="Melk")
    await client.patch(
        f"/v2/shopping-lists/{list_id}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "status": "archived"},
        headers=headers,
    )

    response = await _copy(client, headers, list_id, name="Neste tur")

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "active"
    assert response.json()["name"] == "Neste tur"
    assert response.json()["id"] != list_id
    archived = await client.get(f"/v2/shopping-lists/{list_id}", headers=headers)
    assert archived.json()["status"] == "archived"


async def test_copy_of_a_foreign_or_deleted_list_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers_a = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    list_of_a = await _new_list(client, headers_a)
    deleted = await _new_list(client, headers_a, name="Slettes")
    await client.patch(
        f"/v2/shopping-lists/{deleted}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "deleted": True},
        headers=headers_a,
    )

    foreign = await _copy(client, headers_b, list_of_a)
    missing = await _copy(client, headers_a, deleted)

    assert foreign.status_code == 404, foreign.text
    assert foreign.json()["code"] == "NOT_FOUND"
    assert all(key in foreign.json() for key in ERROR_KEYS)
    assert missing.status_code == 404, missing.text
    assert missing.json()["code"] == "NOT_FOUND"


async def test_the_same_copy_mutation_replays_the_original_response(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    await _add_item(client, headers, list_id, free_text="Melk")
    payload = {"mutation_id": str(uuid.uuid4()), "name": "Kopi"}

    first = await client.post(f"/v2/shopping-lists/{list_id}/copy", json=payload, headers=headers)
    second = await client.post(f"/v2/shopping-lists/{list_id}/copy", json=payload, headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json() == first.json()
    collection = await client.get("/v2/shopping-lists", headers=headers)
    copies = [item for item in collection.json()["items"] if item["id"] != list_id]
    assert len(copies) == 1

    conflict = await client.post(
        f"/v2/shopping-lists/{list_id}/copy",
        json={"mutation_id": payload["mutation_id"], "name": "Annen kopi"},
        headers=headers,
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "MUTATION_CONFLICT"
    assert all(key in conflict.json() for key in ERROR_KEYS)


async def test_copy_that_would_exceed_the_item_limit_creates_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user, headers = await _register(client, db_session, "a@example.com")
    list_id = await _new_list(client, headers)
    now = datetime.now(timezone.utc)
    for index in range(201):
        db_session.add(
            ShoppingListItem(
                user_id=user.id,
                list_id=uuid.UUID(list_id),
                free_text=f"Vare {index}",
                quantity=Decimal("1.000"),
                quantity_unit="each",
                position=index,
                version=1,
                sync_seq=index + 1,
                created_at=now,
                updated_at=now,
            ),
        )
    await db_session.flush()

    response = await _copy(client, headers, list_id)

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "LIST_ITEM_LIMIT"
    assert all(key in body for key in ERROR_KEYS)
    assert body["field_errors"]
    collection = await client.get("/v2/shopping-lists", headers=headers)
    assert [item["id"] for item in collection.json()["items"]] == [list_id]


async def test_from_receipt_copies_products_skips_fees_and_does_not_insert_observations(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _user_store(db_session, owner)
    product = await _user_product(db_session, owner)
    receipt = await _ready_receipt(db_session, owner)
    payload = _confirm_payload(
        store_id=str(store.id),
        printed_total="27.50",
        lines=[
            _line(user_product_id=str(product.id), net_line_total="25.00"),
            _line(
                raw_product_name="PANT",
                line_type="deposit",
                net_line_total="2.50",
                printed_unit_price="2.50",
                user_product_id=None,
            ),
            _line(
                raw_product_name="POSE",
                line_type="fee",
                net_line_total="1.00",
                printed_unit_price="1.00",
                user_product_id=None,
            ),
            _line(
                raw_product_name="RABATT",
                line_type="discount",
                net_line_total="-1.00",
                printed_unit_price="-1.00",
                user_product_id=None,
            ),
            _line(
                raw_product_name="RETUR",
                line_type="return",
                net_line_total="0.00",
                printed_unit_price="0.00",
                user_product_id=None,
            ),
            _line(
                raw_product_name="UKJENT",
                line_type="unknown",
                net_line_total="25.00",
                user_product_id=None,
            ),
        ],
    )
    confirmed = await client.post(
        f"/v2/receipts/{receipt.id}/confirm",
        json=payload,
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    before = await _observation_counts(db_session)

    response = await _from_receipt(
        client,
        headers,
        receipt_id=str(receipt.id),
        name="Fra kvittering",
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "active"
    assert body["name"] == "Fra kvittering"
    assert [item["checked"] for item in body["items"]] == [False]
    assert [item["user_product_id"] for item in body["items"]] == [str(product.id)]
    assert body["items"][0]["free_text"] is None
    assert await _observation_counts(db_session) == before


async def test_from_receipt_missing_or_foreign_product_becomes_free_text(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    other, _ = await _register(client, db_session, "other@example.com")
    store = await _user_store(db_session, owner)
    later_foreign = await _user_product(db_session, owner, name="Slettet vare")
    receipt = await _ready_receipt(db_session, owner)
    payload = _confirm_payload(
        store_id=str(store.id),
        printed_total="50.00",
        lines=[
            _line(raw_product_name="UTEN ID", user_product_id=None, net_line_total="25.00"),
            _line(
                raw_product_name="SLETTET VARE",
                user_product_id=str(later_foreign.id),
                net_line_total="25.00",
            ),
        ],
    )
    confirmed = await client.post(
        f"/v2/receipts/{receipt.id}/confirm",
        json=payload,
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    later_foreign.user_id = other.id
    await db_session.flush()

    response = await _from_receipt(client, headers, receipt_id=str(receipt.id))

    assert response.status_code == 201, response.text
    items = response.json()["items"]
    assert [item["user_product_id"] for item in items] == [None, None]
    assert [item["free_text"] for item in items] == ["UTEN ID", "SLETTET VARE"]
    assert all(item["checked"] is False for item in items)


async def test_from_receipt_with_only_fees_creates_an_empty_list(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _user_store(db_session, owner)
    receipt = await _ready_receipt(db_session, owner)
    payload = _confirm_payload(
        store_id=str(store.id),
        printed_total="2.50",
        lines=[
            _line(
                raw_product_name="PANT",
                line_type="deposit",
                net_line_total="2.50",
                printed_unit_price="2.50",
                user_product_id=None,
            ),
        ],
    )
    confirmed = await client.post(
        f"/v2/receipts/{receipt.id}/confirm",
        json=payload,
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text

    response = await _from_receipt(client, headers, receipt_id=str(receipt.id))

    assert response.status_code == 201, response.text
    assert response.json()["items"] == []
    assert response.json()["status"] == "active"


async def test_from_receipt_falls_back_to_v1_items_without_mapping_global_ids(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = Receipt(
        user_id=owner.id,
        status=ReceiptStatus.CONFIRMED.value,
        image_path=f"{owner.id}/v1.jpg",
        image_expires_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
        version=0,
    )
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(
        ReceiptItem(
            receipt_id=receipt.id,
            raw_product_name="V1 MELK",
            quantity=Decimal("2"),
            line_total=Decimal("25.00"),
            line_type="product",
            quantity_unit="each",
        ),
    )
    db_session.add(
        ReceiptItem(
            receipt_id=receipt.id,
            raw_product_name="PANT",
            quantity=Decimal("1"),
            line_total=Decimal("2.50"),
            line_type="deposit",
        ),
    )
    await db_session.flush()

    response = await _from_receipt(client, headers, receipt_id=str(receipt.id))

    assert response.status_code == 201, response.text
    items = response.json()["items"]
    assert [item["free_text"] for item in items] == ["V1 MELK"]
    assert items[0]["user_product_id"] is None
    assert items[0]["quantity"] == "2.000"
    assert items[0]["quantity_unit"] == "each"


async def test_user_b_cannot_copy_user_a_s_receipt(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers_a = await _register(client, db_session, "a@example.com")
    _, headers_b = await _register(client, db_session, "b@example.com")
    store = await _user_store(db_session, owner)
    product = await _user_product(db_session, owner)
    receipt = await _ready_receipt(db_session, owner)
    confirmed = await client.post(
        f"/v2/receipts/{receipt.id}/confirm",
        json=_confirm_payload(store_id=str(store.id), lines=[_line(user_product_id=str(product.id))]),
        headers=headers_a,
    )
    assert confirmed.status_code == 200, confirmed.text

    response = await _from_receipt(client, headers_b, receipt_id=str(receipt.id))

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"
    collection = await client.get("/v2/shopping-lists", headers=headers_b)
    assert collection.json()["items"] == []


async def test_unconfirmed_receipt_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "a@example.com")
    receipt = await _ready_receipt(db_session, owner)

    response = await _from_receipt(client, headers, receipt_id=str(receipt.id))

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


async def test_the_same_from_receipt_mutation_is_applied_once(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "a@example.com")
    store = await _user_store(db_session, owner)
    product = await _user_product(db_session, owner)
    receipt = await _ready_receipt(db_session, owner)
    confirmed = await client.post(
        f"/v2/receipts/{receipt.id}/confirm",
        json=_confirm_payload(store_id=str(store.id), lines=[_line(user_product_id=str(product.id))]),
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    payload = {"receipt_id": str(receipt.id), "mutation_id": str(uuid.uuid4()), "name": "Igjen"}

    first = await client.post("/v2/shopping-lists/from-receipt", json=payload, headers=headers)
    second = await client.post("/v2/shopping-lists/from-receipt", json=payload, headers=headers)

    assert first.status_code == 201, first.text
    assert second.json() == first.json()
    collection = await client.get("/v2/shopping-lists", headers=headers)
    assert len(collection.json()["items"]) == 1


async def test_copy_and_from_receipt_create_no_price_observations(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "a@example.com")
    store = await _user_store(db_session, owner)
    product = await _user_product(db_session, owner)
    list_id = await _new_list(client, headers)
    item = await _add_item(
        client,
        headers,
        list_id,
        free_text=None,
        user_product_id=str(product.id),
    )
    await client.patch(
        f"/v2/shopping-lists/{list_id}/items/{item.json()['id']}",
        json={"mutation_id": str(uuid.uuid4()), "expected_version": 1, "checked": True},
        headers=headers,
    )
    receipt = await _ready_receipt(db_session, owner)
    confirmed = await client.post(
        f"/v2/receipts/{receipt.id}/confirm",
        json=_confirm_payload(store_id=str(store.id), lines=[_line(user_product_id=str(product.id))]),
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    after_confirm = await _observation_counts(db_session)

    copied = await _copy(client, headers, list_id)
    from_receipt = await _from_receipt(client, headers, receipt_id=str(receipt.id))

    assert copied.status_code == 201, copied.text
    assert from_receipt.status_code == 201, from_receipt.text
    assert await _observation_counts(db_session) == after_confirm

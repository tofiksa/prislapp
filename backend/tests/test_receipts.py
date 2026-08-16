from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_item import ReceiptItem
from app.models.store import Store
from app.models.user import User
from app.services.receipt_service import ReceiptService


@pytest.fixture(autouse=True)
def mock_storage_and_celery():
    with (
        patch("app.services.receipt_service.StorageService") as mock_storage_cls,
        patch("app.routers.receipts.process_receipt") as mock_task,
        patch("app.worker.tasks.StorageService") as mock_worker_storage_cls,
    ):
        mock_storage = MagicMock()
        mock_storage.upload_receipt.return_value = "test/path.jpg"
        mock_storage.download_receipt.return_value = b"fake-image-bytes"
        mock_storage_cls.return_value = mock_storage
        mock_worker_storage_cls.return_value = mock_storage
        mock_task.delay = MagicMock()
        yield mock_task


async def _create_ready_receipt(db: AsyncSession, user: User) -> Receipt:
    store = Store(name="Rema 1000 Test", normalized_name="rema 1000 test", chain="Rema 1000")
    db.add(store)
    await db.flush()

    receipt = Receipt(
        user_id=user.id,
        store_id=store.id,
        status=ReceiptStatus.READY_FOR_REVIEW.value,
        image_path="user/receipt.jpg",
        image_expires_at=datetime.now(timezone.utc),
        total=Decimal("50.00"),
        purchase_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
    )
    db.add(receipt)
    await db.flush()

    db.add(
        ReceiptItem(
            receipt_id=receipt.id,
            raw_product_name="Melk 1L",
            quantity=Decimal("1"),
            unit_price=Decimal("25.00"),
            line_total=Decimal("25.00"),
        ),
    )
    db.add(
        ReceiptItem(
            receipt_id=receipt.id,
            raw_product_name="Brød",
            quantity=Decimal("1"),
            unit_price=Decimal("25.00"),
            line_total=Decimal("25.00"),
        ),
    )
    await db.commit()
    await db.refresh(receipt)
    return receipt


@pytest.mark.asyncio
async def test_upload_and_get_receipt(client: AsyncClient):
    register = await client.post(
        "/auth/register",
        json={"email": "receipt@example.com", "password": "TestPass123!"},
    )
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    upload = await client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.jpg", b"fake-jpeg-content", "image/jpeg")},
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["status"] == "UPLOADED"
    receipt_id = body["id"]

    detail = await client.get(f"/receipts/{receipt_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == receipt_id
    assert detail.json()["status"] == "UPLOADED"

    listing = await client.get("/receipts", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == receipt_id


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient):
    response = await client.post(
        "/receipts",
        files={"file": ("receipt.jpg", b"fake-jpeg-content", "image/jpeg")},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_receipt_not_found(client: AsyncClient):
    register = await client.post(
        "/auth/register",
        json={"email": "missing@example.com", "password": "TestPass123!"},
    )
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get(
        "/receipts/00000000-0000-0000-0000-000000000099",
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_confirm_receipt(client: AsyncClient, db_session: AsyncSession):
    register = await client.post(
        "/auth/register",
        json={"email": "confirm@example.com", "password": "TestPass123!"},
    )
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == "confirm@example.com"))
    user = result.scalar_one()
    receipt = await _create_ready_receipt(db_session, user)

    response = await client.put(
        f"/receipts/{receipt.id}/confirm",
        headers=headers,
        json={
            "store_name": "Rema 1000 Test",
            "total": "52.00",
            "items": [
                {
                    "raw_product_name": "Melk 1L",
                    "quantity": "1",
                    "unit_price": "27.00",
                    "line_total": "27.00",
                },
                {
                    "raw_product_name": "Brød",
                    "quantity": "1",
                    "unit_price": "25.00",
                    "line_total": "25.00",
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CONFIRMED"
    assert body["total"] == "52.00"
    assert len(body["items"]) == 2


@pytest.mark.asyncio
async def test_confirm_then_search_and_my_prices(client: AsyncClient, db_session: AsyncSession):
    register = await client.post(
        "/auth/register",
        json={"email": "prices@example.com", "password": "TestPass123!"},
    )
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == "prices@example.com"))
    user = result.scalar_one()
    receipt = await _create_ready_receipt(db_session, user)

    confirm = await client.put(
        f"/receipts/{receipt.id}/confirm",
        headers=headers,
        json={
            "store_name": "Rema 1000 Test",
            "items": [
                {
                    "raw_product_name": "Melk 1L",
                    "quantity": "1",
                    "line_total": "25.00",
                },
            ],
        },
    )
    assert confirm.status_code == 200

    search = await client.get("/products/search?q=melk", headers=headers)
    assert search.status_code == 200
    products = search.json()["items"]
    assert len(products) == 1
    product_id = products[0]["id"]

    prices = await client.get(f"/products/{product_id}/my-prices", headers=headers)
    assert prices.status_code == 200
    body = prices.json()
    assert body["cheapest"]["price"] == "25.00"
    assert len(body["observations"]) == 1

    stores = await client.get("/stores", headers=headers)
    assert stores.status_code == 200
    assert len(stores.json()["items"]) == 1


@pytest.mark.asyncio
async def test_delete_receipt(client: AsyncClient, db_session: AsyncSession):
    register = await client.post(
        "/auth/register",
        json={"email": "delete@example.com", "password": "TestPass123!"},
    )
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == "delete@example.com"))
    user = result.scalar_one()
    receipt = await _create_ready_receipt(db_session, user)

    response = await client.delete(f"/receipts/{receipt.id}", headers=headers)
    assert response.status_code == 204

    detail = await client.get(f"/receipts/{receipt.id}", headers=headers)
    assert detail.status_code == 404

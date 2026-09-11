import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt
from app.services.storage_service import StorageService
from tests.test_phase23 import account, image_bytes


@pytest.fixture(autouse=True)
def mock_storage_and_celery():
    with (
        patch.object(StorageService, "upload_receipt", return_value="test/path.jpg"),
        patch.object(StorageService, "download_receipt", return_value=b"fake-image-bytes"),
        patch("app.routers.receipts.process_receipt") as mock_task,
    ):
        mock_task.delay = MagicMock()
        yield


@pytest.mark.asyncio
async def test_owner_can_download_receipt_image(client: AsyncClient):
    headers, _ = await account(client, "owner-image@example.com")
    upload = await client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.jpg", image_bytes(), "image/jpeg")},
    )
    assert upload.status_code == 201
    receipt_id = upload.json()["id"]

    response = await client.get(f"/receipts/{receipt_id}/image", headers=headers)
    assert response.status_code == 200
    assert response.content == b"fake-image-bytes"
    assert response.headers["content-type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_other_user_gets_404_for_receipt_image(client: AsyncClient):
    headers_a, _ = await account(client, "owner-a@example.com")
    headers_b, _ = await account(client, "other-b@example.com")
    upload = await client.post(
        "/receipts",
        headers=headers_a,
        files={"file": ("receipt.jpg", image_bytes(), "image/jpeg")},
    )
    receipt_id = upload.json()["id"]

    response = await client.get(f"/receipts/{receipt_id}/image", headers=headers_b)
    assert response.status_code == 404
    assert response.json()["detail"] == "Receipt not found"


@pytest.mark.asyncio
async def test_empty_image_path_returns_410(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await account(client, "empty-path@example.com")
    upload = await client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.jpg", image_bytes(), "image/jpeg")},
    )
    receipt_id = upload.json()["id"]

    receipt = await db_session.get(Receipt, uuid.UUID(receipt_id))
    receipt.image_path = ""
    await db_session.commit()

    response = await client.get(f"/receipts/{receipt_id}/image", headers=headers)
    assert response.status_code == 410
    assert response.json()["detail"] == "Original image expired"


@pytest.mark.asyncio
async def test_receipt_image_requires_auth(client: AsyncClient):
    response = await client.get("/receipts/00000000-0000-0000-0000-000000000001/image")
    assert response.status_code == 401

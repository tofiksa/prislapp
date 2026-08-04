from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


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

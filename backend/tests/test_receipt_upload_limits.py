"""S02-C: filgrenser, formatmetadata og idempotens med SHA-256 payload-hash."""

from __future__ import annotations

import hashlib
import uuid
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_outbox import JobOutbox
from app.models.receipt import Receipt
from app.models.user import User
from tests.test_phase23 import image_bytes

ERROR_KEYS = ("code", "message", "field_errors", "retryable", "request_id")


@pytest.fixture(autouse=True)
def mock_storage_and_celery():
    with (
        patch("app.services.receipt_service.StorageService") as mock_storage_cls,
        patch("app.services.ocr_outbox.deliver_ocr_job") as mock_task,
        patch("app.worker.tasks.StorageService") as mock_worker_storage_cls,
    ):
        mock_storage = MagicMock()
        mock_storage.upload_receipt.return_value = "test/path.jpg"
        mock_storage.download_receipt.return_value = b"fake-image-bytes"
        mock_storage_cls.return_value = mock_storage
        mock_worker_storage_cls.return_value = mock_storage
        yield mock_task


async def _register(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": "TestPass123!"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _jpeg(size: tuple[int, int], color: str = "white") -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="JPEG")
    return output.getvalue()


def _png(size: tuple[int, int]) -> bytes:
    output = BytesIO()
    Image.new("L", size, 0).save(output, format="PNG")
    return output.getvalue()


def _assert_c00(response, *, status_code: int, code: str) -> dict:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(ERROR_KEYS) <= set(body)
    assert body["code"] == code
    assert body["retryable"] is False
    assert body["request_id"]
    assert "ocr" not in body["message"].lower()
    return body


async def _count(db: AsyncSession, model) -> int:
    result = await db.execute(select(func.count()).select_from(model))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_same_key_and_same_bytes_replay_one_receipt_and_one_outbox(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await _register(client, "replay@example.com")
    key = str(uuid.uuid4())
    payload = image_bytes()
    files = {"file": ("receipt.jpg", payload, "image/jpeg")}
    upload_headers = {**headers, "Idempotency-Key": key}

    first = await client.post("/receipts", headers=upload_headers, files=files)
    second = await client.post("/receipts", headers=upload_headers, files=files)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == second.json()["status"]

    receipt_id = uuid.UUID(first.json()["id"])
    receipt = await db_session.get(Receipt, receipt_id)
    assert receipt is not None
    digest = hashlib.sha256(payload).hexdigest()
    assert getattr(receipt, "payload_hash", None) == digest
    assert len(digest) == 64

    jobs = list(
        (
            await db_session.execute(
                select(JobOutbox).where(JobOutbox.aggregate_id == receipt_id),
            )
        ).scalars(),
    )
    assert len(jobs) == 1
    assert await _count(db_session, Receipt) == 1


@pytest.mark.asyncio
async def test_same_key_and_different_bytes_returns_409_and_leaves_original(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await _register(client, "conflict@example.com")
    key = str(uuid.uuid4())
    first_payload = _jpeg((24, 24), "white")
    second_payload = _jpeg((24, 24), "black")
    upload_headers = {**headers, "Idempotency-Key": key}

    first = await client.post(
        "/receipts",
        headers=upload_headers,
        files={"file": ("a.jpg", first_payload, "image/jpeg")},
    )
    assert first.status_code == 201
    receipt_id = uuid.UUID(first.json()["id"])
    original = await db_session.get(Receipt, receipt_id)
    assert original is not None
    original_status = original.status
    original_hash = getattr(original, "payload_hash", None)

    conflict = await client.post(
        "/receipts",
        headers=upload_headers,
        files={"file": ("b.jpg", second_payload, "image/jpeg")},
    )
    _assert_c00(conflict, status_code=409, code="IDEMPOTENCY_CONFLICT")

    leftover = await db_session.get(Receipt, receipt_id)
    assert leftover is not None
    assert leftover.status == original_status
    assert getattr(leftover, "payload_hash", None) == original_hash
    assert leftover.image_path == original.image_path
    assert await _count(db_session, Receipt) == 1
    jobs = list(
        (
            await db_session.execute(
                select(JobOutbox).where(JobOutbox.aggregate_id == receipt_id),
            )
        ).scalars(),
    )
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_side_over_12000_px_is_rejected_before_ocr(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await _register(client, "wide@example.com")
    payload = _jpeg((12_001, 8), "white")

    response = await client.post(
        "/receipts",
        headers=headers,
        files={"file": ("wide.jpg", payload, "image/jpeg")},
    )
    body = _assert_c00(response, status_code=413, code="IMAGE_DIMENSIONS")
    assert body["field_errors"]

    assert await _count(db_session, Receipt) == 0
    assert await _count(db_session, JobOutbox) == 0
    assert await _count(db_session, User) == 1


@pytest.mark.asyncio
async def test_pixel_count_over_40_million_is_rejected_before_ocr(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await _register(client, "pixels@example.com")
    payload = _png((10_001, 4_000))

    response = await client.post(
        "/receipts",
        headers=headers,
        files={"file": ("huge.png", payload, "image/png")},
    )
    body = _assert_c00(response, status_code=413, code="IMAGE_TOO_LARGE")
    assert body["field_errors"]

    assert await _count(db_session, Receipt) == 0
    assert await _count(db_session, JobOutbox) == 0


@pytest.mark.asyncio
async def test_upload_without_key_still_stores_payload_hash(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await _register(client, "nokey@example.com")
    payload = image_bytes()

    response = await client.post(
        "/receipts",
        headers=headers,
        files={"file": ("receipt.jpg", payload, "image/jpeg")},
    )
    assert response.status_code == 201
    receipt = await db_session.get(Receipt, uuid.UUID(response.json()["id"]))
    assert receipt is not None
    assert getattr(receipt, "payload_hash", None) == hashlib.sha256(payload).hexdigest()
    assert getattr(receipt, "image_width", None) == 20
    assert getattr(receipt, "image_height", None) == 20
    assert getattr(receipt, "content_type", None) == "image/jpeg"

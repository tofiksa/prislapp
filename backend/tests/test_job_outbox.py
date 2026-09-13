"""S10-B: transaksjonell OCR-outbox, fencing, reconciler og readiness."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.product import PriceObservation
from app.models.receipt import Receipt, ReceiptStatus
from app.models.user import User
from app.services.receipt_service import ReceiptService
from tests.fixtures.rema1000_ocr import REMA1000_SAMPLE_OCR
from tests.test_phase23 import image_bytes


@pytest.fixture(autouse=True)
def mock_storage():
    with (
        patch("app.services.receipt_service.StorageService") as mock_storage_cls,
        patch("app.worker.tasks.StorageService") as mock_worker_storage_cls,
    ):
        mock_storage = MagicMock()
        mock_storage.upload_receipt.return_value = "test/path.jpg"
        mock_storage.download_receipt.return_value = b"fake-image-bytes"
        mock_storage_cls.return_value = mock_storage
        mock_worker_storage_cls.return_value = mock_storage
        yield mock_storage


async def _register(client: AsyncClient, email: str) -> tuple[dict[str, str], str]:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": "TestPass123!"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, email


async def _user_by_email(db: AsyncSession, email: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one()


async def _outbox_for(db: AsyncSession, receipt_id: UUID):
    from app.models.job_outbox import JobOutbox

    result = await db.execute(
        select(JobOutbox).where(JobOutbox.aggregate_id == receipt_id),
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_outbox_insert_rolls_back_with_the_receipt(db_session: AsyncSession):
    from app.models.job_outbox import JobOutbox
    from app.services.ocr_outbox import enqueue_ocr_job

    user = User(email="outbox-tx@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    receipt = Receipt(
        user_id=user.id,
        status=ReceiptStatus.UPLOADED.value,
        image_path="user/receipt.jpg",
        image_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(receipt)
    await db_session.flush()
    await enqueue_ocr_job(db_session, user.id, receipt.id)
    await db_session.flush()
    await db_session.rollback()

    assert await db_session.get(Receipt, receipt.id) is None
    leftover = await db_session.execute(select(JobOutbox))
    assert leftover.scalars().all() == []


@pytest.mark.asyncio
async def test_create_receipt_inserts_pending_or_published_outbox(
    client: AsyncClient,
    db_session: AsyncSession,
):
    from app.models.job_outbox import JobOutboxStatus

    headers, email = await _register(client, "outbox-create@example.com")
    user = await _user_by_email(db_session, email)

    with patch("app.services.ocr_outbox.deliver_ocr_job"):
        upload = await client.post(
            "/receipts",
            headers=headers,
            files={"file": ("receipt.jpg", image_bytes(), "image/jpeg")},
        )

    assert upload.status_code == 201
    receipt_id = UUID(upload.json()["id"])
    jobs = await _outbox_for(db_session, receipt_id)
    assert len(jobs) == 1
    assert jobs[0].job_type == "ocr_process"
    assert jobs[0].aggregate_type == "receipt"
    assert jobs[0].user_id == user.id
    assert jobs[0].status in {
        JobOutboxStatus.PENDING.value,
        JobOutboxStatus.PUBLISHED.value,
    }


@pytest.mark.asyncio
async def test_publish_failure_after_commit_leaves_pending_outbox_and_receipt(
    client: AsyncClient,
    db_session: AsyncSession,
):
    from app.models.job_outbox import JobOutboxStatus

    headers, email = await _register(client, "outbox-redis-down@example.com")
    user = await _user_by_email(db_session, email)

    with patch(
        "app.services.ocr_outbox.deliver_ocr_job",
        side_effect=ConnectionError("redis down"),
    ):
        upload = await client.post(
            "/receipts",
            headers=headers,
            files={"file": ("receipt.jpg", image_bytes(), "image/jpeg")},
        )

    assert upload.status_code == 201
    receipt_id = UUID(upload.json()["id"])
    stored = await db_session.get(Receipt, receipt_id)
    assert stored is not None
    assert stored.user_id == user.id

    jobs = await _outbox_for(db_session, receipt_id)
    assert len(jobs) == 1
    assert jobs[0].status == JobOutboxStatus.PENDING.value


@pytest.mark.asyncio
async def test_reconciler_publishes_pending_jobs_and_worker_can_run(
    client: AsyncClient,
    db_session: AsyncSession,
):
    from app.models.job_outbox import JobOutboxStatus
    from app.services.ocr_outbox import reconcile_job_outbox
    from app.worker.tasks import process_receipt_with_db

    headers, _email = await _register(client, "outbox-reconcile@example.com")

    with patch(
        "app.services.ocr_outbox.deliver_ocr_job",
        side_effect=ConnectionError("redis down"),
    ):
        upload = await client.post(
            "/receipts",
            headers=headers,
            files={"file": ("receipt.jpg", image_bytes(), "image/jpeg")},
        )
    receipt_id = UUID(upload.json()["id"])

    with patch("app.services.ocr_outbox.deliver_ocr_job") as deliver:
        published = await reconcile_job_outbox(db_session, min_age_seconds=0)

    assert published >= 1
    deliver.assert_called()
    jobs = await _outbox_for(db_session, receipt_id)
    assert jobs[0].status == JobOutboxStatus.PUBLISHED.value

    with patch("app.worker.tasks.OcrService") as mock_ocr_cls:
        mock_ocr_cls.return_value.extract_text.return_value = REMA1000_SAMPLE_OCR
        await process_receipt_with_db(str(receipt_id), db_session)

    receipt = await db_session.get(Receipt, receipt_id)
    await db_session.refresh(receipt)
    assert receipt.status == ReceiptStatus.READY_FOR_REVIEW.value
    jobs = await _outbox_for(db_session, receipt_id)
    assert jobs[0].status == JobOutboxStatus.DONE.value


@pytest.mark.asyncio
async def test_stale_attempt_does_not_write_parsed_receipt_twice(db_session: AsyncSession):
    from app.models.job_outbox import JobOutbox, JobOutboxStatus
    from app.services.ocr_outbox import claim_ocr_job, complete_ocr_result

    user = User(email="fence@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    service = ReceiptService(db_session)
    receipt = await service.create_receipt(user, b"image-bytes", "image/jpeg")

    first = await claim_ocr_job(db_session, receipt.id)
    assert first is not None

    job = await db_session.get(JobOutbox, first.outbox_id)
    job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()

    second = await claim_ocr_job(db_session, receipt.id)
    assert second is not None
    assert second.attempt_id != first.attempt_id

    from app.models.receipt_item import ReceiptItem

    items = [
        {
            "raw_product_name": "Melk",
            "quantity": 1,
            "unit_price": None,
            "line_total": 10,
        }
    ]
    await complete_ocr_result(
        db_session,
        receipt.id,
        first.attempt_id,
        "x",
        None,
        None,
        None,
        items,
    )
    stale_count = (
        await db_session.scalar(
            select(ReceiptItem.id).where(ReceiptItem.receipt_id == receipt.id),
        )
    )
    stale_status = await db_session.scalar(
        select(Receipt.status).where(Receipt.id == receipt.id),
    )
    assert stale_status != ReceiptStatus.READY_FOR_REVIEW.value
    assert stale_count is None

    await complete_ocr_result(
        db_session,
        receipt.id,
        second.attempt_id,
        "x",
        None,
        None,
        None,
        items,
    )

    saved_count = await db_session.scalar(
        select(ReceiptItem.id).where(ReceiptItem.receipt_id == receipt.id),
    )
    ready_status = await db_session.scalar(
        select(Receipt.status).where(Receipt.id == receipt.id),
    )
    assert ready_status == ReceiptStatus.READY_FOR_REVIEW.value
    assert saved_count is not None
    jobs = await _outbox_for(db_session, receipt.id)
    assert jobs[0].status == JobOutboxStatus.DONE.value
    assert jobs[0].attempt_id == second.attempt_id


_STALE_ITEMS = [
    {
        "raw_product_name": "Melk",
        "quantity": 1,
        "unit_price": None,
        "line_total": 10,
    }
]


def _session_for_same_db(session: AsyncSession) -> AsyncSession:
    maker = async_sessionmaker(
        session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return maker()


async def _claim_a_then_reclaim_b_on_other_session(session1: AsyncSession, email: str):
    from app.models.job_outbox import JobOutbox
    from app.services.ocr_outbox import claim_ocr_job

    user = User(email=email, password_hash="hash")
    session1.add(user)
    await session1.commit()
    await session1.refresh(user)

    receipt = await ReceiptService(session1).create_receipt(
        user, b"image-bytes", "image/jpeg",
    )
    first = await claim_ocr_job(session1, receipt.id)
    assert first is not None

    cached = await session1.get(JobOutbox, first.outbox_id)
    # SQLite returns naive datetimes; a past timestamptz cannot be compared
    # to aware `now` in claim. Clearing the lease is the reclaimable state.
    cached.lease_expires_at = None
    await session1.commit()
    assert cached.attempt_id == first.attempt_id

    async with _session_for_same_db(session1) as session2:
        second = await claim_ocr_job(session2, receipt.id)
        assert second is not None
        assert second.attempt_id != first.attempt_id

    # Worker session still holds the pre-reclaim row (expire_on_commit=False).
    assert cached.attempt_id == first.attempt_id
    return receipt, first, second, cached


async def _committed_outbox_and_receipt(db: AsyncSession, outbox_id, receipt_id):
    from app.models.job_outbox import JobOutbox

    db.expire_all()
    job = await db.get(JobOutbox, outbox_id)
    stored = await db.get(Receipt, receipt_id)
    return job, stored


@pytest.mark.asyncio
async def test_stale_session_complete_does_not_overwrite_newer_claim(
    db_session: AsyncSession,
):
    from app.models.job_outbox import JobOutboxStatus
    from app.models.receipt_item import ReceiptItem
    from app.services.ocr_outbox import complete_ocr_result

    receipt, first, second, cached = await _claim_a_then_reclaim_b_on_other_session(
        db_session, "stale-session-complete@example.com",
    )
    assert cached.attempt_id == first.attempt_id

    wrote = await complete_ocr_result(
        db_session,
        receipt.id,
        first.attempt_id,
        "x",
        None,
        None,
        None,
        _STALE_ITEMS,
    )
    assert wrote is False

    job, stored = await _committed_outbox_and_receipt(
        db_session, first.outbox_id, receipt.id,
    )
    item_id = await db_session.scalar(
        select(ReceiptItem.id).where(ReceiptItem.receipt_id == receipt.id),
    )

    assert stored.status != ReceiptStatus.READY_FOR_REVIEW.value
    assert stored.status == ReceiptStatus.PROCESSING.value
    assert job.status == JobOutboxStatus.PROCESSING.value
    assert job.attempt_id == second.attempt_id
    assert item_id is None


@pytest.mark.asyncio
async def test_stale_session_fail_does_not_overwrite_newer_claim(
    db_session: AsyncSession,
):
    from app.models.job_outbox import JobOutboxStatus
    from app.services.ocr_outbox import fail_ocr_job

    receipt, first, second, cached = await _claim_a_then_reclaim_b_on_other_session(
        db_session, "stale-session-fail@example.com",
    )
    assert cached.attempt_id == first.attempt_id

    await fail_ocr_job(
        db_session,
        receipt.id,
        first.attempt_id,
        "OCR_FAILED",
        permanent=False,
    )

    job, stored = await _committed_outbox_and_receipt(
        db_session, first.outbox_id, receipt.id,
    )

    assert stored.status == ReceiptStatus.PROCESSING.value
    assert job.status == JobOutboxStatus.PROCESSING.value
    assert job.attempt_id == second.attempt_id
    assert job.last_error_code != "OCR_FAILED"


@pytest.mark.asyncio
async def test_deleted_account_fence_drops_ocr_result(db_session: AsyncSession):
    from app.models.job_outbox import JobOutboxStatus
    from app.services.ocr_outbox import claim_ocr_job, complete_ocr_result

    user = User(email="deleted-ocr@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    service = ReceiptService(db_session)
    receipt = await service.create_receipt(user, b"image-bytes", "image/jpeg")
    claimed = await claim_ocr_job(db_session, receipt.id)
    assert claimed is not None

    user.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()

    await complete_ocr_result(
        db_session,
        receipt.id,
        claimed.attempt_id,
        REMA1000_SAMPLE_OCR,
        None,
        None,
        None,
        [
            {
                "raw_product_name": "Melk",
                "quantity": 1,
                "unit_price": None,
                "line_total": 10,
            }
        ],
    )

    updated = await service.get_receipt_for_user(receipt.id, user.id)
    assert updated is not None
    assert updated.status != ReceiptStatus.READY_FOR_REVIEW.value
    jobs = await _outbox_for(db_session, receipt.id)
    assert len(jobs) == 1
    assert jobs[0].status == JobOutboxStatus.FAILED_PERMANENT.value
    assert jobs[0].last_error_code == "ACCOUNT_DELETED"

    observations = await db_session.execute(select(PriceObservation))
    assert observations.scalars().all() == []


@pytest.mark.asyncio
async def test_complete_ocr_locks_deleted_user_for_update(db_session: AsyncSession):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from app.models.store import Store
    from app.services.ocr_outbox import claim_ocr_job, complete_ocr_result

    user = User(email="lock-ocr@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    service = ReceiptService(db_session)
    receipt = await service.create_receipt(user, b"image-bytes", "image/jpeg")
    claimed = await claim_ocr_job(db_session, receipt.id)
    assert claimed is not None

    user.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()

    statements = []

    def capture(execute_state):
        statements.append(execute_state.statement)

    event.listen(Session, "do_orm_execute", capture)
    try:
        wrote = await complete_ocr_result(
            db_session,
            receipt.id,
            claimed.attempt_id,
            REMA1000_SAMPLE_OCR,
            None,
            None,
            None,
            [
                {
                    "raw_product_name": "Melk",
                    "quantity": 1,
                    "unit_price": None,
                    "line_total": 10,
                }
            ],
            store_name="REMA 1000",
            store_chain="rema1000",
        )
    finally:
        event.remove(Session, "do_orm_execute", capture)

    assert wrote is False
    user_locks = [
        stmt
        for stmt in statements
        if "users" in str(stmt).lower() and getattr(stmt, "_for_update_arg", None) is not None
    ]
    assert user_locks

    jobs = await _outbox_for(db_session, receipt.id)
    assert len(jobs) == 1
    assert jobs[0].status == "failed_permanent"
    assert jobs[0].last_error_code == "ACCOUNT_DELETED"
    stores = (await db_session.execute(select(Store))).scalars().all()
    assert stores == []


@pytest.mark.asyncio
async def test_claim_ocr_locks_user_for_update(db_session: AsyncSession):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from app.services.ocr_outbox import claim_ocr_job

    user = User(email="lock-claim@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    service = ReceiptService(db_session)
    receipt = await service.create_receipt(user, b"image-bytes", "image/jpeg")

    statements = []

    def capture(execute_state):
        statements.append(execute_state.statement)

    event.listen(Session, "do_orm_execute", capture)
    try:
        claimed = await claim_ocr_job(db_session, receipt.id)
    finally:
        event.remove(Session, "do_orm_execute", capture)

    assert claimed is not None
    user_locks = [
        stmt
        for stmt in statements
        if "users" in str(stmt).lower() and getattr(stmt, "_for_update_arg", None) is not None
    ]
    assert user_locks


@pytest.mark.asyncio
async def test_worker_does_not_reenqueue_ocr_after_account_deleted(
    db_session: AsyncSession,
):
    from app.models.job_outbox import JobOutboxStatus
    from app.models.store import Store
    from app.worker.tasks import process_receipt_with_db

    user = User(email="deleted-worker@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    service = ReceiptService(db_session)
    receipt = await service.create_receipt(user, b"image-bytes", "image/jpeg")
    user.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()

    with (
        patch("app.worker.tasks.StorageService") as mock_storage_cls,
        patch("app.worker.tasks.OcrService") as mock_ocr_cls,
        patch.object(ReceiptService, "get_or_create_store") as mock_store,
    ):
        mock_storage_cls.return_value.download_receipt.return_value = b"fake-image-bytes"
        mock_ocr_cls.return_value.extract_text.return_value = REMA1000_SAMPLE_OCR
        await process_receipt_with_db(str(receipt.id), db_session)

    mock_ocr_cls.return_value.extract_text.assert_not_called()
    mock_store.assert_not_called()

    jobs = await _outbox_for(db_session, receipt.id)
    assert len(jobs) == 1
    assert jobs[0].status == JobOutboxStatus.FAILED_PERMANENT.value
    assert jobs[0].last_error_code == "ACCOUNT_DELETED"

    stored = await db_session.get(Receipt, receipt.id)
    assert stored is not None
    assert stored.status != ReceiptStatus.READY_FOR_REVIEW.value

    stores = (await db_session.execute(select(Store))).scalars().all()
    assert stores == []
    observations = (await db_session.execute(select(PriceObservation))).scalars().all()
    assert observations == []


@pytest.mark.asyncio
async def test_complete_after_delete_does_not_create_store_or_enqueue(
    db_session: AsyncSession,
):
    from app.models.job_outbox import JobOutboxStatus
    from app.models.store import Store
    from app.services.ocr_outbox import claim_ocr_job, complete_ocr_result
    from app.worker.tasks import process_receipt_with_db

    user = User(email="deleted-mid-ocr@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    service = ReceiptService(db_session)
    receipt = await service.create_receipt(user, b"image-bytes", "image/jpeg")
    claimed = await claim_ocr_job(db_session, receipt.id)
    assert claimed is not None

    user.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()

    wrote = await complete_ocr_result(
        db_session,
        receipt.id,
        claimed.attempt_id,
        REMA1000_SAMPLE_OCR,
        None,
        None,
        None,
        [
            {
                "raw_product_name": "Melk",
                "quantity": 1,
                "unit_price": None,
                "line_total": 10,
            }
        ],
        store_name="REMA 1000",
        store_chain="rema1000",
    )
    assert wrote is False

    with (
        patch("app.worker.tasks.StorageService"),
        patch("app.worker.tasks.OcrService") as mock_ocr_cls,
    ):
        mock_ocr_cls.return_value.extract_text.return_value = REMA1000_SAMPLE_OCR
        await process_receipt_with_db(str(receipt.id), db_session)

    mock_ocr_cls.return_value.extract_text.assert_not_called()
    jobs = await _outbox_for(db_session, receipt.id)
    assert len(jobs) == 1
    assert jobs[0].status == JobOutboxStatus.FAILED_PERMANENT.value
    assert jobs[0].last_error_code == "ACCOUNT_DELETED"

    stored = await db_session.get(Receipt, receipt.id)
    assert stored is not None
    assert stored.status != ReceiptStatus.READY_FOR_REVIEW.value
    stores = (await db_session.execute(select(Store))).scalars().all()
    assert stores == []
    observations = (await db_session.execute(select(PriceObservation))).scalars().all()
    assert observations == []


@pytest.mark.asyncio
async def test_retry_reuses_pending_outbox_and_inserts_after_failed_permanent(
    client: AsyncClient,
    db_session: AsyncSession,
):
    from app.models.job_outbox import JobOutboxStatus

    headers, _email = await _register(client, "outbox-retry@example.com")

    with patch(
        "app.services.ocr_outbox.deliver_ocr_job",
        side_effect=ConnectionError("redis down"),
    ):
        upload = await client.post(
            "/receipts",
            headers=headers,
            files={"file": ("receipt.jpg", image_bytes(), "image/jpeg")},
        )
    receipt_id = UUID(upload.json()["id"])
    first_jobs = await _outbox_for(db_session, receipt_id)
    first_id = first_jobs[0].id

    receipt = await db_session.get(Receipt, receipt_id)
    receipt.status = ReceiptStatus.FAILED.value
    await db_session.commit()

    with patch("app.services.ocr_outbox.deliver_ocr_job"):
        retry = await client.post(f"/receipts/{receipt_id}/retry", headers=headers)
    assert retry.status_code == 200
    jobs = await _outbox_for(db_session, receipt_id)
    assert len(jobs) == 1
    assert jobs[0].id == first_id
    assert jobs[0].status in {
        JobOutboxStatus.PENDING.value,
        JobOutboxStatus.PUBLISHED.value,
    }

    jobs[0].status = JobOutboxStatus.FAILED_PERMANENT.value
    receipt = await db_session.get(Receipt, receipt_id)
    receipt.status = ReceiptStatus.FAILED.value
    await db_session.commit()

    with patch("app.services.ocr_outbox.deliver_ocr_job"):
        retry_again = await client.post(f"/receipts/{receipt_id}/retry", headers=headers)
    assert retry_again.status_code == 200
    jobs = await _outbox_for(db_session, receipt_id)
    assert len(jobs) == 2
    statuses = {job.status for job in jobs}
    assert JobOutboxStatus.FAILED_PERMANENT.value in statuses
    assert statuses & {
        JobOutboxStatus.PENDING.value,
        JobOutboxStatus.PUBLISHED.value,
    }


@pytest.mark.asyncio
async def test_ready_is_503_when_postgres_fails_and_health_stays_200(client: AsyncClient):
    async def postgres_down(_db):
        return False

    with patch("app.routers.health.check_postgres", postgres_down):
        ready = await client.get("/ready")
        health = await client.get("/health")

    assert ready.status_code == 503
    body = ready.json()
    assert body["code"] == "NOT_READY"
    assert body["retryable"] is True
    assert "request_id" in body
    assert health.status_code == 200


@pytest.mark.asyncio
async def test_ready_is_503_when_stale_pending_cannot_be_published(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    from app.config import settings
    from app.models.job_outbox import JobOutboxStatus

    monkeypatch.setattr(settings, "ready_stale_pending_seconds", 0)
    headers, _email = await _register(client, "outbox-ready@example.com")

    with patch(
        "app.services.ocr_outbox.deliver_ocr_job",
        side_effect=ConnectionError("redis down"),
    ):
        upload = await client.post(
            "/receipts",
            headers=headers,
            files={"file": ("receipt.jpg", image_bytes(), "image/jpeg")},
        )
    assert upload.status_code == 201
    jobs = await _outbox_for(db_session, UUID(upload.json()["id"]))
    assert jobs[0].status == JobOutboxStatus.PENDING.value

    with (
        patch("app.routers.health.check_minio", return_value=True),
        patch(
            "app.services.ocr_outbox.deliver_ocr_job",
            side_effect=ConnectionError("redis down"),
        ),
    ):
        ready = await client.get("/ready")

    assert ready.status_code == 503
    assert ready.json()["code"] == "NOT_READY"


@pytest.mark.asyncio
async def test_ready_is_200_when_dependencies_are_up(client: AsyncClient):
    async def postgres_ok(_db):
        return True

    with (
        patch("app.routers.health.check_postgres", postgres_ok),
        patch("app.routers.health.check_minio", return_value=True),
    ):
        ready = await client.get("/ready")

    assert ready.status_code == 200
    assert ready.json()["status"] == "ok"

"""OCR-jobber via transaksjonell outbox: enqueue, publish, claim og fencing."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.job_outbox import (
    JobAggregateType,
    JobOutbox,
    JobOutboxStatus,
    JobType,
)
from app.models.receipt import Receipt, ReceiptStatus
from app.models.store import Store
from app.models.user import User
from app.services.receipt_service import ReceiptService

logger = logging.getLogger(__name__)

_TERMINAL = (
    JobOutboxStatus.DONE.value,
    JobOutboxStatus.FAILED_PERMANENT.value,
)


@dataclass(frozen=True)
class ClaimedOcrJob:
    outbox_id: uuid.UUID
    attempt_id: uuid.UUID
    image_path: str


def deliver_ocr_job(receipt_id: str) -> None:
    from app.worker.tasks import process_receipt

    process_receipt.delay(receipt_id)


async def enqueue_ocr_job(
    db: AsyncSession,
    user_id: uuid.UUID,
    receipt_id: uuid.UUID,
) -> JobOutbox:
    existing = await _active_job(db, receipt_id)
    if existing is not None:
        return existing

    job = JobOutbox(
        user_id=user_id,
        aggregate_type=JobAggregateType.RECEIPT.value,
        aggregate_id=receipt_id,
        job_type=JobType.OCR_PROCESS.value,
        payload={"receipt_id": str(receipt_id)},
        status=JobOutboxStatus.PENDING.value,
        attempt_count=0,
    )
    db.add(job)
    await db.flush()
    return job


async def publish_pending_for_receipt(db: AsyncSession, receipt_id: uuid.UUID) -> bool:
    job = await _active_job(db, receipt_id)
    if job is None:
        return False
    return await _try_publish(db, job)


async def reconcile_job_outbox(
    db: AsyncSession,
    min_age_seconds: int | None = None,
) -> int:
    if min_age_seconds is None:
        min_age_seconds = settings.outbox_reconcile_min_age_seconds
    now = datetime.now(timezone.utc)
    if min_age_seconds <= 0:
        clauses = [
            JobOutbox.status == JobOutboxStatus.PENDING.value,
            JobOutbox.status == JobOutboxStatus.PUBLISHED.value,
            and_(
                JobOutbox.status == JobOutboxStatus.PROCESSING.value,
                JobOutbox.lease_expires_at.is_not(None),
                JobOutbox.lease_expires_at <= now,
            ),
        ]
    else:
        cutoff = now - timedelta(seconds=min_age_seconds)
        clauses = [
            and_(
                JobOutbox.status == JobOutboxStatus.PENDING.value,
                JobOutbox.created_at <= cutoff,
            ),
            and_(
                JobOutbox.status == JobOutboxStatus.PUBLISHED.value,
                JobOutbox.published_at.is_not(None),
                JobOutbox.published_at <= cutoff,
            ),
            and_(
                JobOutbox.status == JobOutboxStatus.PROCESSING.value,
                JobOutbox.lease_expires_at.is_not(None),
                JobOutbox.lease_expires_at <= now,
            ),
        ]

    result = await db.execute(
        select(JobOutbox).where(
            JobOutbox.job_type == JobType.OCR_PROCESS.value,
            or_(*clauses),
        ),
    )
    published = 0
    for job in result.scalars().all():
        if await _try_publish(db, job):
            published += 1
    return published


async def check_readiness(db: AsyncSession) -> bool:
    if not await _has_stale_pending(db):
        return True
    await reconcile_job_outbox(
        db,
        min_age_seconds=settings.ready_stale_pending_seconds,
    )
    return not await _has_stale_pending(db)


async def claim_ocr_job(
    db: AsyncSession,
    receipt_id: uuid.UUID,
) -> ClaimedOcrJob | None:
    job = await _lock_active_job(db, receipt_id)
    if job is None:
        return None

    now = datetime.now(timezone.utc)
    lease = job.lease_expires_at
    if lease is not None and lease.tzinfo is None:
        lease = lease.replace(tzinfo=timezone.utc)
    if (
        job.status == JobOutboxStatus.PROCESSING.value
        and lease is not None
        and lease > now
    ):
        return None

    user = await _lock_user(db, job.user_id)
    if user is None or user.deleted_at is not None:
        job.status = JobOutboxStatus.FAILED_PERMANENT.value
        job.last_error_code = "ACCOUNT_DELETED"
        await db.commit()
        return None

    receipt = await db.get(Receipt, receipt_id)
    if receipt is None:
        job.status = JobOutboxStatus.FAILED_PERMANENT.value
        job.last_error_code = "RECEIPT_MISSING"
        await db.commit()
        return None

    if receipt.status in {
        ReceiptStatus.READY_FOR_REVIEW.value,
        ReceiptStatus.CONFIRMED.value,
    }:
        job.status = JobOutboxStatus.DONE.value
        await db.commit()
        return None

    if job.attempt_count >= settings.outbox_max_attempts:
        job.status = JobOutboxStatus.FAILED_PERMANENT.value
        job.last_error_code = "MAX_ATTEMPTS"
        receipt.status = ReceiptStatus.FAILED.value
        await db.commit()
        return None

    job.status = JobOutboxStatus.PROCESSING.value
    job.attempt_id = uuid.uuid4()
    job.lease_expires_at = now + timedelta(seconds=settings.outbox_lease_seconds)
    job.attempt_count += 1
    receipt.status = ReceiptStatus.PROCESSING.value
    await db.commit()
    return ClaimedOcrJob(
        outbox_id=job.id,
        attempt_id=job.attempt_id,
        image_path=receipt.image_path,
    )


async def complete_ocr_result(
    db: AsyncSession,
    receipt_id: uuid.UUID,
    attempt_id: uuid.UUID,
    raw_ocr_text: str,
    store: Store | None,
    purchase_date: datetime | None,
    total: Decimal | None,
    items: list[dict],
    *,
    store_name: str | None = None,
    store_chain: str | None = None,
) -> bool:
    job = await _lock_active_job(db, receipt_id, attempt_id)
    if job is None:
        return False

    user = await _lock_user(db, job.user_id)
    if user is None or user.deleted_at is not None:
        job.status = JobOutboxStatus.FAILED_PERMANENT.value
        job.last_error_code = "ACCOUNT_DELETED"
        await db.commit()
        return False

    service = ReceiptService(db)
    if store is None and store_name:
        store = await service.get_or_create_store(store_name, store_chain)

    job.status = JobOutboxStatus.DONE.value
    await service.save_parsed_receipt(
        receipt_id,
        raw_ocr_text,
        store,
        purchase_date,
        total,
        items,
    )
    return True


async def fail_ocr_job(
    db: AsyncSession,
    receipt_id: uuid.UUID,
    attempt_id: uuid.UUID,
    error_code: str,
    permanent: bool,
) -> None:
    job = await _lock_active_job(db, receipt_id, attempt_id)
    if job is None:
        return

    job.last_error_code = error_code
    receipt = await db.get(Receipt, receipt_id)
    if permanent or job.attempt_count >= settings.outbox_max_attempts:
        job.status = JobOutboxStatus.FAILED_PERMANENT.value
        if receipt is not None:
            receipt.status = ReceiptStatus.FAILED.value
    else:
        job.status = JobOutboxStatus.PENDING.value
        job.lease_expires_at = None
        if receipt is not None and receipt.status == ReceiptStatus.PROCESSING.value:
            receipt.status = ReceiptStatus.UPLOADED.value
    await db.commit()


async def _try_publish(db: AsyncSession, job: JobOutbox) -> bool:
    try:
        deliver_ocr_job(str(job.aggregate_id))
    except Exception:
        logger.exception("OCR outbox publish failed: %s", job.id)
        return False

    await db.refresh(job)
    if job.status == JobOutboxStatus.PENDING.value:
        job.status = JobOutboxStatus.PUBLISHED.value
        job.published_at = datetime.now(timezone.utc)
        await db.commit()
    return True


async def _has_stale_pending(db: AsyncSession) -> bool:
    stmt = select(JobOutbox.id).where(
        JobOutbox.job_type == JobType.OCR_PROCESS.value,
        JobOutbox.status == JobOutboxStatus.PENDING.value,
    )
    threshold = settings.ready_stale_pending_seconds
    if threshold > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=threshold)
        stmt = stmt.where(JobOutbox.created_at <= cutoff)
    stmt = stmt.limit(1)
    return (await db.execute(stmt)).first() is not None


async def _active_job(db: AsyncSession, receipt_id: uuid.UUID) -> JobOutbox | None:
    result = await db.execute(
        select(JobOutbox).where(
            JobOutbox.job_type == JobType.OCR_PROCESS.value,
            JobOutbox.aggregate_id == receipt_id,
            JobOutbox.status.notin_(_TERMINAL),
        ),
    )
    return result.scalar_one_or_none()


async def _lock_active_job(
    db: AsyncSession,
    receipt_id: uuid.UUID,
    attempt_id: uuid.UUID | None = None,
) -> JobOutbox | None:
    clauses = [
        JobOutbox.job_type == JobType.OCR_PROCESS.value,
        JobOutbox.aggregate_id == receipt_id,
        JobOutbox.status.notin_(_TERMINAL),
    ]
    if attempt_id is not None:
        clauses.append(JobOutbox.attempt_id == attempt_id)
    result = await db.execute(
        select(JobOutbox)
        .where(*clauses)
        .with_for_update()
        .execution_options(populate_existing=True),
    )
    return result.scalar_one_or_none()


async def _lock_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True),
    )
    return result.scalar_one_or_none()

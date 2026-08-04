from unittest.mock import patch

import pytest

from app.worker.tasks import process_receipt_with_db
from tests.fixtures.rema1000_ocr import REMA1000_SAMPLE_OCR


@pytest.mark.asyncio
async def test_process_receipt_parses_rema1000(client, db_session):
    from app.models.user import User
    from app.services.receipt_service import ReceiptService

    user = User(email="worker@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    service = ReceiptService(db_session)
    with patch.object(service.storage, "upload_receipt", return_value="path.jpg"):
        receipt = await service.create_receipt(user, b"image-bytes", "image/jpeg")

    with (
        patch("app.worker.tasks.StorageService") as mock_storage_cls,
        patch("app.worker.tasks.OcrService") as mock_ocr_cls,
    ):
        mock_storage = mock_storage_cls.return_value
        mock_storage.download_receipt.return_value = b"image-bytes"
        mock_ocr_cls.return_value.extract_text.return_value = REMA1000_SAMPLE_OCR

        await process_receipt_with_db(str(receipt.id), db_session)

    updated = await service.get_receipt_for_user(receipt.id, user.id)
    assert updated is not None
    assert updated.status == "READY_FOR_REVIEW"
    assert updated.store is not None
    assert updated.store.chain == "rema1000"
    assert len(updated.items) == 7
    assert updated.total is not None

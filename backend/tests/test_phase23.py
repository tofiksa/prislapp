from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
import uuid

import pytest
from PIL import Image
from sqlalchemy import select

from app.models.user import User
from app.models.receipt import Receipt
from app.models.product import PriceObservation
from app.parsers import parse_receipt_text
from app.services.receipt_service import ReceiptService
from app.services.storage_service import StorageService


def image_bytes():
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format="JPEG")
    return output.getvalue()


async def account(client, email="phase23@example.com"):
    response = await client.post("/auth/register", json={"email": email, "password": "TestPass123!"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, response.json()


@pytest.fixture
def storage():
    objects = {}
    def upload(self, name, data, content_type="image/jpeg"):
        objects[name] = data
        return name
    def remove(self, name):
        objects.pop(name, None)
    with patch.object(StorageService, "upload_receipt", upload), patch.object(
        StorageService, "delete_receipt", remove, create=True
    ), patch("app.services.ocr_outbox.deliver_ocr_job"):
        yield objects


@pytest.mark.asyncio
async def test_refresh_requires_refresh_token_and_existing_user(client):
    _, tokens = await account(client)
    response = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    assert (await client.get("/auth/me", headers={"Authorization": "Bearer " + response.json()["access_token"]})).status_code == 200
    assert (await client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})).status_code == 401
    assert (await client.post("/auth/refresh", json={"refresh_token": "invalid"})).status_code == 401


@pytest.mark.asyncio
async def test_upload_is_idempotent_and_user_scoped(client, storage):
    headers, _ = await account(client)
    key = str(uuid.uuid4())
    async def upload(h):
        return await client.post("/receipts", headers={**h, "Idempotency-Key": key}, files={"file": ("r.jpg", image_bytes(), "image/jpeg")})
    first, second = await upload(headers), await upload(headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(storage) == 1
    other, _ = await account(client, "other@example.com")
    assert (await upload(other)).status_code == 409
    for method, suffix in [("get", ""), ("delete", ""), ("post", "/retry")]:
        assert (await getattr(client, method)(f"/receipts/{first.json()['id']}{suffix}", headers=other)).status_code == 404


@pytest.mark.asyncio
async def test_invalid_image_and_uuid_are_validation_errors(client, storage):
    headers, _ = await account(client)
    response = await client.post("/receipts", headers=headers, files={"file": ("r.jpg", b"not an image", "image/jpeg")})
    assert response.status_code == 400
    assert (await client.get("/receipts/not-a-uuid", headers=headers)).status_code == 422
    assert (await client.get("/receipts?store_id=bad", headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_expired_images_removed_without_deleting_history(client, db_session, storage):
    headers, _ = await account(client)
    upload = await client.post("/receipts", headers=headers, files={"file": ("r.jpg", image_bytes(), "image/jpeg")})
    receipt = await db_session.get(Receipt, uuid.UUID(upload.json()["id"]))
    receipt.image_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()
    service = ReceiptService(db_session)
    assert await service.delete_expired_images() == 1
    assert storage == {}
    assert await db_session.get(Receipt, receipt.id) is not None
    assert await service.delete_expired_images() == 0


@pytest.mark.asyncio
async def test_delete_removes_original_image(client, storage):
    headers, _ = await account(client)
    response = await client.post("/receipts", headers=headers, files={"file": ("r.jpg", image_bytes(), "image/jpeg")})
    assert len(storage) == 1
    assert (await client.delete(f"/receipts/{response.json()['id']}", headers=headers)).status_code == 204
    assert storage == {}


@pytest.mark.asyncio
async def test_confirm_updates_store_and_compares_unit_price_and_latest(client, db_session, storage):
    headers, _ = await account(client)
    user = (await db_session.execute(select(User))).scalar_one()
    service = ReceiptService(db_session)
    for date, quantity, total in [("2026-01-01T12:00:00Z", "2", "40"), ("2026-02-01T12:00:00Z", "1", "25")]:
        receipt = await service.create_receipt(user, image_bytes())
        old_store = await service.get_or_create_store("Old store", None)
        await service.save_parsed_receipt(receipt.id, "text", old_store, None, None, [])
        result = await client.put(f"/receipts/{receipt.id}/confirm", headers=headers, json={
            "store_name": "Correct store", "purchase_date": date,
            "items": [{"raw_product_name": "Melk 1L", "quantity": quantity, "line_total": total}],
        })
        assert result.status_code == 200
        assert result.json()["store"]["name"] == "Correct store"
    search = await client.get("/products/search?q=melk", headers=headers)
    product_id = search.json()["items"][0]["id"]
    prices = (await client.get(f"/products/{product_id}/my-prices", headers=headers)).json()
    assert prices["cheapest"]["price"] == "20.00"
    assert prices["cheapest"]["store"]["name"] == "Correct store"
    assert prices["latest_by_store"][0]["price"] == "25.00"
    other, _ = await account(client, "private@example.com")
    assert (await client.get("/products/search?q=melk", headers=other)).json()["items"] == []
    assert (await client.get(f"/products/{product_id}/my-prices", headers=other)).status_code == 404


@pytest.mark.asyncio
async def test_confirm_rejects_invalid_quantity(client, db_session, storage):
    headers, _ = await account(client)
    user = (await db_session.execute(select(User))).scalar_one()
    receipt = await ReceiptService(db_session).create_receipt(user, image_bytes())
    response = await client.put(f"/receipts/{receipt.id}/confirm", headers=headers, json={
        "items": [{"raw_product_name": "Melk", "quantity": "0", "line_total": "25"}],
    })
    assert response.status_code == 422


def test_generic_parser_handles_norwegian_receipt_and_ignores_payment():
    parsed = parse_receipt_text("KIWI Majorstuen\n10.08.2026 14:30\nMELK 1L 25,90\nBRØD 39,90\nTOTAL 65,80\nVISA 65,80")
    assert parsed.store_name == "KIWI Majorstuen"
    assert [item.raw_name for item in parsed.items] == ["MELK 1L", "BRØD"]
    assert parsed.total == Decimal("65.80")
    assert parsed.purchase_date.year == 2026
    assert parsed.purchase_date.utcoffset() == timedelta(hours=2)


def test_invalid_ocr_date_does_not_crash_parser():
    parsed = parse_receipt_text("REMA 1000 Test\n99.99.26 25:99\nMELK 15 25,00")
    assert parsed.purchase_date is None
    assert len(parsed.items) == 1


@pytest.mark.asyncio
async def test_retry_failed_receipt_and_worker_does_not_overwrite_confirmed(client, db_session, storage):
    from app.worker.tasks import process_receipt_with_db
    headers, _ = await account(client)
    user = (await db_session.execute(select(User))).scalar_one()
    service = ReceiptService(db_session)
    receipt = await service.create_receipt(user, image_bytes())
    receipt.status = "FAILED"
    await db_session.commit()
    assert (await client.post(f"/receipts/{receipt.id}/retry", headers=headers)).status_code == 200
    receipt.status = "CONFIRMED"
    await db_session.commit()
    with patch("app.worker.tasks.StorageService") as mock_storage:
        await process_receipt_with_db(str(receipt.id), db_session)
    await db_session.refresh(receipt)
    assert receipt.status == "CONFIRMED"
    mock_storage.return_value.download_receipt.assert_not_called()


def test_ocr_groups_columns_into_receipt_lines():
    from types import SimpleNamespace
    from app.services.ocr_service import _result_to_text
    result = SimpleNamespace(txts=["MELK", "15", "25,90", "BRØD", "15", "39,90"], boxes=[
        [[0, 0], [80, 0], [80, 20], [0, 20]],
        [[100, 2], [120, 2], [120, 22], [100, 22]],
        [[200, 1], [250, 1], [250, 21], [200, 21]],
        [[0, 40], [80, 40], [80, 60], [0, 60]],
        [[100, 41], [120, 41], [120, 61], [100, 61]],
        [[200, 40], [250, 40], [250, 60], [200, 60]],
    ])
    assert _result_to_text(result).splitlines() == ["MELK 15 25,90", "BRØD 15 39,90"]


def test_missing_bucket_is_not_healthy():
    service = StorageService()
    with patch.object(service.client, "bucket_exists", return_value=False):
        assert service.is_available() is False


def test_normal_format_parses_vat_letters_and_total():
    parsed = parse_receipt_text("Normal\nNormal Oslo, Thon Senter Triaden\nDato 31.07.26 19:36\nBeskrivelse Beløp\nMALACO SNØRE 94G 16,00 B\nSKITTLES 152G 20,00 B\nI alt kr. 36,00\nKontant 50,00\nVekslepenger 14,00")
    assert parsed.store_name == "Normal Oslo, Thon Senter Triaden"
    assert len(parsed.items) == 2
    assert parsed.items[0].raw_name == "MALACO SNØRE 94G"
    assert parsed.total == Decimal("36")


def test_europris_format_extracts_left_receipt_when_text_continues():
    parsed = parse_receipt_text("Europris\nEP TRIADEN Tlf:47650093\n31 07 2026 19:57:23\nVARE MVA% SUM\nSUPERMIX SMÅGODT 220 G 15 39,90 SKITTLES\nÀ BÉTÀLÈ 39,90 OTHER RECEIPT\nKontant 50,00")
    assert parsed.store_name == "EP TRIADEN"
    assert len(parsed.items) == 1
    assert parsed.items[0].raw_name == "SUPERMIX SMÅGODT 220 G"
    assert parsed.total == Decimal("39.90")


@pytest.mark.asyncio
async def test_product_normalization_matches_spacing_and_small_ocr_errors_not_sizes(db_session):
    from app.services.product_service import ProductService
    service = ProductService(db_session)
    first = await service.resolve_product("COTTAGE CHEESE 400 G", None)
    spacing = await service.resolve_product("cottage cheese 400g", None)
    typo = await service.resolve_product("COTTAGE CHEESE 400G.", None)
    different = await service.resolve_product("COTTAGE CHEESE 200G", None)
    assert first.id == spacing.id == typo.id
    assert different.id != first.id


@pytest.mark.asyncio
async def test_fuzzy_matching_is_conservative_about_numbers(db_session):
    from app.services.product_service import ProductService
    service = ProductService(db_session)
    first = await service.resolve_product("COTTAGE CHEESE MAGER 400G", None)
    await service.resolve_product("COTTAGE CHEE5E MAGER 400G", None)
    other_size = await service.resolve_product("COTTAGE CHEESE MAGER 200G", None)
    # Embedded OCR digits should not merge different quantities or sizes.
    assert other_size.id != first.id
    safe_typo = await service.resolve_product("COTTAGE CHEESE MAGFR 400G", None)
    assert safe_typo.id == first.id


@pytest.mark.asyncio
async def test_price_migration_recomputes_existing_observations(db_session):
    import importlib
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from app.models.product import Product
    from app.models.store import Store
    from app.models.receipt_item import ReceiptItem
    user = User(email="migration@example.com")
    store = Store(name="Test", normalized_name="test")
    product = Product(canonical_name="Melk")
    db_session.add_all([user, store, product])
    await db_session.flush()
    receipt = Receipt(user_id=user.id, store_id=store.id, status="CONFIRMED", image_path="", image_expires_at=datetime.now(timezone.utc))
    db_session.add(receipt)
    await db_session.flush()
    item = ReceiptItem(receipt_id=receipt.id, product_id=product.id, raw_product_name="Melk", quantity=Decimal("2"), line_total=Decimal("40"))
    db_session.add(item)
    await db_session.flush()
    observation = PriceObservation(user_id=user.id, store_id=store.id, product_id=product.id, receipt_item_id=item.id, price=Decimal("40"))
    db_session.add(observation)
    await db_session.commit()
    migration_path = __import__("pathlib").Path(__file__).parents[1] / "alembic/versions/004_unit_prices.py"
    assert migration_path.exists(), "Existing price history must be migrated to unit prices"
    spec = importlib.util.spec_from_file_location("unit_prices_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = await db_session.connection()
    def upgrade(conn):
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
    await connection.run_sync(upgrade)
    await db_session.refresh(observation)
    assert observation.price == Decimal("20")

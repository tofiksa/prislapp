"""S05-A: revisjoner, atomisk confirm/retting og avstemming på /v2/receipts."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_ledger import AccountLedger
from app.models.product import PriceObservation, Product
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_item import ReceiptItem
from app.models.receipt_revision import (
    PriceObservationV2,
    ReceiptRevision,
    ReceiptRevisionLine,
    RevisionStatus,
)
from app.models.store import Store
from app.models.user import User
from app.models.user_product import IdentityStatus, UserProduct
from app.models.user_store import StoreIdentityLevel, UserStore

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


async def _legacy_observation(db: AsyncSession, user: User, receipt: Receipt) -> uuid.UUID:
    """En v1-observasjon fra den gamle bekreftelsesstien."""
    product = Product(canonical_name="Melk lett 1L")
    db.add(product)
    store = (await db.execute(select(Store))).scalars().first()
    item = ReceiptItem(
        receipt_id=receipt.id,
        raw_product_name="MELK LETT 1L",
        quantity=Decimal("1"),
        line_total=Decimal("2.50"),
    )
    db.add(item)
    await db.flush()
    observation = PriceObservation(
        user_id=user.id,
        product_id=product.id,
        store_id=store.id,
        receipt_item_id=item.id,
        price=Decimal("2.50"),
        observed_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    db.add(observation)
    await db.flush()
    return observation.id


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


def _payload(**overrides) -> dict:
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


async def _confirm(client: AsyncClient, receipt: Receipt, headers: dict, payload: dict):
    return await client.post(
        f"/v2/receipts/{receipt.id}/confirm",
        json=payload,
        headers=headers,
    )


async def test_confirm_creates_the_first_revision_and_confirms_the_receipt(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _user_store(db_session, owner)
    product = await _user_product(db_session, owner)
    receipt = await _ready_receipt(db_session, owner)
    payload = _payload(
        store_id=str(store.id),
        lines=[_line(user_product_id=str(product.id))],
    )

    response = await _confirm(client, receipt, headers, payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["receipt_id"] == str(receipt.id)
    assert body["revision"] == 1
    assert body["status"] == "confirmed"
    assert body["price_data_version"] == 2
    assert body["reconciliation"]["status"] == "balanced"
    assert body["reconciliation"]["computed_total"] == "25.00"
    assert body["reconciliation"]["difference"] == "0.00"


async def test_confirm_bumps_the_account_price_data_version(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)

    await _confirm(client, receipt, headers, _payload())

    ledger = (
        await db_session.execute(
            select(AccountLedger).where(AccountLedger.user_id == owner.id),
        )
    ).scalar_one()
    assert ledger.price_data_version == 2


async def test_double_confirm_with_the_same_mutation_creates_one_revision(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)
    payload = _payload()

    first = await _confirm(client, receipt, headers, payload)
    second = await _confirm(client, receipt, headers, payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    revisions = (
        await db_session.execute(
            select(ReceiptRevision).where(ReceiptRevision.receipt_id == receipt.id),
        )
    ).scalars().all()
    assert len(revisions) == 1


async def test_replayed_confirm_does_not_bump_the_price_data_version_again(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)
    payload = _payload()

    await _confirm(client, receipt, headers, payload)
    replay = await _confirm(client, receipt, headers, payload)

    assert replay.json()["price_data_version"] == 2
    ledger = (
        await db_session.execute(
            select(AccountLedger).where(AccountLedger.user_id == owner.id),
        )
    ).scalar_one()
    assert ledger.price_data_version == 2


async def test_same_mutation_id_with_other_content_is_a_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)
    payload = _payload()

    await _confirm(client, receipt, headers, payload)
    changed = dict(payload, printed_total="30.00", lines=[_line(net_line_total="30.00")])
    response = await _confirm(client, receipt, headers, changed)

    assert response.status_code == 409, response.text
    body = response.json()
    assert all(key in body for key in ERROR_KEYS)
    assert body["code"] == "MUTATION_CONFLICT"
    assert [error["field"] for error in body["field_errors"]] == ["mutation_id"]
    assert body["retryable"] is False


async def test_the_same_mutation_id_on_another_receipt_is_a_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    first = await _ready_receipt(db_session, owner)
    second = await _ready_receipt(db_session, owner)
    payload = _payload()

    await _confirm(client, first, headers, payload)
    response = await _confirm(client, second, headers, payload)

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "MUTATION_CONFLICT"
    assert (
        await db_session.execute(
            select(ReceiptRevision).where(ReceiptRevision.receipt_id == second.id),
        )
    ).scalar_one_or_none() is None


async def test_confirm_after_confirm_with_a_new_mutation_is_a_state_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)

    await _confirm(client, receipt, headers, _payload())
    response = await _confirm(client, receipt, headers, _payload())

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "RECEIPT_STATE_CONFLICT"


async def test_receipt_version_follows_the_current_confirmed_revision(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)
    receipt_id = receipt.id

    await _confirm(client, receipt, headers, _payload())

    db_session.expire_all()
    stored = (
        await db_session.execute(select(Receipt).where(Receipt.id == receipt_id))
    ).scalar_one()
    assert stored.version == 1
    assert stored.status == ReceiptStatus.CONFIRMED.value


async def test_stale_expected_version_conflicts_with_the_current_version(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)

    response = await _confirm(client, receipt, headers, _payload(expected_version=3))

    assert response.status_code == 409, response.text
    body = response.json()
    assert all(key in body for key in ERROR_KEYS)
    assert body["code"] == "VERSION_CONFLICT"
    assert body["current_version"] == 0
    assert [error["field"] for error in body["field_errors"]] == ["expected_version"]
    assert body["retryable"] is False


async def test_reconciliation_gap_without_acceptance_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)
    payload = _payload(
        printed_total="25.50",
        lines=[_line(net_line_total="25.00")],
    )

    response = await _confirm(client, receipt, headers, payload)

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "RECONCILIATION_GAP"
    assert [error["field"] for error in body["field_errors"]] == ["reconciliation"]


async def test_a_gap_of_one_ore_is_within_tolerance(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)
    payload = _payload(printed_total="25.01", lines=[_line(net_line_total="25.00")])

    response = await _confirm(client, receipt, headers, payload)

    assert response.status_code == 200, response.text
    assert response.json()["reconciliation"]["status"] == "balanced"


async def test_accepted_gap_confirms_and_keeps_unresolved_lines_out_of_pricing(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _user_store(db_session, owner)
    product = await _user_product(db_session, owner)
    unresolved = await _user_product(db_session, owner, "Yoghurt naturell")
    receipt = await _ready_receipt(db_session, owner)
    payload = _payload(
        store_id=str(store.id),
        printed_total="100.00",
        accept_reconciliation_gap=True,
        lines=[
            _line(user_product_id=str(product.id), net_line_total="99.50"),
            _line(
                raw_product_name="YOGHURT",
                user_product_id=str(unresolved.id),
                net_line_total=None,
            ),
        ],
    )

    response = await _confirm(client, receipt, headers, payload)

    assert response.status_code == 200, response.text
    reconciliation = response.json()["reconciliation"]
    assert reconciliation["status"] == "gap_accepted"
    assert reconciliation["computed_total"] == "99.50"
    assert reconciliation["difference"] == "-0.50"
    assert reconciliation["reason"] == "unresolved_line_amounts"

    lines = (
        await db_session.execute(
            select(ReceiptRevisionLine).order_by(ReceiptRevisionLine.position),
        )
    ).scalars().all()
    assert [line.eligible for line in lines] == [True, False]
    assert "unknown_discount" in lines[1].exclusion_reasons


async def _eligible_confirm(
    client: AsyncClient,
    db: AsyncSession,
    email: str = "owner@example.com",
    price: str = "2.50",
) -> tuple[User, dict, Receipt, UserProduct, str]:
    """En bekreftet kvittering med én rangerbar linje til `price`."""
    owner, headers = await _register(client, db, email)
    store = await _user_store(db, owner)
    product = await _user_product(db, owner)
    receipt = await _ready_receipt(db, owner)
    line_id = str(uuid.uuid4())
    response = await _confirm(
        client,
        receipt,
        headers,
        _payload(
            store_id=str(store.id),
            printed_total=price,
            lines=[_line(id=line_id, user_product_id=str(product.id), net_line_total=price)],
        ),
    )
    assert response.status_code == 200, response.text
    return owner, headers, receipt, product, line_id


async def _current_prices(db: AsyncSession) -> list[Decimal]:
    result = await db.execute(
        select(PriceObservationV2.price).where(PriceObservationV2.is_current.is_(True)),
    )
    return list(result.scalars().all())


async def test_an_eligible_line_publishes_a_current_price_observation(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await _eligible_confirm(client, db_session)

    assert await _current_prices(db_session) == [Decimal("2.500000")]


async def test_correcting_a_price_replaces_the_wrong_minimum(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers, receipt, product, line_id = await _eligible_confirm(client, db_session)
    store_id = (
        await db_session.execute(select(UserStore.id))
    ).scalar_one()

    response = await client.post(
        f"/v2/receipts/{receipt.id}/revisions",
        json=_payload(
            expected_version=1,
            store_id=str(store_id),
            printed_total="25.00",
            lines=[
                _line(id=line_id, user_product_id=str(product.id), net_line_total="25.00"),
            ],
        ),
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 2
    assert body["status"] == "confirmed"
    assert body["price_data_version"] == 3
    assert await _current_prices(db_session) == [Decimal("25.000000")]


async def test_the_superseded_revision_no_longer_publishes_its_price(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers, receipt, product, line_id = await _eligible_confirm(client, db_session)
    store_id = (await db_session.execute(select(UserStore.id))).scalar_one()

    await client.post(
        f"/v2/receipts/{receipt.id}/revisions",
        json=_payload(
            expected_version=1,
            store_id=str(store_id),
            printed_total="25.00",
            lines=[_line(id=line_id, user_product_id=str(product.id), net_line_total="25.00")],
        ),
        headers=headers,
    )

    observations = (
        await db_session.execute(
            select(PriceObservationV2).order_by(PriceObservationV2.revision),
        )
    ).scalars().all()
    assert [(row.revision, row.is_current) for row in observations] == [(1, False), (2, True)]


async def test_a_revision_keeps_the_stable_line_id(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers, receipt, product, line_id = await _eligible_confirm(client, db_session)
    store_id = (await db_session.execute(select(UserStore.id))).scalar_one()

    await client.post(
        f"/v2/receipts/{receipt.id}/revisions",
        json=_payload(
            expected_version=1,
            store_id=str(store_id),
            printed_total="25.00",
            lines=[_line(id=line_id, user_product_id=str(product.id), net_line_total="25.00")],
        ),
        headers=headers,
    )

    rows = (
        await db_session.execute(
            select(ReceiptRevisionLine.line_id, ReceiptRevision.revision)
            .join(ReceiptRevision, ReceiptRevision.id == ReceiptRevisionLine.revision_id)
            .order_by(ReceiptRevision.revision),
        )
    ).all()
    assert [(str(row[0]), row[1]) for row in rows] == [(line_id, 1), (line_id, 2)]


async def test_a_revision_requires_a_confirmed_receipt(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)

    response = await client.post(
        f"/v2/receipts/{receipt.id}/revisions",
        json=_payload(expected_version=0),
        headers=headers,
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "RECEIPT_STATE_CONFLICT"


async def test_reconciliation_without_a_printed_total_is_not_independent(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)

    response = await _confirm(client, receipt, headers, _payload(printed_total=None))

    assert response.status_code == 200, response.text
    reconciliation = response.json()["reconciliation"]
    assert reconciliation["status"] == "unverifiable"
    assert reconciliation["reason"] == "missing_printed_total"
    assert reconciliation["difference"] is None
    assert reconciliation["computed_total"] == "25.00"


async def test_another_owners_receipt_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers = await _register(client, db_session, "owner@example.com")
    other, _ = await _register(client, db_session, "other@example.com")
    foreign = await _ready_receipt(db_session, other)

    response = await _confirm(client, foreign, headers, _payload())

    assert response.status_code == 404, response.text
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert str(foreign.id) not in body["message"]


async def test_unknown_receipt_id_is_not_found(client: AsyncClient, db_session: AsyncSession):
    _, headers = await _register(client, db_session, "owner@example.com")

    response = await client.post(
        f"/v2/receipts/{uuid.uuid4()}/confirm",
        json=_payload(),
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_another_owners_store_in_the_body_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    other, _ = await _register(client, db_session, "other@example.com")
    foreign_store = await _user_store(db_session, other)
    receipt = await _ready_receipt(db_session, owner)

    response = await _confirm(
        client,
        receipt,
        headers,
        _payload(store_id=str(foreign_store.id)),
    )

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


async def test_another_owners_product_in_a_line_is_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    other, _ = await _register(client, db_session, "other@example.com")
    foreign_product = await _user_product(db_session, other)
    receipt = await _ready_receipt(db_session, owner)

    response = await _confirm(
        client,
        receipt,
        headers,
        _payload(lines=[_line(user_product_id=str(foreign_product.id))]),
    )

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


async def test_confirm_requires_authentication(client: AsyncClient, db_session: AsyncSession):
    owner, _ = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)

    response = await client.post(f"/v2/receipts/{receipt.id}/confirm", json=_payload())

    assert response.status_code in (401, 403)


async def test_unknown_date_confirmed_today_stays_undated(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _user_store(db_session, owner)
    product = await _user_product(db_session, owner)
    receipt = await _ready_receipt(db_session, owner)
    receipt_id = receipt.id

    response = await _confirm(
        client,
        receipt,
        headers,
        _payload(
            store_id=str(store.id),
            purchase_date=None,
            date_precision="unknown",
            lines=[_line(user_product_id=str(product.id))],
        ),
    )

    assert response.status_code == 200, response.text
    db_session.expire_all()
    stored = (
        await db_session.execute(select(Receipt).where(Receipt.id == receipt_id))
    ).scalar_one()
    assert stored.purchase_date is None
    assert stored.date_precision == "unknown"
    assert stored.date_source == "unknown"
    revision = (
        await db_session.execute(select(ReceiptRevision).where(ReceiptRevision.revision == 1))
    ).scalar_one()
    assert revision.purchase_date is None
    assert revision.date_precision == "unknown"


async def test_an_undated_line_is_saved_but_not_ranked_by_date(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _user_store(db_session, owner)
    product = await _user_product(db_session, owner)
    receipt = await _ready_receipt(db_session, owner)

    await _confirm(
        client,
        receipt,
        headers,
        _payload(
            store_id=str(store.id),
            purchase_date=None,
            date_precision="unknown",
            lines=[_line(user_product_id=str(product.id))],
        ),
    )

    observation = (
        await db_session.execute(select(PriceObservationV2))
    ).scalar_one()
    assert observation.purchase_date is None
    assert observation.quality_status == "rankable_undated"
    line = (await db_session.execute(select(ReceiptRevisionLine))).scalar_one()
    assert line.eligible is True
    assert line.eligible_for_dated_ranking is False
    assert "unknown_date" in line.exclusion_reasons


async def test_a_receipt_without_a_store_is_confirmed_without_publishing_prices(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    product = await _user_product(db_session, owner)
    receipt = await _ready_receipt(db_session, owner)

    response = await _confirm(
        client,
        receipt,
        headers,
        _payload(store_id=None, lines=[_line(user_product_id=str(product.id))]),
    )

    assert response.status_code == 200, response.text
    assert await _current_prices(db_session) == []
    line = (await db_session.execute(select(ReceiptRevisionLine))).scalar_one()
    assert line.eligible is False
    assert "unknown_store" in line.exclusion_reasons


async def test_a_line_without_a_confirmed_identity_is_not_ranked(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _user_store(db_session, owner)
    receipt = await _ready_receipt(db_session, owner)

    await _confirm(client, receipt, headers, _payload(store_id=str(store.id)))

    assert await _current_prices(db_session) == []
    line = (await db_session.execute(select(ReceiptRevisionLine))).scalar_one()
    assert line.eligible is False
    assert "unresolved_identity" in line.exclusion_reasons


async def test_draft_is_saved_without_confirming_the_receipt(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)
    receipt_id = receipt.id

    response = await client.put(
        f"/v2/receipts/{receipt.id}/draft",
        json=_payload(),
        headers=headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 1
    assert body["status"] == "draft"
    assert body["price_data_version"] == 1
    db_session.expire_all()
    stored = (
        await db_session.execute(select(Receipt).where(Receipt.id == receipt_id))
    ).scalar_one()
    assert stored.status == ReceiptStatus.READY_FOR_REVIEW.value
    assert stored.version == 0
    assert await _current_prices(db_session) == []


async def test_a_second_draft_reuses_the_pending_revision(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)

    await client.put(f"/v2/receipts/{receipt.id}/draft", json=_payload(), headers=headers)
    await client.put(
        f"/v2/receipts/{receipt.id}/draft",
        json=_payload(printed_total="30.00", lines=[_line(net_line_total="30.00")]),
        headers=headers,
    )

    revisions = (
        await db_session.execute(select(ReceiptRevision))
    ).scalars().all()
    assert len(revisions) == 1
    assert revisions[0].status == RevisionStatus.DRAFT.value
    lines = (await db_session.execute(select(ReceiptRevisionLine))).scalars().all()
    assert [line.net_line_total for line in lines] == [Decimal("30.00")]


async def test_confirm_promotes_the_saved_draft_revision(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)

    await client.put(f"/v2/receipts/{receipt.id}/draft", json=_payload(), headers=headers)
    response = await _confirm(client, receipt, headers, _payload())

    assert response.status_code == 200, response.text
    revisions = (await db_session.execute(select(ReceiptRevision))).scalars().all()
    assert len(revisions) == 1
    assert revisions[0].status == RevisionStatus.CONFIRMED.value
    assert revisions[0].confirmed_at is not None


async def test_a_draft_with_a_gap_is_still_saved(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)

    response = await client.put(
        f"/v2/receipts/{receipt.id}/draft",
        json=_payload(printed_total="100.00", lines=[_line(net_line_total="25.00")]),
        headers=headers,
    )

    assert response.status_code == 200, response.text
    reconciliation = response.json()["reconciliation"]
    assert reconciliation["status"] == "gap"
    assert reconciliation["difference"] == "-75.00"
    assert reconciliation["gap_accepted"] is False
    revision = (await db_session.execute(select(ReceiptRevision))).scalar_one()
    assert revision.status == RevisionStatus.DRAFT.value


async def test_draft_on_a_confirmed_receipt_is_a_state_conflict(
    client: AsyncClient,
    db_session: AsyncSession,
):
    _, headers, receipt, _, _ = await _eligible_confirm(client, db_session)

    response = await client.put(
        f"/v2/receipts/{receipt.id}/draft",
        json=_payload(expected_version=1),
        headers=headers,
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "RECEIPT_STATE_CONFLICT"


async def test_money_sent_as_a_json_number_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)

    response = await _confirm(
        client,
        receipt,
        headers,
        _payload(printed_total=25.0, lines=[_line(net_line_total=25.0)]),
    )

    assert response.status_code == 422, response.text


async def test_two_lines_may_not_share_a_line_id(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    receipt = await _ready_receipt(db_session, owner)
    shared = str(uuid.uuid4())

    response = await _confirm(
        client,
        receipt,
        headers,
        _payload(
            printed_total="50.00",
            lines=[_line(id=shared), _line(id=shared)],
        ),
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert [error["field"] for error in body["field_errors"]] == ["lines"]


async def test_confirming_a_v2_receipt_clears_the_v1_price_observations(
    client: AsyncClient,
    db_session: AsyncSession,
):
    owner, headers = await _register(client, db_session, "owner@example.com")
    store = await _user_store(db_session, owner)
    product = await _user_product(db_session, owner)
    receipt = await _ready_receipt(db_session, owner)
    legacy = await _legacy_observation(db_session, owner, receipt)

    await _confirm(
        client,
        receipt,
        headers,
        _payload(store_id=str(store.id), lines=[_line(user_product_id=str(product.id))]),
    )

    remaining = (
        await db_session.execute(
            select(PriceObservation).where(PriceObservation.id == legacy),
        )
    ).scalar_one_or_none()
    assert remaining is None

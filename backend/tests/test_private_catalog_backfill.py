"""S03-A: backfill bygger privat katalog fra eierens egne bekreftede kvitteringer."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_ledger import AccountLedger
from app.models.product import Product, ProductAlias
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_item import ReceiptItem
from app.models.store import Store
from app.models.user import User
from app.models.user_product import (
    AliasMatchMethod,
    AliasSource,
    IdentityStatus,
    UserProduct,
    UserProductAlias,
)
from app.models.user_store import StoreIdentityLevel, UserStore
from app.services.private_catalog_backfill import backfill_private_catalog
from app.services.product_service import normalize_product_name
from app.services.store_service import normalize_store_name

pytestmark = pytest.mark.asyncio

EXPIRES_AT = datetime(2026, 10, 1, tzinfo=timezone.utc)
PURCHASED_AT = datetime(2026, 9, 1, tzinfo=timezone.utc)


async def _run_backfill(db: AsyncSession) -> None:
    connection = await db.connection()
    await connection.run_sync(backfill_private_catalog)


async def _user(db: AsyncSession, email: str) -> User:
    user = User(email=email, password_hash="hash")
    db.add(user)
    await db.flush()
    return user


async def _store(db: AsyncSession, name: str, chain: str | None = None) -> Store:
    store = Store(name=name, normalized_name=normalize_store_name(name), chain=chain)
    db.add(store)
    await db.flush()
    return store


async def _global_product(db: AsyncSession, canonical_name: str, *aliases: str) -> Product:
    product = Product(canonical_name=canonical_name)
    db.add(product)
    await db.flush()
    for alias in aliases or (canonical_name,):
        db.add(
            ProductAlias(
                product_id=product.id,
                alias_name=normalize_product_name(alias),
            ),
        )
    await db.flush()
    return product


async def _receipt(
    db: AsyncSession,
    user: User,
    store: Store | None,
    lines: list[tuple[str, Product | None]],
    status: str = ReceiptStatus.CONFIRMED.value,
    purchase_date: datetime | None = PURCHASED_AT,
) -> Receipt:
    receipt = Receipt(
        user_id=user.id,
        store_id=store.id if store else None,
        status=status,
        image_path=f"{user.id}/receipt.jpg",
        image_expires_at=EXPIRES_AT,
        purchase_date=purchase_date,
    )
    db.add(receipt)
    await db.flush()
    for raw_name, product in lines:
        db.add(
            ReceiptItem(
                receipt_id=receipt.id,
                product_id=product.id if product else None,
                raw_product_name=raw_name,
                quantity=Decimal("1"),
                unit_price=Decimal("25.00"),
                line_total=Decimal("25.00"),
            ),
        )
    await db.flush()
    return receipt


async def _products_of(db: AsyncSession, user: User) -> list[UserProduct]:
    result = await db.execute(
        select(UserProduct)
        .where(UserProduct.user_id == user.id)
        .order_by(UserProduct.display_name),
    )
    return list(result.scalars().all())


async def _aliases_of(db: AsyncSession, user: User) -> list[UserProductAlias]:
    result = await db.execute(
        select(UserProductAlias)
        .where(UserProductAlias.user_id == user.id)
        .order_by(UserProductAlias.normalized_text),
    )
    return list(result.scalars().all())


async def _stores_of(db: AsyncSession, user: User) -> list[UserStore]:
    result = await db.execute(
        select(UserStore).where(UserStore.user_id == user.id).order_by(UserStore.display_name),
    )
    return list(result.scalars().all())


async def test_two_users_with_the_same_raw_text_get_separate_products(db_session: AsyncSession):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    product = await _global_product(db_session, "MELK LETT 1L")
    user_a = await _user(db_session, "a@example.com")
    user_b = await _user(db_session, "b@example.com")
    await _receipt(db_session, user_a, store, [("MELK LETT 1L", product)])
    await _receipt(db_session, user_b, store, [("MELK LETT 1L", product)])

    await _run_backfill(db_session)

    products_a = await _products_of(db_session, user_a)
    products_b = await _products_of(db_session, user_b)
    assert len(products_a) == 1
    assert len(products_b) == 1
    assert products_a[0].id != products_b[0].id
    assert products_a[0].user_id == user_a.id
    assert products_b[0].user_id == user_b.id


async def test_alias_from_one_user_never_points_at_another_users_product(
    db_session: AsyncSession,
):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    product = await _global_product(db_session, "MELK LETT 1L")
    user_a = await _user(db_session, "a@example.com")
    user_b = await _user(db_session, "b@example.com")
    await _receipt(db_session, user_a, store, [("MELK LETT 1L", product)])
    await _receipt(db_session, user_b, store, [("MELK LETT 1L", product)])

    await _run_backfill(db_session)

    products_b = {product.id for product in await _products_of(db_session, user_b)}
    aliases_a = await _aliases_of(db_session, user_a)
    assert aliases_a
    assert all(alias.user_product_id not in products_b for alias in aliases_a)


async def test_user_without_own_confirmed_line_gets_no_private_catalog(
    db_session: AsyncSession,
):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    product = await _global_product(db_session, "MELK LETT 1L")
    user_a = await _user(db_session, "a@example.com")
    user_b = await _user(db_session, "b@example.com")
    await _receipt(db_session, user_a, store, [("MELK LETT 1L", product)])

    await _run_backfill(db_session)

    assert await _products_of(db_session, user_b) == []
    assert await _aliases_of(db_session, user_b) == []
    assert await _stores_of(db_session, user_b) == []
    assert await db_session.get(AccountLedger, user_b.id) is None


async def test_unconfirmed_receipt_lines_are_not_backfilled(db_session: AsyncSession):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    product = await _global_product(db_session, "MELK LETT 1L")
    user = await _user(db_session, "a@example.com")
    await _receipt(
        db_session,
        user,
        store,
        [("MELK LETT 1L", product)],
        status=ReceiptStatus.READY_FOR_REVIEW.value,
    )

    await _run_backfill(db_session)

    assert await _products_of(db_session, user) == []
    assert await _stores_of(db_session, user) == []


async def test_globally_matched_line_is_inherited_never_confirmed(db_session: AsyncSession):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    product = await _global_product(db_session, "MELK LETT 1L")
    user = await _user(db_session, "a@example.com")
    await _receipt(db_session, user, store, [("MELK LETT 1L", product)])

    await _run_backfill(db_session)

    (user_product,) = await _products_of(db_session, user)
    assert user_product.identity_status == IdentityStatus.INHERITED.value
    assert user_product.legacy_product_id == product.id
    assert user_product.version == 1


async def test_line_without_global_product_is_unresolved(db_session: AsyncSession):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    user = await _user(db_session, "a@example.com")
    await _receipt(db_session, user, store, [("YOGHURT", None)])

    await _run_backfill(db_session)

    (user_product,) = await _products_of(db_session, user)
    assert user_product.identity_status == IdentityStatus.UNRESOLVED.value
    assert user_product.legacy_product_id is None
    assert user_product.display_name == "YOGHURT"


async def test_display_name_comes_from_the_owners_own_receipt_text(db_session: AsyncSession):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    product = await _global_product(db_session, "MELK LETT 1L", "MELK LETT 1L", "H-MELK 1L")
    user_a = await _user(db_session, "a@example.com")
    user_b = await _user(db_session, "b@example.com")
    await _receipt(db_session, user_a, store, [("MELK LETT 1L", product)])
    await _receipt(db_session, user_b, store, [("H-MELK 1L", product)])

    await _run_backfill(db_session)

    (product_b,) = await _products_of(db_session, user_b)
    assert product_b.display_name == "H-MELK 1L"
    aliases_b = await _aliases_of(db_session, user_b)
    assert [alias.raw_text for alias in aliases_b] == ["H-MELK 1L"]
    assert "melk lett" not in " ".join(alias.normalized_text for alias in aliases_b)


async def test_alias_keeps_original_text_with_backfill_provenance(db_session: AsyncSession):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    product = await _global_product(db_session, "MELK LETT 1L")
    user = await _user(db_session, "a@example.com")
    await _receipt(db_session, user, store, [("MELK  Lett 1L", product)])

    await _run_backfill(db_session)

    (alias,) = await _aliases_of(db_session, user)
    assert alias.raw_text == "MELK  Lett 1L"
    assert alias.normalized_text == normalize_product_name("MELK  Lett 1L")
    assert alias.source == AliasSource.BACKFILL.value
    assert alias.match_method == AliasMatchMethod.INHERITED.value
    assert alias.store_id == store.id
    assert alias.chain == "Rema 1000"


async def test_same_product_in_two_stores_gets_one_alias_per_store(db_session: AsyncSession):
    first = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    second = await _store(db_session, "Kiwi Torshov", chain="Kiwi")
    product = await _global_product(db_session, "MELK LETT 1L")
    user = await _user(db_session, "a@example.com")
    await _receipt(db_session, user, first, [("MELK LETT 1L", product)])
    await _receipt(db_session, user, second, [("MELK LETT 1L", product)])

    await _run_backfill(db_session)

    (user_product,) = await _products_of(db_session, user)
    aliases = await _aliases_of(db_session, user)
    assert len(aliases) == 2
    assert {alias.store_id for alias in aliases} == {first.id, second.id}
    assert {alias.user_product_id for alias in aliases} == {user_product.id}


async def test_each_raw_text_for_the_same_product_becomes_its_own_alias(
    db_session: AsyncSession,
):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    product = await _global_product(db_session, "MELK LETT 1L", "MELK LETT 1L", "MELK LETT 1 5L")
    user = await _user(db_session, "a@example.com")
    await _receipt(db_session, user, store, [("MELK LETT 1L", product)])
    await _receipt(db_session, user, store, [("MELK LETT 1 5L", product)])

    await _run_backfill(db_session)

    (user_product,) = await _products_of(db_session, user)
    aliases = await _aliases_of(db_session, user)
    assert {alias.raw_text for alias in aliases} == {"MELK LETT 1L", "MELK LETT 1 5L"}
    assert {alias.user_product_id for alias in aliases} == {user_product.id}


async def test_store_with_known_chain_is_chain_only_not_branch(db_session: AsyncSession):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    user = await _user(db_session, "a@example.com")
    await _receipt(db_session, user, store, [("MELK LETT 1L", None)])

    await _run_backfill(db_session)

    (user_store,) = await _stores_of(db_session, user)
    assert user_store.identity_level == StoreIdentityLevel.CHAIN_ONLY.value
    assert user_store.chain == "Rema 1000"
    assert user_store.legacy_store_id == store.id
    assert user_store.display_name == "Rema 1000 Grunerlokka"
    assert user_store.branch_name is None


async def test_store_without_known_chain_is_unknown(db_session: AsyncSession):
    store = await _store(db_session, "Ukjent butikk", chain=None)
    user = await _user(db_session, "a@example.com")
    await _receipt(db_session, user, store, [("MELK LETT 1L", None)])

    await _run_backfill(db_session)

    (user_store,) = await _stores_of(db_session, user)
    assert user_store.identity_level == StoreIdentityLevel.UNKNOWN.value
    assert user_store.chain is None


async def test_two_branches_of_the_same_chain_stay_separate(db_session: AsyncSession):
    first = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    second = await _store(db_session, "Rema 1000 Torshov", chain="Rema 1000")
    user = await _user(db_session, "a@example.com")
    await _receipt(db_session, user, first, [("MELK LETT 1L", None)])
    await _receipt(db_session, user, second, [("MELK LETT 1L", None)])

    await _run_backfill(db_session)

    stores = await _stores_of(db_session, user)
    assert len(stores) == 2
    assert {store.legacy_store_id for store in stores} == {first.id, second.id}


async def test_account_ledger_starts_at_version_one(db_session: AsyncSession):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    user = await _user(db_session, "a@example.com")
    await _receipt(db_session, user, store, [("MELK LETT 1L", None)])

    await _run_backfill(db_session)

    ledger = await db_session.get(AccountLedger, user.id)
    assert ledger is not None
    assert ledger.price_data_version == 1


async def test_purchase_history_is_counted_from_the_owners_own_lines(db_session: AsyncSession):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    product = await _global_product(db_session, "MELK LETT 1L")
    user_a = await _user(db_session, "a@example.com")
    user_b = await _user(db_session, "b@example.com")
    await _receipt(db_session, user_a, store, [("MELK LETT 1L", product)])
    await _receipt(
        db_session,
        user_a,
        store,
        [("MELK LETT 1L", product)],
        purchase_date=PURCHASED_AT + timedelta(days=7),
    )
    await _receipt(db_session, user_b, store, [("MELK LETT 1L", product)])

    await _run_backfill(db_session)

    (product_a,) = await _products_of(db_session, user_a)
    (product_b,) = await _products_of(db_session, user_b)
    assert product_a.purchase_count == 2
    assert product_a.last_purchased_at is not None
    assert product_a.last_purchased_at.replace(tzinfo=timezone.utc) == PURCHASED_AT + timedelta(
        days=7,
    )
    assert product_b.purchase_count == 1


async def test_backfill_is_idempotent(db_session: AsyncSession):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    product = await _global_product(db_session, "MELK LETT 1L")
    user = await _user(db_session, "a@example.com")
    await _receipt(db_session, user, store, [("MELK LETT 1L", product), ("YOGHURT", None)])

    await _run_backfill(db_session)
    first = (
        len(await _products_of(db_session, user)),
        len(await _aliases_of(db_session, user)),
        len(await _stores_of(db_session, user)),
    )
    await _run_backfill(db_session)

    assert first == (2, 2, 1)
    assert (
        len(await _products_of(db_session, user)),
        len(await _aliases_of(db_session, user)),
        len(await _stores_of(db_session, user)),
    ) == first
    ledger_count = await db_session.execute(select(func.count()).select_from(AccountLedger))
    assert ledger_count.scalar_one() == 1


async def test_backfill_keeps_the_global_compatibility_tables(db_session: AsyncSession):
    store = await _store(db_session, "Rema 1000 Grunerlokka", chain="Rema 1000")
    product = await _global_product(db_session, "MELK LETT 1L")
    user = await _user(db_session, "a@example.com")
    await _receipt(db_session, user, store, [("MELK LETT 1L", product)])

    await _run_backfill(db_session)

    remaining = await db_session.execute(select(func.count()).select_from(ProductAlias))
    assert remaining.scalar_one() == 1
    assert await db_session.get(Product, product.id) is not None

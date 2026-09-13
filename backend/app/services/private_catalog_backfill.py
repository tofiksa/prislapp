"""S03-A: bygger privat katalog fra eierens egne bekreftede kvitteringslinjer.

Kjøres av migrering 005 og er idempotent. Tabellene beskrives eksplisitt her i
stedet for gjennom ORM-modellene, slik at senere kolonner ikke lekker inn i en
migrering som kjøres på et eldre skjema.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.models.user_product import (
    AliasMatchMethod,
    AliasSource,
    IdentityStatus,
    alias_context_key,
)
from app.models.user_store import StoreIdentityLevel
from app.services.product_service import normalize_product_name

CONFIRMED_STATUS = "CONFIRMED"
UNKNOWN_STORE_NAME = "Ukjent butikk"

_metadata = sa.MetaData()

users = sa.Table("users", _metadata, sa.Column("id", sa.Uuid(), primary_key=True))

stores = sa.Table(
    "stores",
    _metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("name", sa.String(255)),
    sa.Column("chain", sa.String(64)),
)

receipts = sa.Table(
    "receipts",
    _metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("user_id", sa.Uuid()),
    sa.Column("store_id", sa.Uuid()),
    sa.Column("purchase_date", sa.DateTime(timezone=True)),
    sa.Column("status", sa.String(32)),
)

receipt_items = sa.Table(
    "receipt_items",
    _metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("receipt_id", sa.Uuid()),
    sa.Column("product_id", sa.Uuid()),
    sa.Column("raw_product_name", sa.String(512)),
)

user_products = sa.Table(
    "user_products",
    _metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("user_id", sa.Uuid()),
    sa.Column("legacy_product_id", sa.Uuid()),
    sa.Column("display_name", sa.String(512)),
    sa.Column("pack_unit", sa.String(16)),
    sa.Column("identity_status", sa.String(16)),
    sa.Column("last_purchased_at", sa.DateTime(timezone=True)),
    sa.Column("purchase_count", sa.Integer()),
    sa.Column("version", sa.Integer()),
)

user_product_aliases = sa.Table(
    "user_product_aliases",
    _metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("user_id", sa.Uuid()),
    sa.Column("user_product_id", sa.Uuid()),
    sa.Column("normalized_text", sa.String(512)),
    sa.Column("raw_text", sa.String(512)),
    sa.Column("store_id", sa.Uuid()),
    sa.Column("chain", sa.String(64)),
    sa.Column("context_key", sa.String(64)),
    sa.Column("source", sa.String(16)),
    sa.Column("match_method", sa.String(16)),
)

user_stores = sa.Table(
    "user_stores",
    _metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("user_id", sa.Uuid()),
    sa.Column("legacy_store_id", sa.Uuid()),
    sa.Column("display_name", sa.String(255)),
    sa.Column("chain", sa.String(64)),
    sa.Column("branch_name", sa.String(255)),
    sa.Column("identity_level", sa.String(16)),
    sa.Column("version", sa.Integer()),
)

account_ledgers = sa.Table(
    "account_ledgers",
    _metadata,
    sa.Column("user_id", sa.Uuid(), primary_key=True),
    sa.Column("price_data_version", sa.Integer()),
)


@dataclass
class _AliasDraft:
    normalized_text: str
    raw_text: str
    store_id: uuid.UUID | None
    chain: str | None
    context_key: str


def _is_newer(candidate: datetime | None, current: datetime | None) -> bool:
    """Ukjent kjøpsdato er aldri nyere. Naive og tidssonebevisste verdier blandes ikke."""
    if candidate is None:
        return False
    if current is None:
        return True
    return candidate > current


@dataclass
class _ProductDraft:
    user_id: uuid.UUID
    legacy_product_id: uuid.UUID | None
    identity_status: str
    display_name: str = ""
    display_name_at: datetime | None = None
    purchase_count: int = 0
    last_purchased_at: datetime | None = None
    aliases: dict[tuple[str, str], _AliasDraft] = field(default_factory=dict)

    def add_line(self, alias: _AliasDraft, purchased_at: datetime | None) -> None:
        self.purchase_count += 1
        if _is_newer(purchased_at, self.last_purchased_at):
            self.last_purchased_at = purchased_at
        # Visningsnavnet er eierens nyeste egne varetekst, aldri global kanonisk tekst.
        if not self.display_name or _is_newer(purchased_at, self.display_name_at):
            self.display_name = alias.raw_text
            self.display_name_at = purchased_at
        # Hver varetekst i hver butikkontekst beholdes som eget alias.
        self.aliases.setdefault((alias.normalized_text, alias.context_key), alias)


def _normalized(raw_product_name: str) -> str:
    return normalize_product_name(raw_product_name) or raw_product_name.strip().lower()


def _confirmed_lines(connection: Connection) -> list[sa.Row]:
    query = (
        sa.select(
            receipts.c.user_id,
            receipts.c.store_id,
            receipts.c.purchase_date,
            receipt_items.c.id.label("line_id"),
            receipt_items.c.product_id,
            receipt_items.c.raw_product_name,
        )
        .select_from(
            receipt_items.join(receipts, receipts.c.id == receipt_items.c.receipt_id),
        )
        .where(sa.func.upper(receipts.c.status) == CONFIRMED_STATUS)
        .order_by(receipt_items.c.id)
    )
    return list(connection.execute(query))


def _collect_products(
    lines: list[sa.Row],
    store_rows: dict[uuid.UUID, sa.Row],
) -> dict[tuple[uuid.UUID, str, object], _ProductDraft]:
    drafts: dict[tuple[uuid.UUID, str, object], _ProductDraft] = {}
    for line in lines:
        normalized = _normalized(line.raw_product_name)
        store = store_rows.get(line.store_id) if line.store_id else None
        chain = store.chain if store else None
        alias = _AliasDraft(
            normalized_text=normalized,
            raw_text=line.raw_product_name,
            store_id=line.store_id,
            chain=chain,
            context_key=alias_context_key(line.store_id, chain),
        )
        if line.product_id is not None:
            # Global match er arvet, aldri bekreftet av eieren.
            key = (line.user_id, "legacy", line.product_id)
            status = IdentityStatus.INHERITED.value
            legacy_product_id = line.product_id
        else:
            # Ingen global opprinnelse: eieren har tekst, men ingen avklart identitet.
            key = (line.user_id, "text", normalized)
            status = IdentityStatus.UNRESOLVED.value
            legacy_product_id = None
        draft = drafts.setdefault(
            key,
            _ProductDraft(
                user_id=line.user_id,
                legacy_product_id=legacy_product_id,
                identity_status=status,
            ),
        )
        draft.add_line(alias, line.purchase_date)
    return drafts


def _existing_product_ids(connection: Connection) -> dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID]:
    query = sa.select(
        user_products.c.id,
        user_products.c.user_id,
        user_products.c.legacy_product_id,
    ).where(user_products.c.legacy_product_id.isnot(None))
    return {(row.user_id, row.legacy_product_id): row.id for row in connection.execute(query)}


def _existing_alias_targets(
    connection: Connection,
) -> dict[tuple[uuid.UUID, str, str], uuid.UUID]:
    query = sa.select(
        user_product_aliases.c.user_id,
        user_product_aliases.c.normalized_text,
        user_product_aliases.c.context_key,
        user_product_aliases.c.user_product_id,
    )
    return {
        (row.user_id, row.normalized_text, row.context_key): row.user_product_id
        for row in connection.execute(query)
    }


def _resolve_existing_id(
    draft: _ProductDraft,
    legacy_ids: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID],
    alias_targets: dict[tuple[uuid.UUID, str, str], uuid.UUID],
) -> uuid.UUID | None:
    if draft.legacy_product_id is not None:
        return legacy_ids.get((draft.user_id, draft.legacy_product_id))
    for alias in draft.aliases.values():
        existing = alias_targets.get((draft.user_id, alias.normalized_text, alias.context_key))
        if existing is not None:
            return existing
    return None


def _backfill_products(connection: Connection, lines: list[sa.Row]) -> None:
    store_rows = {
        row.id: row
        for row in connection.execute(sa.select(stores.c.id, stores.c.name, stores.c.chain))
    }
    drafts = _collect_products(lines, store_rows)
    legacy_ids = _existing_product_ids(connection)
    alias_targets = _existing_alias_targets(connection)

    new_products: list[dict] = []
    new_aliases: list[dict] = []
    for draft in drafts.values():
        product_id = _resolve_existing_id(draft, legacy_ids, alias_targets)
        if product_id is None:
            product_id = uuid.uuid4()
            new_products.append(
                {
                    "id": product_id,
                    "user_id": draft.user_id,
                    "legacy_product_id": draft.legacy_product_id,
                    "display_name": draft.display_name,
                    "pack_unit": "unknown",
                    "identity_status": draft.identity_status,
                    "last_purchased_at": draft.last_purchased_at,
                    "purchase_count": draft.purchase_count,
                    "version": 1,
                },
            )
        else:
            connection.execute(
                user_products.update()
                .where(user_products.c.id == product_id)
                .values(
                    last_purchased_at=draft.last_purchased_at,
                    purchase_count=draft.purchase_count,
                ),
            )
        for alias in draft.aliases.values():
            alias_key = (draft.user_id, alias.normalized_text, alias.context_key)
            if alias_key in alias_targets:
                continue
            alias_targets[alias_key] = product_id
            new_aliases.append(
                {
                    "id": uuid.uuid4(),
                    "user_id": draft.user_id,
                    "user_product_id": product_id,
                    "normalized_text": alias.normalized_text,
                    "raw_text": alias.raw_text,
                    "store_id": alias.store_id,
                    "chain": alias.chain,
                    "context_key": alias.context_key,
                    "source": AliasSource.BACKFILL.value,
                    "match_method": AliasMatchMethod.INHERITED.value,
                },
            )

    if new_products:
        connection.execute(user_products.insert(), new_products)
    if new_aliases:
        connection.execute(user_product_aliases.insert(), new_aliases)


def _backfill_stores(connection: Connection) -> None:
    query = (
        sa.select(receipts.c.user_id, stores.c.id, stores.c.name, stores.c.chain)
        .select_from(receipts.join(stores, stores.c.id == receipts.c.store_id))
        .where(sa.func.upper(receipts.c.status) == CONFIRMED_STATUS)
        .distinct()
    )
    existing = {
        (row.user_id, row.legacy_store_id)
        for row in connection.execute(
            sa.select(user_stores.c.user_id, user_stores.c.legacy_store_id),
        )
    }

    rows: list[dict] = []
    for row in connection.execute(query):
        if (row.user_id, row.id) in existing:
            continue
        existing.add((row.user_id, row.id))
        chain = row.chain or None
        rows.append(
            {
                "id": uuid.uuid4(),
                "user_id": row.user_id,
                "legacy_store_id": row.id,
                "display_name": row.name or chain or UNKNOWN_STORE_NAME,
                "chain": chain,
                # Gammelt butikkoppslag slår sammen på normalisert navn, så
                # filialen er ikke dokumentert. Aldri `branch` fra backfill.
                "branch_name": None,
                "identity_level": (
                    StoreIdentityLevel.CHAIN_ONLY.value
                    if chain
                    else StoreIdentityLevel.UNKNOWN.value
                ),
                "version": 1,
            },
        )
    if rows:
        connection.execute(user_stores.insert(), rows)


def _backfill_ledgers(connection: Connection, user_ids: set[uuid.UUID]) -> None:
    existing = {
        row.user_id for row in connection.execute(sa.select(account_ledgers.c.user_id))
    }
    rows = [
        {"user_id": user_id, "price_data_version": 1}
        for user_id in sorted(user_ids - existing, key=str)
    ]
    if rows:
        connection.execute(account_ledgers.insert(), rows)


def backfill_private_catalog(connection: Connection) -> None:
    """Opprett private produkter, aliaser, butikker og kontoteller for hver eier."""
    lines = _confirmed_lines(connection)
    _backfill_products(connection, lines)
    _backfill_stores(connection)

    owners = {line.user_id for line in lines}
    owners |= {
        row.user_id
        for row in connection.execute(
            sa.select(receipts.c.user_id)
            .where(sa.func.upper(receipts.c.status) == CONFIRMED_STATUS)
            .distinct(),
        )
    }
    _backfill_ledgers(connection, owners)

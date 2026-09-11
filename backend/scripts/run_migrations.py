#!/usr/bin/env python3
"""Apply Alembic migrations safely on databases bootstrapped via create_all()."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.database import engine

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Stabil nøkkel for pg_advisory_lock, slik at to samtidige oppgraderinger serialiseres.
MIGRATION_LOCK_ID = 831_524_007


class MigrationStateError(RuntimeError):
    """Skjemaet kan ikke knyttes til en kjent revisjon, så stamping ville vært gjetting."""


@dataclass(frozen=True)
class SchemaRevision:
    """Tabellene og kolonnene en revisjon oppretter, brukt til å verifisere skjemaet."""

    revision: str
    tables: Mapping[str, tuple[str, ...]]


# Tabellnærvær alene er ikke bevis for en revisjon; kolonnene kontrolleres også.
# Nye migreringer med skjemaendring må legges til her, og rene datamigreringer
# i DATA_ONLY_REVISIONS. Udeklarerte revisjoner gir MigrationStateError.
SCHEMA_REVISIONS: tuple[SchemaRevision, ...] = (
    SchemaRevision(
        "001",
        {"users": ("id", "email", "password_hash", "google_sub", "created_at")},
    ),
    SchemaRevision(
        "002",
        {
            "stores": ("id", "name", "normalized_name", "chain"),
            "receipts": (
                "id",
                "user_id",
                "store_id",
                "purchase_date",
                "total",
                "status",
                "image_path",
                "image_expires_at",
                "raw_ocr_text",
                "created_at",
            ),
            "receipt_items": (
                "id",
                "receipt_id",
                "product_id",
                "raw_product_name",
                "quantity",
                "unit_price",
                "line_total",
            ),
        },
    ),
    SchemaRevision(
        "003",
        {
            "products": ("id", "canonical_name", "category", "ean"),
            "product_aliases": ("id", "product_id", "alias_name", "store_id"),
            "price_observations": (
                "id",
                "user_id",
                "product_id",
                "store_id",
                "receipt_item_id",
                "price",
                "observed_at",
            ),
        },
    ),
    SchemaRevision(
        "005",
        {
            "user_products": (
                "id",
                "user_id",
                "legacy_product_id",
                "display_name",
                "brand",
                "variant",
                "pack_content",
                "pack_unit",
                "pack_count",
                "identity_status",
                "last_purchased_at",
                "purchase_count",
                "version",
                "created_at",
                "updated_at",
            ),
            "user_product_aliases": (
                "id",
                "user_id",
                "user_product_id",
                "normalized_text",
                "raw_text",
                "store_id",
                "chain",
                "context_key",
                "source",
                "match_method",
                "created_at",
            ),
            "user_stores": (
                "id",
                "user_id",
                "legacy_store_id",
                "display_name",
                "chain",
                "branch_name",
                "address",
                "identity_level",
                "raw_ocr_text",
                "version",
                "created_at",
                "updated_at",
            ),
            "account_ledgers": (
                "user_id",
                "price_data_version",
                "created_at",
                "updated_at",
            ),
        },
    ),
)

# Datamigreringer etterlater ingen skjemaspor. De kjøres på nytt etter stamping,
# så de må være idempotente: 004 regner prisen ut fra rå kvitteringslinjer.
DATA_ONLY_REVISIONS = frozenset({"004"})


def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def migration_revisions() -> tuple[str, ...]:
    """Alle revisjoner i alembic/versions, eldste først."""
    script_directory = ScriptDirectory.from_config(alembic_config())
    return tuple(reversed([script.revision for script in script_directory.walk_revisions()]))


def reapplied_data_revisions(revision: str) -> tuple[str, ...]:
    """Datamigreringer som kjøres på nytt fordi skjemaet stampes til `revision`."""
    revisions = migration_revisions()
    later = revisions[revisions.index(revision) + 1 :]
    return tuple(candidate for candidate in later if candidate in DATA_ONLY_REVISIONS)


def _schema_objects(revision: SchemaRevision) -> list[str]:
    objects: list[str] = []
    for table, columns in revision.tables.items():
        objects.append(table)
        objects.extend(f"{table}.{column}" for column in columns)
    return objects


async def _table_exists(table_name: str) -> bool:
    async with engine.connect() as conn:
        return await conn.run_sync(
            lambda connection: inspect(connection).has_table(table_name),
        )


async def _alembic_revision() -> str | None:
    if not await _table_exists("alembic_version"):
        return None

    query = text("SELECT version_num FROM alembic_version LIMIT 1")
    async with engine.connect() as conn:
        result = await conn.execute(query)
        row = result.first()
        return row[0] if row else None


async def _missing_schema_objects(revision: SchemaRevision) -> list[str]:
    def collect(connection) -> list[str]:
        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())
        missing: list[str] = []
        for table, columns in revision.tables.items():
            if table not in existing_tables:
                missing.append(table)
                missing.extend(f"{table}.{column}" for column in columns)
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table)}
            missing.extend(
                f"{table}.{column}" for column in columns if column not in existing_columns
            )
        return missing

    async with engine.connect() as conn:
        return await conn.run_sync(collect)


async def detect_schema_revision() -> str | None:
    """Nyeste revisjon som er verifisert i skjemaet, eller None for tom database."""
    missing_objects = {
        revision.revision: await _missing_schema_objects(revision)
        for revision in SCHEMA_REVISIONS
    }

    verified: list[str] = []
    for revision in SCHEMA_REVISIONS:
        if missing_objects[revision.revision]:
            break
        verified.append(revision.revision)

    for revision in SCHEMA_REVISIONS[len(verified) :]:
        missing = missing_objects[revision.revision]
        if not missing:
            raise MigrationStateError(
                f"Skjemaet har revisjon {revision.revision}, men mangler en tidligere "
                f"revisjon. Rett opp skjemaet manuelt; stamping ville vært gjetting."
            )
        if len(missing) < len(_schema_objects(revision)):
            raise MigrationStateError(
                f"Revisjon {revision.revision} er bare delvis til stede, mangler: "
                f"{', '.join(missing)}. Rett opp skjemaet manuelt; stamping ville "
                f"vært gjetting."
            )

    return verified[-1] if verified else None


async def _stamp_revision(revision: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS alembic_version (
                    version_num VARCHAR(32) NOT NULL,
                    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                )
                """
            ),
        )
        await conn.execute(text("DELETE FROM alembic_version"))
        await conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )


def _assert_revisions_declared() -> None:
    declared = {revision.revision for revision in SCHEMA_REVISIONS} | DATA_ONLY_REVISIONS
    undeclared = [
        revision for revision in migration_revisions() if revision not in declared
    ]
    if undeclared:
        raise MigrationStateError(
            f"Revisjon {', '.join(undeclared)} er ikke deklarert i SCHEMA_REVISIONS "
            f"eller DATA_ONLY_REVISIONS, så skjemaversjonen kan ikke verifiseres."
        )


async def prepare_migrations() -> None:
    current_revision = await _alembic_revision()
    if current_revision is not None:
        return

    _assert_revisions_declared()

    detected_revision = await detect_schema_revision()
    if detected_revision is None:
        return

    await _stamp_revision(detected_revision)
    reapplied = reapplied_data_revisions(detected_revision)
    message = f"Stamped existing schema to Alembic revision {detected_revision}"
    if reapplied:
        message += f"; data migrations re-applied: {', '.join(reapplied)}"
    print(message, file=sys.stderr)


@asynccontextmanager
async def migration_lock() -> AsyncIterator[None]:
    """Serialiser migreringer med advisory lock på PostgreSQL; ingen lås for andre dialekter."""
    if engine.dialect.name != "postgresql":
        yield
        return

    async with engine.connect() as connection:
        conn = await connection.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": MIGRATION_LOCK_ID},
        )
        try:
            yield
        finally:
            if not conn.closed:
                await conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": MIGRATION_LOCK_ID},
                )


async def upgrade_to_head() -> None:
    async with migration_lock():
        await prepare_migrations()
        # Alembic starter sin egen event loop, så oppgraderingen kjøres i en tråd.
        await asyncio.to_thread(command.upgrade, alembic_config(), "head")


def main() -> None:
    asyncio.run(upgrade_to_head())


if __name__ == "__main__":
    main()

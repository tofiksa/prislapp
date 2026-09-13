"""S06-A mot ekte PostgreSQL: samtidige mutasjoner, synsekvens og Decimal i SQL.

SQLite beviser ikke låser eller at to samtidige skrivere får hvert sitt
sekvensnummer, så idempotensen må vises her.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
from postgres_helpers import execute, fetch_all, fetch_scalar, run_migrations_cli
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.schemas.shopping_list import (
    ShoppingListCreateRequest,
    ShoppingListItemCreateRequest,
)
from app.services.shopping_list_service import ShoppingListService

pytestmark = pytest.mark.postgres

USER_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


@pytest.fixture
def migrated_url(postgres_url: str) -> str:
    result = run_migrations_cli(postgres_url)
    assert result.returncode == 0, result.stdout + result.stderr
    execute(
        postgres_url,
        [
            f"INSERT INTO users (id, email, password_hash) "
            f"VALUES ('{USER_ID}', 'a@example.com', 'hash')",
        ],
    )
    return postgres_url


def _run_concurrently(url: str, *calls) -> list:
    """Kjør tjenestekallene samtidig, hvert med sin egen sesjon og forbindelse."""

    async def run() -> list:
        engine = create_async_engine(url, poolclass=NullPool)
        maker = async_sessionmaker(engine, expire_on_commit=False)

        async def one(call):
            async with maker() as session:
                return await call(ShoppingListService(session))

        try:
            return await asyncio.gather(*(one(call) for call in calls))
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_two_concurrent_retries_of_the_same_mutation_create_one_list(migrated_url: str):
    request = ShoppingListCreateRequest(mutation_id=uuid.uuid4(), name="Ukeshandel")

    responses = _run_concurrently(
        migrated_url,
        lambda service: service.create_list(USER_ID, request),
        lambda service: service.create_list(USER_ID, request),
    )

    assert responses[0]["id"] == responses[1]["id"]
    assert fetch_scalar(migrated_url, "SELECT COUNT(*) FROM shopping_lists") == 1
    assert fetch_scalar(migrated_url, "SELECT COUNT(*) FROM shopping_list_mutations") == 1


def test_the_first_two_writes_on_a_fresh_account_both_succeed(migrated_url: str):
    """Synsekvensraden finnes ikke ennå. To enheter kan opprette den samtidig."""
    responses = _run_concurrently(
        migrated_url,
        lambda service: service.create_list(
            USER_ID,
            ShoppingListCreateRequest(mutation_id=uuid.uuid4(), name="Ukeshandel"),
        ),
        lambda service: service.create_list(
            USER_ID,
            ShoppingListCreateRequest(mutation_id=uuid.uuid4(), name="Fredagstaco"),
        ),
    )

    assert {response["name"] for response in responses} == {"Ukeshandel", "Fredagstaco"}
    sequences = [response["content_revision"] for response in responses]
    assert len(set(sequences)) == 2
    assert fetch_scalar(migrated_url, "SELECT sequence FROM shopping_list_sync_state") == max(
        sequences,
    )


def test_two_concurrent_lines_get_their_own_sequence_number(migrated_url: str):
    created = _run_concurrently(
        migrated_url,
        lambda service: service.create_list(
            USER_ID,
            ShoppingListCreateRequest(mutation_id=uuid.uuid4(), name="Ukeshandel"),
        ),
    )
    list_id = uuid.UUID(created[0]["id"])

    _run_concurrently(
        migrated_url,
        lambda service: service.create_item(
            USER_ID,
            list_id,
            ShoppingListItemCreateRequest(
                mutation_id=uuid.uuid4(),
                free_text="Melk",
                quantity=Decimal("1"),
                quantity_unit="each",
            ),
        ),
        lambda service: service.create_item(
            USER_ID,
            list_id,
            ShoppingListItemCreateRequest(
                mutation_id=uuid.uuid4(),
                free_text="Brød",
                quantity=Decimal("1"),
                quantity_unit="each",
            ),
        ),
    )

    sequences = [
        row[0]
        for row in fetch_all(migrated_url, "SELECT sync_seq FROM shopping_list_items")
    ]
    assert len(sequences) == 2
    assert len(set(sequences)) == 2
    assert fetch_scalar(migrated_url, "SELECT sequence FROM shopping_list_sync_state") == max(
        sequences,
    )


def test_a_weight_quantity_keeps_three_decimals_through_the_service(migrated_url: str):
    created = _run_concurrently(
        migrated_url,
        lambda service: service.create_list(
            USER_ID,
            ShoppingListCreateRequest(mutation_id=uuid.uuid4(), name="Ukeshandel"),
        ),
    )

    _run_concurrently(
        migrated_url,
        lambda service: service.create_item(
            USER_ID,
            uuid.UUID(created[0]["id"]),
            ShoppingListItemCreateRequest(
                mutation_id=uuid.uuid4(),
                free_text="Kaffe",
                quantity=Decimal("0.125"),
                quantity_unit="kg",
            ),
        ),
    )

    assert fetch_scalar(
        migrated_url,
        "SELECT quantity FROM shopping_list_items",
    ) == Decimal("0.125")

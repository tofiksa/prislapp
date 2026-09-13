"""S10-B: migrering 010 mot ekte PostgreSQL, der unik aktiv OCR-nøkkel er reell."""

import pytest
from postgres_helpers import (
    alembic_upgrade,
    execute,
    fetch_all,
    fetch_scalar,
    metadata_differences,
    run_backend,
    run_migrations_cli,
    table_names,
)

pytestmark = pytest.mark.postgres

USER_ID = "11111111-1111-1111-1111-111111111111"
RECEIPT_ID = "22222222-2222-2222-2222-222222222222"

NEW_TABLES = ("job_outbox",)

SEED = (
    f"INSERT INTO users (id, email, password_hash) "
    f"VALUES ('{USER_ID}', 'p0@example.com', 'hash')",
)


@pytest.fixture
def upgraded_database(postgres_url: str) -> str:
    alembic_upgrade(postgres_url, "009")
    execute(postgres_url, list(SEED))
    alembic_upgrade(postgres_url, "010")
    return postgres_url


def test_upgrade_creates_job_outbox_and_user_deleted_at(upgraded_database: str):
    assert set(NEW_TABLES) <= set(table_names(upgraded_database))
    columns = {
        row[0]
        for row in fetch_all(
            upgraded_database,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users'",
        )
    }
    assert "deleted_at" in columns


def test_the_migration_adds_no_outbox_rows(upgraded_database: str):
    assert fetch_scalar(upgraded_database, "SELECT COUNT(*) FROM job_outbox") == 0


def test_two_pending_ocr_jobs_for_the_same_receipt_are_rejected(upgraded_database: str):
    insert = (
        "INSERT INTO job_outbox (id, user_id, aggregate_type, aggregate_id, job_type, "
        "payload, status, attempt_count) VALUES (gen_random_uuid(), "
        f"'{USER_ID}', 'receipt', '{RECEIPT_ID}', 'ocr_process', '{{}}'::json, "
        "'pending', 0)"
    )
    execute(upgraded_database, [insert])

    with pytest.raises(Exception):
        execute(upgraded_database, [insert])


def test_a_new_job_is_allowed_after_the_previous_is_done(upgraded_database: str):
    execute(
        upgraded_database,
        [
            "INSERT INTO job_outbox (id, user_id, aggregate_type, aggregate_id, job_type, "
            "payload, status, attempt_count) VALUES (gen_random_uuid(), "
            f"'{USER_ID}', 'receipt', '{RECEIPT_ID}', 'ocr_process', '{{}}'::json, "
            "'done', 1)",
            "INSERT INTO job_outbox (id, user_id, aggregate_type, aggregate_id, job_type, "
            "payload, status, attempt_count) VALUES (gen_random_uuid(), "
            f"'{USER_ID}', 'receipt', '{RECEIPT_ID}', 'ocr_process', '{{}}'::json, "
            "'pending', 0)",
        ],
    )

    assert fetch_scalar(upgraded_database, "SELECT COUNT(*) FROM job_outbox") == 2


def test_downgrade_removes_outbox_and_keeps_auth_sessions(upgraded_database: str):
    result = run_backend(["-m", "alembic", "downgrade", "009"], upgraded_database)

    assert result.returncode == 0, result.stdout + result.stderr
    assert set(NEW_TABLES).isdisjoint(set(table_names(upgraded_database)))
    assert "refresh_sessions" in set(table_names(upgraded_database))


def test_migrated_schema_matches_the_models(postgres_url: str):
    assert run_migrations_cli(postgres_url).returncode == 0

    assert metadata_differences(postgres_url) == []

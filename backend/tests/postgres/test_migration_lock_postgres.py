"""Migreringslås mot ekte PostgreSQL: samtidige oppgraderinger må ikke ødelegge skjemaet."""

import subprocess
from pathlib import Path

import pytest
from postgres_helpers import (
    fetch_scalar,
    metadata_differences,
    start_backend,
    table_names,
)

from scripts import run_migrations

pytestmark = pytest.mark.postgres

LOCK_HOLDER = Path(__file__).parent / "advisory_lock_holder.py"
HEAD_REVISION = run_migrations.migration_revisions()[-1]


def _stamped_revision(url: str) -> str:
    return fetch_scalar(url, "SELECT version_num FROM alembic_version")


def test_second_migration_run_waits_for_the_advisory_lock(postgres_url):
    holder = start_backend(
        [str(LOCK_HOLDER), str(run_migrations.MIGRATION_LOCK_ID)], postgres_url
    )
    try:
        assert holder.stdout.readline().strip() == "locked"

        migration = start_backend(["-m", "scripts.run_migrations"], postgres_url)
        try:
            with pytest.raises(subprocess.TimeoutExpired):
                migration.wait(timeout=5)
            assert table_names(postgres_url) == []
        finally:
            holder.stdin.write("release\n")
            holder.stdin.flush()

        assert migration.wait(timeout=180) == 0
        assert _stamped_revision(postgres_url) == HEAD_REVISION
    finally:
        holder.kill()
        holder.wait(timeout=30)


def test_concurrent_migration_runs_reach_head_without_corrupting_schema(postgres_url):
    runs = [start_backend(["-m", "scripts.run_migrations"], postgres_url) for _ in range(2)]
    outputs = [run.communicate(timeout=180)[0] for run in runs]

    assert [run.returncode for run in runs] == [0, 0], outputs
    assert _stamped_revision(postgres_url) == HEAD_REVISION
    assert metadata_differences(postgres_url) == []

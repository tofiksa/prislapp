"""create job_outbox for OCR and optional users.deleted_at fence

Additiv: kvitteringsrader og auth-sesjoner røres ikke. Outbox er ikke
shopping_list_mutations. deleted_at er bare et gjerde for OCR/outbox.

Revision ID: 010
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

NEW_TABLES = ("job_outbox",)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "job_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("aggregate_type", sa.String(length=32), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_job_outbox_user_id", "job_outbox", ["user_id"])
    op.create_index(
        "ix_job_outbox_status_created_at",
        "job_outbox",
        ["status", "created_at"],
    )
    op.create_index(
        "uq_job_outbox_active_ocr",
        "job_outbox",
        ["job_type", "aggregate_id"],
        unique=True,
        sqlite_where=sa.text("status NOT IN ('done', 'failed_permanent')"),
        postgresql_where=sa.text("status NOT IN ('done', 'failed_permanent')"),
    )


def downgrade() -> None:
    op.drop_index("uq_job_outbox_active_ocr", table_name="job_outbox")
    op.drop_index("ix_job_outbox_status_created_at", table_name="job_outbox")
    op.drop_index("ix_job_outbox_user_id", table_name="job_outbox")
    for table in NEW_TABLES:
        op.drop_table(table)
    op.drop_column("users", "deleted_at")

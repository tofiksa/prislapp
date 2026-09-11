"""create receipt revisions, revision lines, v2 price observations and mutation keys

Additiv: `receipt_items`, `price_observations`, `purchase_date`, `unit_price` og
`line_total` beholdes uendret. Bekreftede kvitteringer får revisjon 1 som
gjeldende uten at v1-linjer slettes.

Revision ID: 007
"""

import sqlalchemy as sa
from alembic import op

from app.services.receipt_revision_backfill import backfill_receipt_revisions

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "price_observations_v2",
    "receipt_mutations",
    "receipt_revision_lines",
    "receipt_revisions",
)


def _timestamp(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def upgrade() -> None:
    # Gjeldende bekreftede revisjonsnummer. 0 betyr ingen bekreftet revisjon.
    op.add_column(
        "receipts",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "receipt_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("receipt_id", sa.Uuid(), sa.ForeignKey("receipts.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("mutation_id", sa.Uuid(), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "user_store_id",
            sa.Uuid(),
            sa.ForeignKey("user_stores.id"),
            nullable=True,
        ),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("purchase_time", sa.Time(), nullable=True),
        sa.Column(
            "date_precision",
            sa.String(length=16),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "date_source",
            sa.String(length=16),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("printed_total", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("computed_total", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "reconciliation_difference",
            sa.Numeric(precision=12, scale=2),
            nullable=True,
        ),
        sa.Column(
            "reconciliation_status",
            sa.String(length=16),
            nullable=False,
            server_default="unverifiable",
        ),
        sa.Column("reconciliation_reason", sa.String(length=32), nullable=True),
        sa.Column("gap_accepted", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        sa.UniqueConstraint("receipt_id", "revision", name="uq_receipt_revisions_number"),
    )
    op.create_index("ix_receipt_revisions_receipt_id", "receipt_revisions", ["receipt_id"])
    op.create_index("ix_receipt_revisions_user_id", "receipt_revisions", ["user_id"])
    op.create_index(
        "ix_receipt_revisions_user_receipt",
        "receipt_revisions",
        ["user_id", "receipt_id"],
    )

    op.create_table(
        "receipt_revision_lines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "revision_id",
            sa.Uuid(),
            sa.ForeignKey("receipt_revisions.id"),
            nullable=False,
        ),
        # Klientgenerert, stabil linje-ID. Den peker ikke på `receipt_items`,
        # fordi v1-linjene står urørt som rå avlesning.
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("raw_product_name", sa.String(length=512), nullable=False),
        sa.Column(
            "user_product_id",
            sa.Uuid(),
            sa.ForeignKey("user_products.id"),
            nullable=True,
        ),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("quantity_unit", sa.String(length=16), nullable=False),
        sa.Column("line_type", sa.String(length=16), nullable=False),
        sa.Column("net_line_total", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("printed_unit_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("price_basis", sa.String(length=16), nullable=False),
        sa.Column("condition", sa.String(length=16), nullable=False),
        # Null er ukjent valuta, ikke NOK.
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("comparison_price", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("eligible", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "eligible_for_dated_ranking",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("exclusion_reasons", sa.JSON(), nullable=False),
        sa.UniqueConstraint("revision_id", "line_id", name="uq_receipt_revision_lines_line"),
    )
    op.create_index(
        "ix_receipt_revision_lines_revision_id",
        "receipt_revision_lines",
        ["revision_id"],
    )
    op.create_index(
        "ix_receipt_revision_lines_line_id",
        "receipt_revision_lines",
        ["line_id"],
    )

    op.create_table(
        "price_observations_v2",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "user_product_id",
            sa.Uuid(),
            sa.ForeignKey("user_products.id"),
            nullable=False,
        ),
        sa.Column(
            "user_store_id",
            sa.Uuid(),
            sa.ForeignKey("user_stores.id"),
            nullable=False,
        ),
        sa.Column("receipt_id", sa.Uuid(), sa.ForeignKey("receipts.id"), nullable=False),
        sa.Column(
            "revision_id",
            sa.Uuid(),
            sa.ForeignKey("receipt_revisions.id"),
            nullable=False,
        ),
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("price_basis", sa.String(length=16), nullable=False),
        sa.Column("quantity_unit", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("date_precision", sa.String(length=16), nullable=False),
        sa.Column("condition", sa.String(length=16), nullable=False),
        sa.Column("quality_status", sa.String(length=24), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="1"),
        _timestamp("created_at"),
    )
    for column in ("user_id", "user_product_id", "user_store_id", "receipt_id", "revision_id"):
        op.create_index(
            f"ix_price_observations_v2_{column}",
            "price_observations_v2",
            [column],
        )
    op.create_index(
        "ix_price_observations_v2_current",
        "price_observations_v2",
        ["user_id", "user_product_id", "is_current"],
    )

    op.create_table(
        "receipt_mutations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("mutation_id", sa.Uuid(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), sa.ForeignKey("receipts.id"), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        _timestamp("created_at"),
        sa.UniqueConstraint(
            "user_id",
            "operation",
            "mutation_id",
            name="uq_receipt_mutations_key",
        ),
    )
    op.create_index("ix_receipt_mutations_user_id", "receipt_mutations", ["user_id"])
    op.create_index("ix_receipt_mutations_receipt_id", "receipt_mutations", ["receipt_id"])

    backfill_receipt_revisions(op.get_bind())


def downgrade() -> None:
    # Bare det nye laget fjernes. `receipt_items`, `price_observations` og
    # `purchase_date` er kjøpsgrunnlag og røres ikke.
    for table in NEW_TABLES:
        op.drop_table(table)
    with op.batch_alter_table("receipts") as batch:
        batch.drop_column("version")

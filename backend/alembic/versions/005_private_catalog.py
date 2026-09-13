"""create private user_products, aliases, user_stores and account_ledgers

Additiv: ingen eksisterende tabell endres eller slettes. Backfillen leser bare
eierens egne bekreftede kvitteringslinjer og kan kjøres på nytt.

Revision ID: 005
"""

import sqlalchemy as sa
from alembic import op

from app.services.private_catalog_backfill import backfill_private_catalog

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_products",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "legacy_product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id"),
            nullable=True,
        ),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("variant", sa.String(length=255), nullable=True),
        sa.Column("pack_content", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("pack_unit", sa.String(length=16), nullable=False),
        sa.Column("pack_count", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("identity_status", sa.String(length=16), nullable=False),
        sa.Column("last_purchased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purchase_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "legacy_product_id", name="uq_user_products_legacy"),
    )
    op.create_index("ix_user_products_user_id", "user_products", ["user_id"])
    op.create_index(
        "ix_user_products_user_display_name",
        "user_products",
        ["user_id", "display_name"],
    )
    op.create_index(
        "ix_user_products_user_last_purchased_at",
        "user_products",
        ["user_id", "last_purchased_at"],
    )
    op.create_index(
        "ix_user_products_user_purchase_count",
        "user_products",
        ["user_id", "purchase_count"],
    )

    op.create_table(
        "user_product_aliases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "user_product_id",
            sa.Uuid(),
            sa.ForeignKey("user_products.id"),
            nullable=False,
        ),
        sa.Column("normalized_text", sa.String(length=512), nullable=False),
        sa.Column("raw_text", sa.String(length=512), nullable=True),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("chain", sa.String(length=64), nullable=True),
        sa.Column("context_key", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("match_method", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "normalized_text",
            "context_key",
            name="uq_user_product_aliases_context",
        ),
    )
    op.create_index("ix_user_product_aliases_user_id", "user_product_aliases", ["user_id"])
    op.create_index(
        "ix_user_product_aliases_user_product_id",
        "user_product_aliases",
        ["user_product_id"],
    )
    op.create_index(
        "ix_user_product_aliases_user_text",
        "user_product_aliases",
        ["user_id", "normalized_text"],
    )

    op.create_table(
        "user_stores",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("legacy_store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("chain", sa.String(length=64), nullable=True),
        sa.Column("branch_name", sa.String(length=255), nullable=True),
        sa.Column("address", sa.String(length=512), nullable=True),
        sa.Column("identity_level", sa.String(length=16), nullable=False),
        sa.Column("raw_ocr_text", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "legacy_store_id", name="uq_user_stores_legacy"),
    )
    op.create_index("ix_user_stores_user_id", "user_stores", ["user_id"])
    op.create_index(
        "ix_user_stores_user_display_name",
        "user_stores",
        ["user_id", "display_name"],
    )

    op.create_table(
        "account_ledgers",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("price_data_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    backfill_private_catalog(op.get_bind())


def downgrade() -> None:
    # Bare de nye tabellene fjernes. `products`, `product_aliases` og
    # `price_observations` er kjøpsgrunnlag og røres ikke.
    op.drop_table("account_ledgers")
    op.drop_index("ix_user_stores_user_display_name", table_name="user_stores")
    op.drop_index("ix_user_stores_user_id", table_name="user_stores")
    op.drop_table("user_stores")
    op.drop_index("ix_user_product_aliases_user_text", table_name="user_product_aliases")
    op.drop_index("ix_user_product_aliases_user_product_id", table_name="user_product_aliases")
    op.drop_index("ix_user_product_aliases_user_id", table_name="user_product_aliases")
    op.drop_table("user_product_aliases")
    op.drop_index("ix_user_products_user_purchase_count", table_name="user_products")
    op.drop_index("ix_user_products_user_last_purchased_at", table_name="user_products")
    op.drop_index("ix_user_products_user_display_name", table_name="user_products")
    op.drop_index("ix_user_products_user_id", table_name="user_products")
    op.drop_table("user_products")

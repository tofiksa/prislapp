"""create products product_aliases price_observations tables

Revision ID: 003
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("canonical_name", sa.String(length=512), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("ean", sa.String(length=32), nullable=True),
    )

    op.create_table(
        "product_aliases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("alias_name", sa.String(length=512), nullable=False),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=True),
    )
    op.create_index("ix_product_aliases_product_id", "product_aliases", ["product_id"])
    op.create_index("ix_product_aliases_alias_name", "product_aliases", ["alias_name"])

    op.create_table(
        "price_observations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column(
            "receipt_item_id",
            sa.Uuid(),
            sa.ForeignKey("receipt_items.id"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_price_observations_user_id", "price_observations", ["user_id"])
    op.create_index("ix_price_observations_product_id", "price_observations", ["product_id"])
    op.create_index("ix_price_observations_store_id", "price_observations", ["store_id"])
    op.create_index(
        "ix_price_observations_receipt_item_id",
        "price_observations",
        ["receipt_item_id"],
    )

    with op.batch_alter_table("receipt_items") as batch_op:
        batch_op.create_foreign_key(
            "fk_receipt_items_product_id",
            "products",
            ["product_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("receipt_items") as batch_op:
        batch_op.drop_constraint("fk_receipt_items_product_id", type_="foreignkey")

    op.drop_index("ix_price_observations_receipt_item_id", table_name="price_observations")
    op.drop_index("ix_price_observations_store_id", table_name="price_observations")
    op.drop_index("ix_price_observations_product_id", table_name="price_observations")
    op.drop_index("ix_price_observations_user_id", table_name="price_observations")
    op.drop_table("price_observations")
    op.drop_index("ix_product_aliases_alias_name", table_name="product_aliases")
    op.drop_index("ix_product_aliases_product_id", table_name="product_aliases")
    op.drop_table("product_aliases")
    op.drop_table("products")

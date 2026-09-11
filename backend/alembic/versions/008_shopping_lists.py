"""create shopping lists, list items, list mutation keys and the sync sequence

Additiv: ingenting i kvitteringslaget endres, og migreringen fyller ingen rader.
Slettemarkører (`deleted_at`) er egne kolonner, fordi en klient som har vært
uten nett må få vite at en rad er borte i stedet for å legge den inn igjen.

Revision ID: 008
"""

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "shopping_list_mutations",
    "shopping_list_items",
    "shopping_list_sync_state",
    "shopping_lists",
)


def _timestamp(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "shopping_lists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        # Listens egne felter. En linjeendring rører den ikke, slik at et
        # offline navnebytte ikke blir en konflikt.
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        # Kontoens synsekvens for siste endring på listen eller en av linjene.
        sa.Column("content_seq", sa.Integer(), nullable=False, server_default="0"),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_shopping_lists_user_id", "shopping_lists", ["user_id"])
    op.create_index(
        "ix_shopping_lists_user_content_seq",
        "shopping_lists",
        ["user_id", "content_seq"],
    )
    op.create_index(
        "ix_shopping_lists_user_created_at",
        "shopping_lists",
        ["user_id", "created_at"],
    )

    op.create_table(
        "shopping_list_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # Eieren gjentas her, slik at private oppslag ikke må gå via listen.
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "list_id",
            sa.Uuid(),
            sa.ForeignKey("shopping_lists.id"),
            nullable=False,
        ),
        # Enten privat vare eller fritekst. Fritekst slås ikke sammen med en
        # kjent vare, så begge kolonnene er nullbare.
        sa.Column(
            "user_product_id",
            sa.Uuid(),
            sa.ForeignKey("user_products.id"),
            nullable=True,
        ),
        sa.Column("free_text", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column(
            "quantity_unit",
            sa.String(length=16),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sync_seq", sa.Integer(), nullable=False, server_default="0"),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_shopping_list_items_user_id", "shopping_list_items", ["user_id"])
    op.create_index("ix_shopping_list_items_list_id", "shopping_list_items", ["list_id"])
    op.create_index(
        "ix_shopping_list_items_user_sync_seq",
        "shopping_list_items",
        ["user_id", "sync_seq"],
    )
    op.create_index(
        "ix_shopping_list_items_list_position",
        "shopping_list_items",
        ["list_id", "position"],
    )

    op.create_table(
        "shopping_list_mutations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        # Eget operasjonsenum. Kvitteringsnøklene bor i `receipt_mutations`.
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("mutation_id", sa.Uuid(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "list_id",
            sa.Uuid(),
            sa.ForeignKey("shopping_lists.id"),
            nullable=True,
        ),
        sa.Column(
            "item_id",
            sa.Uuid(),
            sa.ForeignKey("shopping_list_items.id"),
            nullable=True,
        ),
        sa.Column("response", sa.JSON(), nullable=False),
        _timestamp("created_at"),
        sa.UniqueConstraint(
            "user_id",
            "operation",
            "mutation_id",
            name="uq_shopping_list_mutations_key",
        ),
    )
    op.create_index(
        "ix_shopping_list_mutations_user_id",
        "shopping_list_mutations",
        ["user_id"],
    )
    op.create_index(
        "ix_shopping_list_mutations_list_id",
        "shopping_list_mutations",
        ["list_id"],
    )

    op.create_table(
        "shopping_list_sync_state",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        # Kontoens monotone synsekvens. Uavhengig av `price_data_version`:
        # en listeendring er ikke en prisendring.
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        _timestamp("created_at"),
        _timestamp("updated_at"),
    )


def downgrade() -> None:
    # Bare listelaget fjernes. Kvitteringer, revisjoner og prisobservasjoner
    # er kjøpsgrunnlag og røres ikke.
    for table in NEW_TABLES:
        op.drop_table(table)

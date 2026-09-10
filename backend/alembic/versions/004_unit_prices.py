"""Normalize historical observations to price per unit and corrected receipt store."""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE price_observations SET price = (
            SELECT ROUND(1.0 * receipt_items.line_total / receipt_items.quantity, 2)
            FROM receipt_items WHERE receipt_items.id = price_observations.receipt_item_id
        ) WHERE receipt_item_id IN (SELECT id FROM receipt_items WHERE quantity > 0)
    """)
    op.execute("""
        UPDATE price_observations SET store_id = (
            SELECT receipts.store_id FROM receipts
            JOIN receipt_items ON receipt_items.receipt_id = receipts.id
            WHERE receipt_items.id = price_observations.receipt_item_id
        ) WHERE receipt_item_id IN (
            SELECT receipt_items.id FROM receipt_items JOIN receipts ON receipts.id = receipt_items.receipt_id
            WHERE receipts.store_id IS NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE price_observations SET price = (
            SELECT line_total FROM receipt_items WHERE receipt_items.id = price_observations.receipt_item_id
        )
    """)

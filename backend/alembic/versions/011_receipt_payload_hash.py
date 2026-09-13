"""add receipt payload_hash and decoded image metadata

Additiv: eksisterende kvitteringer og job_outbox røres ikke. payload_hash
er SHA-256 av rå opplastingsbytes (hex 64). image_width/image_height er
dekodet størrelse. content_type er image/jpeg eller image/png etter
dekoding. Ingen stille nedskalering.

Revision ID: 011
"""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receipts",
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
    )
    op.add_column("receipts", sa.Column("image_width", sa.Integer(), nullable=True))
    op.add_column("receipts", sa.Column("image_height", sa.Integer(), nullable=True))
    op.add_column(
        "receipts",
        sa.Column("content_type", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receipts", "content_type")
    op.drop_column("receipts", "image_height")
    op.drop_column("receipts", "image_width")
    op.drop_column("receipts", "payload_hash")

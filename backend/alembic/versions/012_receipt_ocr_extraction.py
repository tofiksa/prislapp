"""Add OCR extraction metadata to receipts.

Revision ID: 012
"""

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "receipts",
        sa.Column("ocr_extraction_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "receipts",
        sa.Column("ocr_quality", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "receipts",
        sa.Column("ocr_pipeline_version", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receipts", "ocr_pipeline_version")
    op.drop_column("receipts", "ocr_quality")
    op.drop_column("receipts", "ocr_extraction_json")

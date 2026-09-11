"""add date precision, line types, units, conditions and net line totals

Additiv: `purchase_date`, `unit_price` og `line_total` beholdes uendret. Gamle
rader får `unknown`, ikke gjettet enhet eller linjetype, og `purchase_date`
backfilles aldri fra `created_at`.

Revision ID: 006
"""

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

UNKNOWN = "unknown"

RECEIPT_COLUMNS = ("purchase_time", "date_precision", "date_source")
RECEIPT_ITEM_COLUMNS = (
    "line_type",
    "net_line_total",
    "printed_unit_price",
    "quantity_unit",
    "price_basis",
    "condition",
)

# Kjent dato uten sikkert klokkeslett er `date`. Midnatt er ikke et bevis på
# tidspunkt, så presisjonen oppgraderes ikke til `datetime`.
SET_DATE_PRECISION = """
UPDATE receipts
SET date_precision = 'date'
WHERE purchase_date IS NOT NULL
"""

# `printed_unit_price` er det leste feltet. Den gamle `unit_price` speiles hit
# og blir stående der den er.
COPY_PRINTED_UNIT_PRICE = """
UPDATE receipt_items
SET printed_unit_price = unit_price
WHERE unit_price IS NOT NULL
"""

# Nettosummen er bare avklart når kvitteringen er bekreftet og ingen linje på
# samme kvittering kan være en separat rabatt- eller returlinje. Ellers står
# `net_line_total` som null til brukeren avklarer den.
COPY_NET_LINE_TOTAL = """
UPDATE receipt_items
SET net_line_total = line_total
WHERE receipt_id IN (SELECT id FROM receipts WHERE UPPER(status) = 'CONFIRMED')
  AND receipt_id NOT IN (SELECT receipt_id FROM receipt_items WHERE line_total < 0)
"""


def _unknown_column(name: str, length: int = 16) -> sa.Column:
    return sa.Column(
        name,
        sa.String(length=length),
        nullable=False,
        server_default=UNKNOWN,
    )


def upgrade() -> None:
    op.add_column("receipts", sa.Column("purchase_time", sa.Time(), nullable=True))
    op.add_column("receipts", _unknown_column("date_precision"))
    op.add_column("receipts", _unknown_column("date_source"))

    op.add_column("receipt_items", _unknown_column("line_type"))
    op.add_column(
        "receipt_items",
        sa.Column("net_line_total", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "receipt_items",
        sa.Column("printed_unit_price", sa.Numeric(precision=10, scale=2), nullable=True),
    )
    op.add_column("receipt_items", _unknown_column("quantity_unit"))
    op.add_column("receipt_items", _unknown_column("price_basis"))
    op.add_column("receipt_items", _unknown_column("condition"))

    op.execute(SET_DATE_PRECISION)
    op.execute(COPY_PRINTED_UNIT_PRICE)
    op.execute(COPY_NET_LINE_TOTAL)


def downgrade() -> None:
    # Bare de nye kolonnene fjernes. Rå kjøpsgrunnlag i `unit_price`,
    # `line_total` og `purchase_date` røres ikke.
    with op.batch_alter_table("receipt_items") as batch:
        for column in RECEIPT_ITEM_COLUMNS:
            batch.drop_column(column)
    with op.batch_alter_table("receipts") as batch:
        for column in RECEIPT_COLUMNS:
            batch.drop_column(column)

"""S05-A: gir bekreftede v1-kvitteringer revisjon 1 som gjeldende.

Kjøres av migrering 007 og er idempotent. Tabellene beskrives eksplisitt her i
stedet for gjennom ORM-modellene, slik at senere kolonner ikke lekker inn i en
migrering som kjøres på et eldre skjema.

Backfillen gjetter ingenting. Linjene kopieres med verdiene 006 satte, og
`evaluate_line` avgjør at de ikke er rangerbare fordi enhet, valuta og identitet
er ukjent. Revisjonen merkes som ikke avstemt: den gamle bekreftelsesstien
sammenlignet aldri linjesummen med trykt total.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.domain.pricing import (
    Condition,
    DatePrecision,
    LineType,
    PricingLine,
    evaluate_line,
)
from app.domain.units import QuantityUnit

CONFIRMED_STATUS = "CONFIRMED"
CONFIRMED_REVISION = 1
LEGACY_CONFIRMATION = "legacy_confirmation"
UNVERIFIABLE = "unverifiable"

_metadata = sa.MetaData()

receipts = sa.Table(
    "receipts",
    _metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("user_id", sa.Uuid()),
    sa.Column("status", sa.String(32)),
    sa.Column("purchase_date", sa.DateTime(timezone=True)),
    sa.Column("purchase_time", sa.Time()),
    sa.Column("date_precision", sa.String(16)),
    sa.Column("date_source", sa.String(16)),
    sa.Column("total", sa.Numeric(10, 2)),
    sa.Column("version", sa.Integer()),
)

receipt_items = sa.Table(
    "receipt_items",
    _metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("receipt_id", sa.Uuid()),
    sa.Column("raw_product_name", sa.String(512)),
    sa.Column("quantity", sa.Numeric(10, 3)),
    sa.Column("line_type", sa.String(16)),
    sa.Column("net_line_total", sa.Numeric(12, 2)),
    sa.Column("printed_unit_price", sa.Numeric(10, 2)),
    sa.Column("quantity_unit", sa.String(16)),
    sa.Column("price_basis", sa.String(16)),
    sa.Column("condition", sa.String(16)),
)

receipt_revisions = sa.Table(
    "receipt_revisions",
    _metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("receipt_id", sa.Uuid()),
    sa.Column("user_id", sa.Uuid()),
    sa.Column("revision", sa.Integer()),
    sa.Column("status", sa.String(16)),
    sa.Column("operation", sa.String(32)),
    sa.Column("user_store_id", sa.Uuid()),
    sa.Column("purchase_date", sa.Date()),
    sa.Column("purchase_time", sa.Time()),
    sa.Column("date_precision", sa.String(16)),
    sa.Column("date_source", sa.String(16)),
    sa.Column("printed_total", sa.Numeric(12, 2)),
    sa.Column("computed_total", sa.Numeric(12, 2)),
    sa.Column("reconciliation_difference", sa.Numeric(12, 2)),
    sa.Column("reconciliation_status", sa.String(16)),
    sa.Column("reconciliation_reason", sa.String(32)),
    sa.Column("gap_accepted", sa.Boolean()),
    sa.Column("confirmed_at", sa.DateTime(timezone=True)),
)

receipt_revision_lines = sa.Table(
    "receipt_revision_lines",
    _metadata,
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("revision_id", sa.Uuid()),
    sa.Column("line_id", sa.Uuid()),
    sa.Column("position", sa.Integer()),
    sa.Column("raw_product_name", sa.String(512)),
    sa.Column("user_product_id", sa.Uuid()),
    sa.Column("quantity", sa.Numeric(12, 3)),
    sa.Column("quantity_unit", sa.String(16)),
    sa.Column("line_type", sa.String(16)),
    sa.Column("net_line_total", sa.Numeric(12, 2)),
    sa.Column("printed_unit_price", sa.Numeric(10, 2)),
    sa.Column("price_basis", sa.String(16)),
    sa.Column("condition", sa.String(16)),
    sa.Column("currency", sa.String(3)),
    sa.Column("comparison_price", sa.Numeric(20, 6)),
    sa.Column("eligible", sa.Boolean()),
    sa.Column("eligible_for_dated_ranking", sa.Boolean()),
    sa.Column("exclusion_reasons", sa.JSON()),
)


def _enum_value(enum_type, raw: str | None):
    """Ukjent eller manglende tekst blir `unknown`, aldri en gjettet verdi."""
    try:
        return enum_type(raw)
    except ValueError:
        return enum_type("unknown")


def _date_precision(receipt: sa.Row) -> str:
    """Samme slutning som 006: kjent dato er `date`, aldri `datetime`.

    v1-bekreftelsen skrev bare `purchase_date`, så en kvittering som ble
    bekreftet etter 006 kan ha kjent dato og `unknown` presisjon. En allerede
    satt presisjon nedgraderes ikke.
    """
    stored = receipt.date_precision
    if stored and stored != DatePrecision.UNKNOWN.value:
        return stored
    return (
        DatePrecision.DATE.value
        if receipt.purchase_date is not None
        else DatePrecision.UNKNOWN.value
    )


def _line_rows(connection: Connection, revision_id: uuid.UUID, receipt: sa.Row) -> list[dict]:
    # v1 lagrer ingen rekkefølge. Sortering på ID er stabil, men den er ikke en
    # påstand om rekkefølgen på kvitteringen.
    query = (
        sa.select(receipt_items)
        .where(receipt_items.c.receipt_id == receipt.id)
        .order_by(receipt_items.c.id)
    )
    date_precision = DatePrecision(_date_precision(receipt))
    rows: list[dict] = []
    for position, item in enumerate(connection.execute(query)):
        result = evaluate_line(
            PricingLine(
                line_type=_enum_value(LineType, item.line_type),
                # v1 leste aldri valuta. Null er ukjent, ikke NOK.
                currency=None,
                quantity=item.quantity,
                quantity_unit=_enum_value(QuantityUnit, item.quantity_unit),
                net_line_total=item.net_line_total,
                printed_unit_price=item.printed_unit_price,
                condition=_enum_value(Condition, item.condition),
                date_precision=date_precision,
            ),
        )
        rows.append(
            {
                "id": uuid.uuid4(),
                "revision_id": revision_id,
                "line_id": item.id,
                "position": position,
                "raw_product_name": item.raw_product_name,
                "user_product_id": None,
                "quantity": item.quantity,
                "quantity_unit": item.quantity_unit,
                "line_type": item.line_type,
                "net_line_total": item.net_line_total,
                "printed_unit_price": item.printed_unit_price,
                "price_basis": item.price_basis,
                "condition": item.condition,
                "currency": None,
                "comparison_price": result.comparison_price,
                "eligible": result.eligible,
                "eligible_for_dated_ranking": result.eligible_for_dated_ranking,
                "exclusion_reasons": [reason.value for reason in result.exclusion_reasons],
            },
        )
    return rows


def backfill_receipt_revisions(connection: Connection) -> None:
    """Opprett revisjon 1 for hver bekreftede kvittering som mangler den."""
    existing = {
        row.receipt_id
        for row in connection.execute(sa.select(receipt_revisions.c.receipt_id))
    }
    confirmed = connection.execute(
        sa.select(receipts)
        .where(sa.func.upper(receipts.c.status) == CONFIRMED_STATUS)
        .order_by(receipts.c.id),
    )

    revisions: list[dict] = []
    lines: list[dict] = []
    receipt_ids: list[uuid.UUID] = []
    for receipt in confirmed:
        if receipt.id in existing:
            continue
        revision_id = uuid.uuid4()
        receipt_ids.append(receipt.id)
        revisions.append(
            {
                "id": revision_id,
                "receipt_id": receipt.id,
                "user_id": receipt.user_id,
                "revision": CONFIRMED_REVISION,
                "status": "confirmed",
                "operation": "receipt_confirm",
                # v1 kjente bare den globale butikken. Privat butikk-ID avklares
                # først når eieren går gjennom kvitteringen.
                "user_store_id": None,
                "purchase_date": (
                    receipt.purchase_date.date() if receipt.purchase_date else None
                ),
                "purchase_time": receipt.purchase_time,
                "date_precision": _date_precision(receipt),
                "date_source": receipt.date_source,
                "printed_total": receipt.total,
                "computed_total": None,
                "reconciliation_difference": None,
                "reconciliation_status": UNVERIFIABLE,
                "reconciliation_reason": LEGACY_CONFIRMATION,
                "gap_accepted": False,
                # Bekreftelsestidspunktet ble aldri lagret i v1, og det gjettes ikke.
                "confirmed_at": None,
            },
        )
        lines.extend(_line_rows(connection, revision_id, receipt))

    if revisions:
        connection.execute(receipt_revisions.insert(), revisions)
    if lines:
        connection.execute(receipt_revision_lines.insert(), lines)
    if receipt_ids:
        connection.execute(
            receipts.update()
            .where(receipts.c.id.in_(receipt_ids))
            .values(version=CONFIRMED_REVISION),
        )

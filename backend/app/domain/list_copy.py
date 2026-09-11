"""S06-D: mapping fra liste- og kvitteringslinjer til nye handlelinjeverdier.

Ren modul: ingen HTTP, ingen database, ingen prisobservasjon. En kopi er aldri
et nytt kjøp. Slettet eller fremmed vare blir fritekst uten produkt-ID.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.domain.pricing import LineType
from app.domain.units import QuantityUnit

DEFAULT_QUANTITY = Decimal("1")
DEFAULT_UNIT = QuantityUnit.EACH.value
UNKNOWN_UNIT = QuantityUnit.UNKNOWN.value
PRODUCT_LINE_TYPE = LineType.PRODUCT.value


@dataclass(frozen=True)
class SourceListLine:
    id: uuid.UUID
    user_product_id: uuid.UUID | None
    free_text: str | None
    quantity: Decimal
    quantity_unit: str
    checked: bool
    position: int
    deleted: bool = False


@dataclass(frozen=True)
class SourceReceiptLine:
    line_type: str
    raw_product_name: str
    user_product_id: uuid.UUID | None = None
    quantity: Decimal | None = None
    quantity_unit: str | None = None
    deleted: bool = False
    position: int = 0


@dataclass(frozen=True)
class MappedListLine:
    user_product_id: uuid.UUID | None
    free_text: str | None
    quantity: Decimal
    quantity_unit: str


def resolve_wanted_quantity(
    quantity: Decimal | None,
    quantity_unit: str | None,
) -> tuple[Decimal, str]:
    """Ønsket handleantall. Gjett aldri kvitteringens enhet når den er ukjent."""
    unit = quantity_unit or UNKNOWN_UNIT
    if quantity is not None and unit != UNKNOWN_UNIT:
        return quantity, unit
    return DEFAULT_QUANTITY, DEFAULT_UNIT


def copy_list_lines(
    lines: list[SourceListLine],
    unchecked_only: bool = False,
) -> list[MappedListLine]:
    """Kopier kildelinjer i posisjonsrekkefølge. Avkryssing følger ikke med."""
    copied: list[MappedListLine] = []
    for line in sorted(lines, key=lambda item: (item.position, str(item.id))):
        if line.deleted:
            continue
        if unchecked_only and line.checked:
            continue
        copied.append(
            MappedListLine(
                user_product_id=line.user_product_id,
                free_text=line.free_text,
                quantity=line.quantity,
                quantity_unit=line.quantity_unit,
            ),
        )
    return copied


def map_receipt_lines(
    lines: list[SourceReceiptLine],
    owned_product_ids: set[uuid.UUID],
) -> list[MappedListLine]:
    """Bare produktlinjer. Pant, avgift, rabatt, retur og ukjent hoppes over."""
    mapped: list[MappedListLine] = []
    for line in sorted(lines, key=lambda item: (item.position, item.raw_product_name)):
        if line.deleted:
            continue
        if line.line_type != PRODUCT_LINE_TYPE:
            continue
        quantity, unit = resolve_wanted_quantity(line.quantity, line.quantity_unit)
        if line.user_product_id is not None and line.user_product_id in owned_product_ids:
            mapped.append(
                MappedListLine(
                    user_product_id=line.user_product_id,
                    free_text=None,
                    quantity=quantity,
                    quantity_unit=unit,
                ),
            )
            continue
        name = (line.raw_product_name or "").strip() or "Vare"
        mapped.append(
            MappedListLine(
                user_product_id=None,
                free_text=name,
                quantity=quantity,
                quantity_unit=unit,
            ),
        )
    return mapped

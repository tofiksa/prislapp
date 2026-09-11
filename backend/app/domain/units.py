from decimal import ROUND_HALF_UP, Decimal
from enum import Enum


class QuantityUnit(str, Enum):
    EACH = "each"
    KG = "kg"
    G = "g"
    L = "l"
    ML = "ml"
    UNKNOWN = "unknown"


_TO_BASE = {
    QuantityUnit.G: (Decimal("0.001"), QuantityUnit.KG),
    QuantityUnit.ML: (Decimal("0.001"), QuantityUnit.L),
}


def normalize_quantity(quantity: Decimal, unit: QuantityUnit) -> tuple[Decimal, QuantityUnit]:
    """Normalize g→kg and ml→l before comparison. Never convert each to kg."""
    if unit in (QuantityUnit.EACH, QuantityUnit.KG, QuantityUnit.L, QuantityUnit.UNKNOWN):
        return quantity, unit
    factor, target = _TO_BASE[unit]
    normalized = (quantity * factor).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return normalized, target

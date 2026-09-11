"""S04-A: kvalifisering og eksakt sammenligningspris for én kvitteringslinje.

Modulen er ren: den leser bare feltene den får inn, og den gjetter aldri enhet,
linjetype, vilkår eller dato. `eligible` betyr at linjen kan brukes som standard
prisgrunnlag. `eligible_for_dated_ranking` krever i tillegg kjent kjøpsdato;
ukjent dato utelukker bare den tidsbaserte påstanden, ikke selve observasjonen.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.domain.money import per_package_price, per_quantity_price
from app.domain.units import QuantityUnit, normalize_quantity


class LineType(str, Enum):
    PRODUCT = "product"
    DEPOSIT = "deposit"
    FEE = "fee"
    DISCOUNT = "discount"
    RETURN = "return"
    UNKNOWN = "unknown"


class PriceBasis(str, Enum):
    PER_PACKAGE = "per_package"
    PER_KG = "per_kg"
    PER_LITRE = "per_litre"
    UNKNOWN = "unknown"


class Condition(str, Enum):
    NONE = "none"
    MEMBER = "member"
    MULTI_BUY = "multi_buy"
    COUPON = "coupon"
    UNKNOWN = "unknown"


class DatePrecision(str, Enum):
    DATE = "date"
    DATETIME = "datetime"
    UNKNOWN = "unknown"


class DateSource(str, Enum):
    OCR = "ocr"
    USER = "user"
    UNKNOWN = "unknown"


class ExclusionReason(str, Enum):
    NON_PRODUCT_LINE = "non_product_line"
    NON_NOK = "non_nok"
    UNRESOLVED_IDENTITY = "unresolved_identity"
    CONDITIONAL = "conditional"
    UNKNOWN_CONDITION = "unknown_condition"
    UNKNOWN_DISCOUNT = "unknown_discount"
    UNKNOWN_UNIT = "unknown_unit"
    UNKNOWN_QUANTITY = "unknown_quantity"
    NON_POSITIVE_QUANTITY = "non_positive_quantity"
    UNKNOWN_DATE = "unknown_date"


# Bare eierens bekreftede identitet kan rangeres; arvet og uavklart kan ikke.
RANKABLE_IDENTITY_STATUSES = frozenset({"confirmed"})
COMPARISON_CURRENCY = "NOK"

_WEIGHT_UNITS = (QuantityUnit.KG, QuantityUnit.G)
_VOLUME_UNITS = (QuantityUnit.L, QuantityUnit.ML)


@dataclass(frozen=True)
class PricingLine:
    """Feltene en kvitteringslinje må ha for å kunne kvalifiseres.

    Standardverdiene er de ukjente. Gamle rader uten enhet eller linjetype blir
    dermed utelukket, ikke gjettet til `each` eller `product`.
    """

    line_type: LineType = LineType.UNKNOWN
    currency: str | None = None
    quantity: Decimal | None = None
    quantity_unit: QuantityUnit = QuantityUnit.UNKNOWN
    package_count: Decimal | None = None
    net_line_total: Decimal | None = None
    # Lest av kvitteringen og bevart, men aldri beregningsgrunnlag.
    printed_unit_price: Decimal | None = None
    condition: Condition = Condition.UNKNOWN
    user_product_id: uuid.UUID | None = None
    identity_status: str | None = None
    date_precision: DatePrecision = DatePrecision.UNKNOWN
    pack_content: Decimal | None = None
    pack_unit: QuantityUnit = QuantityUnit.UNKNOWN


@dataclass(frozen=True)
class PricingResult:
    eligible: bool
    comparison_price: Decimal | None
    price_basis: PriceBasis
    exclusion_reasons: tuple[ExclusionReason, ...]
    eligible_for_dated_ranking: bool


@dataclass(frozen=True)
class PackageIdentity:
    """Pakningen en linje gjelder. Likt navn er ikke lik pakning."""

    pack_content: Decimal | None = None
    pack_unit: QuantityUnit = QuantityUnit.UNKNOWN


def same_package_minimum(left: PackageIdentity, right: PackageIdentity) -> bool:
    """To linjer deler pakningsminimum bare når pakningsinnholdet er kjent og likt."""
    normalized = []
    for package in (left, right):
        if package.pack_content is None or package.pack_unit is QuantityUnit.UNKNOWN:
            return False
        normalized.append(normalize_quantity(package.pack_content, package.pack_unit))
    return normalized[0] == normalized[1]


def _basis_and_divisor(
    line: PricingLine,
) -> tuple[PriceBasis, Decimal | None, ExclusionReason | None]:
    """Prisgrunnlaget følger enheten; stk blir aldri kg uten kjent pakningsinnhold."""
    if line.quantity_unit is QuantityUnit.UNKNOWN:
        return PriceBasis.UNKNOWN, None, ExclusionReason.UNKNOWN_UNIT

    if line.quantity_unit is QuantityUnit.EACH:
        # For pakningsvarer er mengden antall pakninger.
        divisor = line.package_count if line.package_count is not None else line.quantity
        price_basis = PriceBasis.PER_PACKAGE
    else:
        price_basis = (
            PriceBasis.PER_KG
            if line.quantity_unit in _WEIGHT_UNITS
            else PriceBasis.PER_LITRE
        )
        divisor = (
            None
            if line.quantity is None
            else normalize_quantity(line.quantity, line.quantity_unit)[0]
        )

    if divisor is None:
        return price_basis, None, ExclusionReason.UNKNOWN_QUANTITY
    if divisor <= 0:
        return price_basis, None, ExclusionReason.NON_POSITIVE_QUANTITY
    return price_basis, divisor, None


def _qualification_reasons(line: PricingLine) -> list[ExclusionReason]:
    reasons: list[ExclusionReason] = []
    if line.line_type is not LineType.PRODUCT:
        # Pant, gebyr, retur, rabattlinjer og ukjent type er ikke vareminimum.
        reasons.append(ExclusionReason.NON_PRODUCT_LINE)
    if (line.currency or "").upper() != COMPARISON_CURRENCY:
        reasons.append(ExclusionReason.NON_NOK)
    if line.user_product_id is None or line.identity_status not in RANKABLE_IDENTITY_STATUSES:
        reasons.append(ExclusionReason.UNRESOLVED_IDENTITY)
    if line.condition is Condition.UNKNOWN:
        reasons.append(ExclusionReason.UNKNOWN_CONDITION)
    elif line.condition is not Condition.NONE:
        reasons.append(ExclusionReason.CONDITIONAL)
    return reasons


def evaluate_line(line: PricingLine) -> PricingResult:
    reasons = _qualification_reasons(line)
    price_basis, divisor, quantity_reason = _basis_and_divisor(line)
    if quantity_reason is not None:
        reasons.append(quantity_reason)
    if line.net_line_total is None:
        # Ufordelt rabatt gjør nettosummen ukjent, og da finnes ingen pris å rangere.
        reasons.append(ExclusionReason.UNKNOWN_DISCOUNT)

    comparison_price = None
    can_compute = (
        divisor is not None
        and line.net_line_total is not None
        and ExclusionReason.NON_NOK not in reasons
    )
    if can_compute:
        comparison_price = (
            per_package_price(line.net_line_total, divisor)
            if price_basis is PriceBasis.PER_PACKAGE
            else per_quantity_price(line.net_line_total, divisor)
        )

    # Rekkefølgen er bevisst: `eligible` avgjøres før datoen legges til, fordi
    # ukjent dato bare utelukker den daterte rangeringen.
    eligible = not reasons
    dated = line.date_precision is not DatePrecision.UNKNOWN
    if not dated:
        reasons.append(ExclusionReason.UNKNOWN_DATE)

    return PricingResult(
        eligible=eligible,
        comparison_price=comparison_price,
        price_basis=price_basis,
        exclusion_reasons=tuple(reasons),
        eligible_for_dated_ranking=eligible and dated,
    )


def standardized_quantity_price(line: PricingLine) -> tuple[PriceBasis, Decimal | None]:
    """Standardisert kr/kg eller kr/l fra pakningsinnhold.

    Verdien er et eget felt og skal aldri blandes inn i pakningsminimumet. Uten
    kjent pakningsinnhold finnes den ikke.
    """
    if line.pack_content is None or line.pack_unit is QuantityUnit.UNKNOWN:
        return PriceBasis.UNKNOWN, None
    if line.pack_unit is QuantityUnit.EACH or line.net_line_total is None:
        return PriceBasis.UNKNOWN, None

    packages = line.package_count if line.package_count is not None else line.quantity
    if packages is None or packages <= 0 or line.pack_content <= 0:
        return PriceBasis.UNKNOWN, None

    content, unit = normalize_quantity(line.pack_content, line.pack_unit)
    price_basis = PriceBasis.PER_KG if unit is QuantityUnit.KG else PriceBasis.PER_LITRE
    return price_basis, per_quantity_price(line.net_line_total, packages * content)

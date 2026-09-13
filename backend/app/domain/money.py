from decimal import ROUND_HALF_UP, Decimal

COMPARISON_QUANTUM = Decimal("0.000001")
NOK_QUANTUM = Decimal("0.01")
QUANTITY_QUANTUM = Decimal("0.001")


def display_nok(value: Decimal) -> str:
    """Round comparison or intermediate NOK amounts at the display boundary."""
    return str(value.quantize(NOK_QUANTUM, rounding=ROUND_HALF_UP))


def per_package_price(net_line_total: Decimal, package_count: Decimal) -> Decimal:
    if package_count <= 0:
        raise ValueError("package_count must be positive")
    return (net_line_total / package_count).quantize(COMPARISON_QUANTUM, rounding=ROUND_HALF_UP)


def per_quantity_price(net_line_total: Decimal, quantity: Decimal) -> Decimal:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return (net_line_total / quantity).quantize(COMPARISON_QUANTUM, rounding=ROUND_HALF_UP)

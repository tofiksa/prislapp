from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class ParsedReceiptItem:
    raw_name: str
    line_total: Decimal
    quantity: Decimal = Decimal("1")
    unit_price: Decimal | None = None


@dataclass
class ParsedReceipt:
    store_chain: str | None = None
    store_name: str | None = None
    purchase_date: datetime | None = None
    total: Decimal | None = None
    items: list[ParsedReceiptItem] = field(default_factory=list)

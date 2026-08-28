"""Decimal money helpers.

Splitting money is the one place a naive implementation loses cents: dividing
100.00 three ways gives 33.33 each, which sums to 99.99. Every function here
distributes the leftover minor units so the parts always add back up to the
whole.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

CURRENCY_SYMBOLS = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "AUD": "A$",
    "CAD": "C$",
    "SGD": "S$",
    "AED": "AED ",
}


def quantize(value: Decimal | int | float | str) -> Decimal:
    """Round ``value`` to two decimal places, half-up."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def to_decimal(value, default: Decimal | None = None) -> Decimal | None:
    """Parse user input into a Decimal, returning ``default`` when it is not a number."""
    if value is None or value == "":
        return default
    try:
        return quantize(Decimal(str(value).strip().replace(",", "")))
    except (InvalidOperation, ValueError, ArithmeticError):
        return default


def symbol_for(currency: str) -> str:
    return CURRENCY_SYMBOLS.get((currency or "INR").upper(), f"{currency} ")


def format_money(value, currency: str = "INR") -> str:
    """Render an amount with its currency symbol and thousands separators."""
    amount = quantize(value if value is not None else ZERO)
    sign = "-" if amount < 0 else ""
    return f"{sign}{symbol_for(currency)}{abs(amount):,.2f}"


def split_equal(total: Decimal, count: int) -> list[Decimal]:
    """Split ``total`` into ``count`` parts that sum exactly to ``total``.

    Leftover cents go to the earliest participants, one cent each, which is the
    conventional behaviour and keeps the result deterministic.
    """
    if count <= 0:
        return []
    total = quantize(total)
    base = (total / count).quantize(CENT, rounding="ROUND_DOWN")
    parts = [base] * count
    remainder = total - base * count
    cents = int((remainder / CENT).to_integral_value(rounding=ROUND_HALF_UP))
    step = CENT if cents >= 0 else -CENT
    for i in range(abs(cents)):
        parts[i % count] += step
    return parts


def split_by_weights(total: Decimal, weights: list[int]) -> list[Decimal]:
    """Split ``total`` proportionally to ``weights`` using the largest-remainder method."""
    if not weights:
        return []
    total_weight = sum(weights)
    if total_weight <= 0:
        return split_equal(total, len(weights))

    total = quantize(total)
    raw = [total * Decimal(w) / Decimal(total_weight) for w in weights]
    floors = [r.quantize(CENT, rounding="ROUND_DOWN") for r in raw]
    remainder = total - sum(floors)
    cents_left = int((remainder / CENT).to_integral_value(rounding=ROUND_HALF_UP))

    order = sorted(range(len(raw)), key=lambda i: (raw[i] - floors[i], weights[i]), reverse=True)
    for i in range(cents_left):
        floors[order[i % len(order)]] += CENT
    return floors

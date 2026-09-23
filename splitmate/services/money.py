"""Decimal money helpers.

Splitting money is the one place a naive implementation loses cents: dividing
100.00 three ways gives 33.33 each, which sums to 99.99. Every function here
distributes the leftover minor units so the parts always add back up to the
whole.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

#: Amounts are stored in ``Numeric(12, 2)``, so ten integer digits is the ceiling.
#: Anything beyond it cannot be persisted, and ``Decimal`` will happily carry a
#: value with a 999-digit exponent right up to the point where ``quantize``
#: raises. Screen it here instead.
MAX_AMOUNT = Decimal("9999999999.99")

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


def is_usable_amount(value) -> bool:
    """True when ``value`` is a number this application can actually store.

    ``Decimal`` accepts ``NaN`` and ``Infinity`` as ordinary values, and puts no
    ceiling on the exponent. None of the three survives contact with the rest of
    the app: ``quantize`` raises on an infinity or a huge exponent, and any
    ordering comparison against a ``NaN`` raises as well, so a form field
    carrying one turns into a 500 rather than a validation message.
    """
    if not isinstance(value, Decimal):
        return False
    return value.is_finite() and abs(value) <= MAX_AMOUNT


def quantize(value: Decimal | int | float | str) -> Decimal:
    """Round ``value`` to two decimal places, half-up.

    Raises :class:`decimal.InvalidOperation` on a non-finite or oversized value,
    which is why callers handling user input screen it with
    :func:`is_usable_amount` first.
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


#: A comma only means "thousands separator" in the positions a grouped number
#: puts it: three digits after each one. ``12,50`` is not that, it is somebody
#: writing twelve fifty the European way, and stripping the comma turns it into
#: 1250.00 without a word. Numbers shaped like that are rejected so the user
#: gets a validation message instead of a hundredfold charge.
_GROUPED = re.compile(r"^-?\d{1,3}(,\d{3})*(\.\d*)?$")


def to_decimal(value, default: Decimal | None = None) -> Decimal | None:
    """Parse user input into a Decimal, returning ``default`` when it is not a usable number."""
    if value is None or value == "":
        return default
    text = str(value).strip()
    if "," in text:
        if not _GROUPED.match(text):
            return default
        text = text.replace(",", "")
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError, ArithmeticError):
        return default
    if not is_usable_amount(parsed):
        return default
    return quantize(parsed)


def symbol_for(currency: str) -> str:
    """The symbol for a currency code, or the code itself when it is not one we know."""
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

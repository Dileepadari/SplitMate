"""Splitting money must never lose or invent a cent."""

from decimal import Decimal

import pytest

from splitmate.services.money import (
    format_money,
    quantize,
    split_by_weights,
    split_equal,
    to_decimal,
)


@pytest.mark.parametrize(
    "total,count",
    [("100.00", 3), ("0.01", 3), ("10.00", 7), ("1260.50", 4), ("999.99", 11), ("5.00", 1)],
)
def test_equal_split_sums_to_total(total, count):
    parts = split_equal(Decimal(total), count)
    assert len(parts) == count
    assert sum(parts) == Decimal(total)


def test_equal_split_spreads_leftover_cents_to_the_front():
    assert split_equal(Decimal("100.00"), 3) == [
        Decimal("33.34"),
        Decimal("33.33"),
        Decimal("33.33"),
    ]


def test_equal_split_of_zero_people_is_empty():
    assert split_equal(Decimal("10.00"), 0) == []


@pytest.mark.parametrize(
    "total,weights",
    [("100.00", [1, 2]), ("10.00", [1, 1, 1]), ("300.00", [2, 3, 5]), ("7.77", [1, 1, 1, 1])],
)
def test_weighted_split_sums_to_total(total, weights):
    parts = split_by_weights(Decimal(total), weights)
    assert sum(parts) == Decimal(total)


def test_weighted_split_is_proportional():
    assert split_by_weights(Decimal("300.00"), [1, 2]) == [Decimal("100.00"), Decimal("200.00")]


def test_zero_weights_fall_back_to_an_equal_split():
    assert split_by_weights(Decimal("9.00"), [0, 0, 0]) == [Decimal("3.00")] * 3


def test_to_decimal_handles_junk_and_separators():
    assert to_decimal("1,250.5") == Decimal("1250.50")
    assert to_decimal("not a number") is None
    assert to_decimal("", default=Decimal("0")) == Decimal("0")


def test_quantize_rounds_half_up():
    assert quantize("1.005") == Decimal("1.01")


def test_format_money_uses_the_currency_symbol():
    assert format_money(Decimal("1234.5"), "INR") == "₹1,234.50"
    assert format_money(Decimal("-20"), "USD") == "-$20.00"

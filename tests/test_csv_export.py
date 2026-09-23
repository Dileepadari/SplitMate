"""The CSV export must not hand a formula to whoever opens it.

Expense descriptions, settlement notes and usernames are written by group
members. Excel, LibreOffice and Sheets all evaluate a cell that begins ``=``,
``+``, ``-`` or ``@``, so before this guard one member could put
``=HYPERLINK("http://...", "click")`` in a description and attack every other
member who opened the export.
"""

from decimal import Decimal

import pytest

from splitmate.blueprints.groups import _csv_safe
from splitmate.extensions import db

from .factories import add_expense, make_group


@pytest.mark.parametrize(
    "dangerous",
    [
        "=1+1",
        '=HYPERLINK("http://evil.example","x")',
        '+HYPERLINK("http://evil.example","x")',
        "-2+3*cmd",
        "@SUM(A1:A9)",
        "\tcmd",
        "\rcmd",
    ],
)
def test_a_formula_is_neutralised(dangerous):
    assert _csv_safe(dangerous) == "'" + dangerous


@pytest.mark.parametrize("number", ["-50.00", "-0.01", "+1", "50.00", "0"])
def test_something_that_parses_as_a_number_is_left_alone(number):
    """Escaping every leading sign would turn every refund into text.

    The exemption is safe because a string ``Decimal`` accepts is only digits, a
    sign, a point and an exponent. There is no way to smuggle a call into one,
    and a cell holding ``+1`` evaluates to 1.
    """
    assert _csv_safe(number) == number
    assert Decimal(_csv_safe(number)) == Decimal(number)


def test_ordinary_text_is_untouched():
    assert _csv_safe("Airport cab") == "Airport cab"
    assert _csv_safe(None) == ""


def test_the_export_quotes_a_formula_a_member_typed(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    add_expense(group, users["alice"], "100.00", description="=1+1")
    login("alice")

    body = client.get(f"/groups/{group.id}/export.csv").get_data(as_text=True)

    assert "'=1+1" in body
    assert ",=1+1," not in body

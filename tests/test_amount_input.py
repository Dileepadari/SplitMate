"""Amount fields must reject what they cannot store, with a message not a 500.

Every string here reached an uncaught ``decimal.InvalidOperation`` before this
suite existed: ``Decimal`` accepts ``NaN`` and ``Infinity`` as ordinary values
and puts no ceiling on the exponent, so they passed ``NumberRange`` and then
blew up in ``quantize`` or in the first ordering comparison. All are reachable
by any signed-in group member typing into a normal form field.
"""

from decimal import Decimal

import pytest

from splitmate.extensions import db
from splitmate.models import Expense, SplitType
from splitmate.services.expenses import build_shares
from splitmate.services.money import MAX_AMOUNT, is_usable_amount, to_decimal

from .factories import make_group

#: Values a ``Decimal`` will construct but this application cannot use.
UNUSABLE = ["NaN", "nan", "-NaN", "Infinity", "-Infinity", "inf", "1e999", "1E+999"]


@pytest.mark.parametrize("raw", UNUSABLE)
def test_to_decimal_rejects_values_decimal_accepts_but_we_cannot_store(raw):
    assert to_decimal(raw) is None
    assert to_decimal(raw, default=Decimal("7.00")) == Decimal("7.00")


def test_to_decimal_rejects_amounts_past_the_column_ceiling():
    assert to_decimal(str(MAX_AMOUNT)) == MAX_AMOUNT
    assert to_decimal(str(MAX_AMOUNT + Decimal("0.01"))) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,500.00", Decimal("1500.00")),
        ("1,234,567.89", Decimal("1234567.89")),
        ("12,50", None),
        ("1,50", None),
        ("1,2345", None),
        ("12,345,67", None),
    ],
)
def test_a_comma_only_means_thousands_in_a_grouped_position(raw, expected):
    """``12,50`` is twelve fifty written the European way, not one thousand two hundred fifty.

    Stripping every comma turned it into 1250.00 silently, a hundredfold
    overcharge on a field the user believed they had filled in correctly. The
    main Amount field rejected the same text outright, so the two fields on one
    form disagreed about what it meant.
    """
    assert to_decimal(raw) == expected


def test_is_usable_amount_only_accepts_finite_decimals_in_range():
    assert is_usable_amount(Decimal("0.01"))
    assert is_usable_amount(MAX_AMOUNT)
    assert not is_usable_amount(Decimal("NaN"))
    assert not is_usable_amount(Decimal("Infinity"))
    assert not is_usable_amount(MAX_AMOUNT + Decimal("0.01"))
    assert not is_usable_amount("10.00")
    assert not is_usable_amount(None)


@pytest.mark.parametrize("raw", UNUSABLE)
def test_build_shares_rejects_an_unusable_amount_instead_of_raising(app, users, raw):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    ids = [m.user_id for m in group.members]

    result = build_shares(group, Decimal(raw), SplitType.EQUAL, ids)

    assert not result.ok
    assert "must be a number" in result.errors[0]


def _post(client, group, users, **overrides):
    data = {
        "description": "Dinner",
        "amount": "100.00",
        "payer_id": users["alice"].id,
        "category": "food",
        "spent_at": "2024-05-01",
        "split_type": "equal",
        "participant": [users["alice"].id, users["bob"].id],
        "notes": "",
    }
    data.update(overrides)
    return client.post(f"/groups/{group.id}/expenses/new", data=data)


@pytest.mark.parametrize("raw", UNUSABLE)
def test_the_amount_field_rejects_unusable_input_without_a_server_error(
    client, users, login, raw
):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")

    response = _post(client, group, users, amount=raw)

    assert response.status_code == 200, f"amount={raw!r} gave {response.status_code}"
    assert db.session.query(Expense).count() == 0


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "1e999"])
def test_an_exact_share_rejects_unusable_input_without_a_server_error(
    client, users, login, raw
):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")

    response = _post(
        client,
        group,
        users,
        split_type="exact",
        **{
            f"exact-{users['alice'].id}": raw,
            f"exact-{users['bob'].id}": "100.00",
        },
    )

    assert response.status_code == 200, f"exact share {raw!r} gave {response.status_code}"
    assert db.session.query(Expense).count() == 0

"""Net balances and the settle-up simplification."""

from decimal import Decimal

from splitmate.models import Settlement, SplitType
from splitmate.services.balances import group_balances, simplify, summaries_for, totals_for

from .factories import add_expense, make_group


def net_map(group):
    return {b.user.username: b.net for b in group_balances(group)}


def test_balances_sum_to_zero(app, db, users):
    group = make_group(users["alice"], users["bob"], users["carol"])
    add_expense(group, users["alice"], "90.00")
    add_expense(group, users["bob"], "30.00")
    assert sum(b.net for b in group_balances(group)) == Decimal("0.00")


def test_payer_is_credited_their_own_share_only_once(app, db, users):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "100.00")
    # Alice paid 100 and consumed 50, so the group owes her 50.
    assert net_map(group) == {"alice": Decimal("50.00"), "bob": Decimal("-50.00")}


def test_payer_excluded_from_the_split_is_owed_the_whole_amount(app, db, users):
    group = make_group(users["alice"], users["bob"], users["carol"])
    add_expense(group, users["alice"], "60.00", participants=[users["bob"], users["carol"]])
    assert net_map(group) == {
        "alice": Decimal("60.00"),
        "bob": Decimal("-30.00"),
        "carol": Decimal("-30.00"),
    }


def test_settlement_moves_the_balance(app, db, users):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "100.00")
    db.session.add(
        Settlement(
            group_id=group.id,
            from_user_id=users["bob"].id,
            to_user_id=users["alice"].id,
            amount=Decimal("50.00"),
        )
    )
    db.session.commit()
    assert net_map(group) == {"alice": Decimal("0.00"), "bob": Decimal("0.00")}


def test_exact_split_respects_the_given_amounts(app, db, users):
    group = make_group(users["alice"], users["bob"])
    add_expense(
        group,
        users["alice"],
        "100.00",
        split_type=SplitType.EXACT,
        exact_amounts={users["alice"].id: "70.00", users["bob"].id: "30.00"},
    )
    assert net_map(group) == {"alice": Decimal("30.00"), "bob": Decimal("-30.00")}


def test_share_split_weights_the_cost(app, db, users):
    group = make_group(users["alice"], users["bob"])
    add_expense(
        group,
        users["alice"],
        "300.00",
        split_type=SplitType.SHARES,
        weights={users["alice"].id: "1", users["bob"].id: "2"},
    )
    assert net_map(group) == {"alice": Decimal("200.00"), "bob": Decimal("-200.00")}


def test_simplify_needs_at_most_one_payment_per_person(app, db, users):
    group = make_group(users["alice"], users["bob"], users["carol"])
    add_expense(group, users["alice"], "90.00")
    add_expense(group, users["bob"], "30.00")
    transfers = simplify(group_balances(group))
    assert len(transfers) <= len(group.members) - 1


def test_simplify_clears_every_balance(app, db, users):
    group = make_group(users["alice"], users["bob"], users["carol"])
    add_expense(group, users["alice"], "120.00")
    add_expense(group, users["carol"], "45.00")

    remaining = {b.user.id: b.net for b in group_balances(group)}
    for transfer in simplify(group_balances(group)):
        remaining[transfer.debtor.id] += transfer.amount
        remaining[transfer.creditor.id] -= transfer.amount
    assert all(value == Decimal("0.00") for value in remaining.values())


def test_settled_group_needs_no_transfers(app, db, users):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "50.00")
    add_expense(group, users["bob"], "50.00")
    assert simplify(group_balances(group)) == []


def test_dashboard_totals_split_credit_and_debt(app, db, users):
    alice, bob, carol = users["alice"], users["bob"], users["carol"]
    owed = make_group(alice, bob, name="Owed")
    add_expense(owed, alice, "100.00")
    owing = make_group(carol, alice, name="Owing")
    add_expense(owing, carol, "80.00")

    db.session.commit()
    summaries = summaries_for(alice)
    totals = totals_for(summaries)
    assert totals.owed_to_you == Decimal("50.00")
    assert totals.you_owe == Decimal("40.00")
    assert totals.net == Decimal("10.00")


def test_archived_groups_stay_out_of_the_summary(app, db, users):
    group = make_group(users["alice"], users["bob"])
    group.archived = True
    db.session.commit()
    assert summaries_for(users["alice"]) == []
    assert len(summaries_for(users["alice"], include_archived=True)) == 1

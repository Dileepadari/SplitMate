"""Adding, editing and deleting expenses through the HTTP layer."""

from decimal import Decimal

from splitmate.extensions import db
from splitmate.models import Expense, SplitType
from splitmate.services.balances import group_balances

from .factories import add_expense, make_group


def post_expense(client, group, users, **overrides):
    data = {
        "description": "Airport cab",
        "amount": "300.00",
        "payer_id": users["alice"].id,
        "category": "transport",
        "spent_at": "2024-05-01",
        "split_type": "equal",
        "participant": [users["alice"].id, users["bob"].id, users["carol"].id],
        "notes": "",
    }
    data.update(overrides)
    return client.post(
        f"/groups/{group.id}/expenses/new", data=data, follow_redirects=True
    )


def test_adding_an_equal_expense_creates_matching_shares(client, users, login):
    group = make_group(users["alice"], users["bob"], users["carol"])
    db.session.commit()
    login("alice")
    response = post_expense(client, group, users)
    assert b"Added Airport cab" in response.data

    expense = db.session.query(Expense).one()
    assert expense.amount == Decimal("300.00")
    assert sum(s.amount for s in expense.shares) == Decimal("300.00")
    assert len(expense.shares) == 3


def test_leftover_cents_still_add_up(client, users, login):
    group = make_group(users["alice"], users["bob"], users["carol"])
    db.session.commit()
    login("alice")
    post_expense(client, group, users, amount="100.00")
    expense = db.session.query(Expense).one()
    assert sorted(s.amount for s in expense.shares) == [
        Decimal("33.33"),
        Decimal("33.33"),
        Decimal("33.34"),
    ]


def test_a_participant_can_be_left_out(client, users, login):
    group = make_group(users["alice"], users["bob"], users["carol"])
    db.session.commit()
    login("alice")
    post_expense(client, group, users, participant=[users["bob"].id, users["carol"].id])
    expense = db.session.query(Expense).one()
    assert {s.user_id for s in expense.shares} == {users["bob"].id, users["carol"].id}
    nets = {b.user.username: b.net for b in group_balances(group)}
    assert nets["alice"] == Decimal("300.00")


def test_exact_amounts_must_add_up_to_the_total(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")
    response = client.post(
        f"/groups/{group.id}/expenses/new",
        data={
            "description": "Dinner",
            "amount": "100.00",
            "payer_id": users["alice"].id,
            "category": "food",
            "spent_at": "2024-05-01",
            "split_type": "exact",
            "participant": [users["alice"].id, users["bob"].id],
            f"exact-{users['alice'].id}": "40.00",
            f"exact-{users['bob'].id}": "40.00",
        },
        follow_redirects=True,
    )
    assert b"add up to 80.00" in response.data
    assert db.session.query(Expense).count() == 0


def test_exact_amounts_that_do_add_up_are_accepted(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")
    client.post(
        f"/groups/{group.id}/expenses/new",
        data={
            "description": "Dinner",
            "amount": "100.00",
            "payer_id": users["alice"].id,
            "category": "food",
            "spent_at": "2024-05-01",
            "split_type": "exact",
            "participant": [users["alice"].id, users["bob"].id],
            f"exact-{users['alice'].id}": "70.00",
            f"exact-{users['bob'].id}": "30.00",
        },
        follow_redirects=True,
    )
    expense = db.session.query(Expense).one()
    assert expense.split_type == SplitType.EXACT
    assert expense.share_for(users["bob"].id) == Decimal("30.00")


def test_shares_weight_the_split(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")
    client.post(
        f"/groups/{group.id}/expenses/new",
        data={
            "description": "Hotel",
            "amount": "300.00",
            "payer_id": users["alice"].id,
            "category": "travel",
            "spent_at": "2024-05-01",
            "split_type": "shares",
            "participant": [users["alice"].id, users["bob"].id],
            f"weight-{users['alice'].id}": "1",
            f"weight-{users['bob'].id}": "2",
        },
        follow_redirects=True,
    )
    expense = db.session.query(Expense).one()
    assert expense.share_for(users["bob"].id) == Decimal("200.00")


def test_an_expense_needs_at_least_one_participant(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")
    response = post_expense(client, group, users, participant=[])
    assert b"Pick at least one person" in response.data


def test_a_non_member_cannot_be_added_to_a_split(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")
    response = post_expense(
        client, group, users, participant=[users["alice"].id, users["carol"].id]
    )
    assert b"not a member of this group" in response.data


def test_a_future_date_is_rejected(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")
    response = post_expense(client, group, users, spent_at="2099-01-01",
                            participant=[users["alice"].id, users["bob"].id])
    assert b"cannot be in the future" in response.data


def test_a_zero_amount_is_rejected(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")
    response = post_expense(client, group, users, amount="0",
                            participant=[users["alice"].id, users["bob"].id])
    assert b"must be positive" in response.data


def test_editing_an_expense_replaces_its_shares(client, users, login):
    group = make_group(users["alice"], users["bob"], users["carol"])
    expense = add_expense(group, users["alice"], "300.00")
    login("alice")
    client.post(
        f"/groups/{group.id}/expenses/{expense.id}/edit",
        data={
            "description": "Cab and tolls",
            "amount": "400.00",
            "payer_id": users["bob"].id,
            "category": "transport",
            "spent_at": "2024-05-02",
            "split_type": "equal",
            "participant": [users["alice"].id, users["bob"].id],
        },
        follow_redirects=True,
    )
    db.session.refresh(expense)
    assert expense.description == "Cab and tolls"
    assert expense.payer_id == users["bob"].id
    assert len(expense.shares) == 2
    assert sum(s.amount for s in expense.shares) == Decimal("400.00")


def test_the_payer_can_delete_their_expense(client, users, login):
    group = make_group(users["alice"], users["bob"])
    expense = add_expense(group, users["alice"], "50.00")
    login("alice")
    client.post(f"/groups/{group.id}/expenses/{expense.id}/delete", follow_redirects=True)
    assert db.session.query(Expense).count() == 0


def test_someone_else_cannot_delete_your_expense(client, users, login):
    group = make_group(users["alice"], users["bob"], users["carol"])
    expense = add_expense(group, users["alice"], "50.00")
    login("carol")
    assert client.post(f"/groups/{group.id}/expenses/{expense.id}/delete").status_code == 403


def test_a_group_owner_can_delete_anyones_expense(client, users, login):
    group = make_group(users["alice"], users["bob"])
    expense = add_expense(group, users["bob"], "50.00")
    login("alice")
    client.post(f"/groups/{group.id}/expenses/{expense.id}/delete", follow_redirects=True)
    assert db.session.query(Expense).count() == 0


def test_an_expense_from_another_group_is_not_reachable(client, users, login):
    mine = make_group(users["alice"], name="Mine")
    theirs = make_group(users["bob"], name="Theirs")
    expense = add_expense(theirs, users["bob"], "10.00")
    login("alice")
    assert client.get(f"/groups/{mine.id}/expenses/{expense.id}").status_code == 404


def test_the_expense_detail_page_renders(client, users, login):
    group = make_group(users["alice"], users["bob"])
    expense = add_expense(group, users["alice"], "100.00", description="Groceries")
    login("alice")
    response = client.get(f"/groups/{group.id}/expenses/{expense.id}")
    assert response.status_code == 200
    assert b"Groceries" in response.data
    assert b"Split breakdown" in response.data

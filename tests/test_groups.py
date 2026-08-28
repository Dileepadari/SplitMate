"""Group lifecycle: creation, membership, permissions, settling and export."""

from decimal import Decimal

from splitmate.extensions import db
from splitmate.models import Group, MemberRole, Settlement
from splitmate.services.balances import group_balances

from .factories import add_expense, make_group


def test_creating_a_group_makes_you_its_owner(client, users, login):
    login("alice")
    response = client.post(
        "/groups/new",
        data={"name": "Goa trip", "description": "Four days", "currency": "INR"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    group = db.session.query(Group).filter_by(name="Goa trip").one()
    assert group.is_owner(users["alice"].id)
    assert len(group.members) == 1


def test_a_non_member_cannot_see_the_group(client, users, login):
    group = make_group(users["bob"])
    db.session.commit()
    login("alice")
    assert client.get(f"/groups/{group.id}").status_code == 404


def test_adding_a_member_by_username(client, users, login):
    group = make_group(users["alice"])
    db.session.commit()
    login("alice")
    response = client.post(
        f"/groups/{group.id}/members", data={"identifier": "bob"}, follow_redirects=True
    )
    assert b"Added Bob Test" in response.data
    assert group.has_member(users["bob"].id)


def test_adding_a_member_by_email(client, users, login):
    group = make_group(users["alice"])
    db.session.commit()
    login("alice")
    client.post(
        f"/groups/{group.id}/members",
        data={"identifier": "bob@example.com"},
        follow_redirects=True,
    )
    assert group.has_member(users["bob"].id)


def test_adding_an_unknown_person_is_rejected(client, users, login):
    group = make_group(users["alice"])
    db.session.commit()
    login("alice")
    response = client.post(
        f"/groups/{group.id}/members", data={"identifier": "ghost"}, follow_redirects=True
    )
    assert b"No SplitMate account matches" in response.data


def test_adding_the_same_person_twice_is_rejected(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")
    response = client.post(
        f"/groups/{group.id}/members", data={"identifier": "bob"}, follow_redirects=True
    )
    assert b"already in this group" in response.data


def test_only_an_owner_may_edit_the_group(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("bob")
    assert client.get(f"/groups/{group.id}/edit").status_code == 403


def test_a_member_with_a_balance_cannot_be_removed(client, users, login):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "100.00")
    login("alice")
    response = client.post(
        f"/groups/{group.id}/members/{users['bob'].id}/remove", follow_redirects=True
    )
    assert b"Settle their balance" in response.data
    assert group.has_member(users["bob"].id)


def test_a_settled_member_can_be_removed(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")
    client.post(f"/groups/{group.id}/members/{users['bob'].id}/remove", follow_redirects=True)
    assert not group.has_member(users["bob"].id)


def test_leaving_requires_a_zero_balance(client, users, login):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "40.00")
    login("bob")
    response = client.post(f"/groups/{group.id}/leave", follow_redirects=True)
    assert b"Settle their balance" in response.data
    assert group.has_member(users["bob"].id)


def test_the_last_member_is_told_to_delete_instead(client, users, login):
    group = make_group(users["alice"])
    db.session.commit()
    login("alice")
    response = client.post(f"/groups/{group.id}/leave", follow_redirects=True)
    assert b"Delete the group instead" in response.data


def test_promoting_and_demoting_an_owner(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")
    client.post(f"/groups/{group.id}/members/{users['bob'].id}/promote", follow_redirects=True)
    assert group.membership_for(users["bob"].id).role == MemberRole.OWNER
    client.post(f"/groups/{group.id}/members/{users['bob'].id}/promote", follow_redirects=True)
    assert group.membership_for(users["bob"].id).role == MemberRole.MEMBER


def test_archiving_hides_the_group_from_the_dashboard(client, users, login):
    group = make_group(users["alice"])
    db.session.commit()
    login("alice")
    client.post(f"/groups/{group.id}/archive", follow_redirects=True)
    assert group.archived is True
    assert b"Archived" in client.get("/dashboard").data


def test_deleting_a_group_removes_its_expenses(client, users, login):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "20.00")
    group_id = group.id
    login("alice")
    client.post(f"/groups/{group_id}/delete", follow_redirects=True)
    assert db.session.get(Group, group_id) is None


def test_a_plain_member_cannot_delete_the_group(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("bob")
    assert client.post(f"/groups/{group.id}/delete").status_code == 403


def test_recording_a_settlement_clears_the_balance(client, users, login):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "100.00")
    login("bob")
    client.post(
        f"/groups/{group.id}/settle",
        data={
            "from_user_id": users["bob"].id,
            "to_user_id": users["alice"].id,
            "amount": "50.00",
            "settled_at": "2024-01-01",
            "note": "UPI",
        },
        follow_redirects=True,
    )
    assert all(b.net == Decimal("0.00") for b in group_balances(group))


def test_a_settlement_cannot_pay_yourself(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")
    response = client.post(
        f"/groups/{group.id}/settle",
        data={
            "from_user_id": users["alice"].id,
            "to_user_id": users["alice"].id,
            "amount": "10.00",
            "settled_at": "2024-01-01",
        },
    )
    assert b"Pick two different people" in response.data


def test_undoing_a_settlement_restores_the_balance(client, users, login):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "100.00")
    settlement = Settlement(
        group_id=group.id,
        from_user_id=users["bob"].id,
        to_user_id=users["alice"].id,
        amount=Decimal("50.00"),
    )
    db.session.add(settlement)
    db.session.commit()
    login("alice")
    client.post(
        f"/groups/{group.id}/settlements/{settlement.id}/delete", follow_redirects=True
    )
    assert {b.user.username: b.net for b in group_balances(group)}["bob"] == Decimal("-50.00")


def test_csv_export_lists_expenses_and_settlements(client, users, login):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "100.00", description="Cab")
    db.session.add(
        Settlement(
            group_id=group.id,
            from_user_id=users["bob"].id,
            to_user_id=users["alice"].id,
            amount=Decimal("50.00"),
            note="UPI",
        )
    )
    db.session.commit()
    login("alice")
    response = client.get(f"/groups/{group.id}/export.csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    body = response.get_data(as_text=True)
    assert "Cab" in body and "UPI" in body
    assert "alice=50.00" in body


def test_expenses_can_be_searched_and_filtered(client, users, login):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "10.00", description="Museum tickets")
    add_expense(group, users["alice"], "20.00", description="Airport cab")
    login("alice")
    hits = client.get(f"/groups/{group.id}?q=museum").data
    assert b"Museum tickets" in hits and b"Airport cab" not in hits

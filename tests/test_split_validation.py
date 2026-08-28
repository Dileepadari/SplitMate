"""Rejection paths in the split builder, and the pages that render it."""

from decimal import Decimal

from splitmate.extensions import db
from splitmate.models import SplitType
from splitmate.services.expenses import build_shares, read_split_input

from .factories import make_group


def ids(users, *names):
    return [users[name].id for name in names]


def test_a_negative_exact_amount_is_rejected(app, users):
    group = make_group(users["alice"], users["bob"])
    result = build_shares(
        group,
        Decimal("100.00"),
        SplitType.EXACT,
        ids(users, "alice", "bob"),
        exact_amounts={users["alice"].id: "-10", users["bob"].id: "110"},
    )
    assert not result.ok
    assert "negative" in result.errors[0]


def test_a_missing_exact_amount_is_rejected(app, users):
    group = make_group(users["alice"], users["bob"])
    result = build_shares(
        group,
        Decimal("100.00"),
        SplitType.EXACT,
        ids(users, "alice", "bob"),
        exact_amounts={users["alice"].id: "100"},
    )
    assert not result.ok
    assert "exact amount" in result.errors[0]


def test_non_numeric_shares_are_rejected(app, users):
    group = make_group(users["alice"], users["bob"])
    result = build_shares(
        group,
        Decimal("100.00"),
        SplitType.SHARES,
        ids(users, "alice", "bob"),
        weights={users["alice"].id: "two", users["bob"].id: "1"},
    )
    assert not result.ok
    assert "whole numbers" in result.errors[0]


def test_negative_shares_are_rejected(app, users):
    group = make_group(users["alice"], users["bob"])
    result = build_shares(
        group,
        Decimal("100.00"),
        SplitType.SHARES,
        ids(users, "alice", "bob"),
        weights={users["alice"].id: "-1", users["bob"].id: "1"},
    )
    assert not result.ok
    assert "negative" in result.errors[0]


def test_all_zero_shares_are_rejected(app, users):
    group = make_group(users["alice"], users["bob"])
    result = build_shares(
        group,
        Decimal("100.00"),
        SplitType.SHARES,
        ids(users, "alice", "bob"),
        weights={users["alice"].id: "0", users["bob"].id: "0"},
    )
    assert not result.ok
    assert "above zero" in result.errors[0]


def test_a_zero_amount_is_rejected(app, users):
    group = make_group(users["alice"], users["bob"])
    result = build_shares(group, Decimal("0"), SplitType.EQUAL, ids(users, "alice"))
    assert not result.ok


def test_duplicate_participants_are_collapsed(app, users):
    group = make_group(users["alice"], users["bob"])
    alice = users["alice"].id
    result = build_shares(group, Decimal("100.00"), SplitType.EQUAL, [alice, alice])
    assert result.ok
    assert result.shares == {alice: (Decimal("100.00"), 1)}


def test_read_split_input_ignores_malformed_keys(app):
    from werkzeug.datastructures import MultiDict

    data = MultiDict(
        [
            ("participant", "1"),
            ("participant", "not-a-number"),
            ("exact-1", "10.00"),
            ("exact-x", "junk"),
            ("weight-1", "2"),
            ("weight-y", "junk"),
        ]
    )
    participants, exact, weights = read_split_input(data)
    assert participants == [1]
    assert exact == {1: "10.00"}
    assert weights == {1: "2"}


def test_every_authenticated_page_renders(client, users, login):
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")

    for path in (
        "/",
        "/dashboard",
        "/about",
        "/account/",
        "/groups/new",
        f"/groups/{group.id}",
        f"/groups/{group.id}/edit",
        f"/groups/{group.id}/members",
        f"/groups/{group.id}/settle",
        f"/groups/{group.id}/expenses/new",
    ):
        response = client.get(path, follow_redirects=True)
        assert response.status_code == 200, path


def test_public_pages_render_signed_out(client):
    for path in ("/", "/about", "/login", "/register"):
        assert client.get(path).status_code == 200, path

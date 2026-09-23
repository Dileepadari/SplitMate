"""Profile, password, theme and account deletion."""


from splitmate.extensions import db
from splitmate.models import Group, MemberRole, User

from .factories import add_expense, make_group


def test_settings_page_renders(client, users, login):
    login("alice")
    response = client.get("/account/")
    assert response.status_code == 200
    assert b"alice@example.com" in response.data


def test_updating_the_profile(client, users, login):
    login("alice")
    response = client.post(
        "/account/",
        data={
            "profile-first_name": "Alicia",
            "profile-last_name": "Keys",
            "profile-email": "alicia@example.com",
            "profile-avatar_url": "",
            "profile-currency": "USD",
            "profile-submit": "Save changes",
        },
        follow_redirects=True,
    )
    assert b"Profile updated" in response.data
    user = db.session.query(User).filter_by(username="alice").one()
    assert user.first_name == "Alicia"
    assert user.currency == "USD"


def test_an_email_already_in_use_is_rejected(client, users, login):
    login("alice")
    response = client.post(
        "/account/",
        data={
            "profile-first_name": "Alice",
            "profile-last_name": "Test",
            "profile-email": "bob@example.com",
            "profile-currency": "INR",
            "profile-submit": "Save changes",
        },
    )
    assert b"Another account already uses that email" in response.data


def test_changing_the_password(client, users, login):
    login("alice")
    response = client.post(
        "/account/",
        data={
            "password-current_password": "password123",
            "password-new_password": "brand-new-secret",
            "password-confirm": "brand-new-secret",
            "password-submit": "Update password",
        },
        follow_redirects=True,
    )
    assert b"Password updated" in response.data
    assert db.session.query(User).filter_by(username="alice").one().check_password(
        "brand-new-secret"
    )


def test_the_wrong_current_password_is_rejected(client, users, login):
    login("alice")
    response = client.post(
        "/account/",
        data={
            "password-current_password": "wrong",
            "password-new_password": "brand-new-secret",
            "password-confirm": "brand-new-secret",
            "password-submit": "Update password",
        },
    )
    assert b"not your current password" in response.data


def test_the_theme_preference_is_stored(client, users, login):
    login("alice")
    response = client.post("/account/theme", json={"theme": "dark"})
    assert response.get_json() == {"theme": "dark"}
    assert db.session.query(User).filter_by(username="alice").one().theme == "dark"


def test_an_unknown_theme_is_refused(client, users, login):
    login("alice")
    assert client.post("/account/theme", json={"theme": "neon"}).status_code == 400


def test_deleting_an_account_with_a_balance_is_blocked(client, users, login):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "100.00")
    login("alice")
    response = client.post("/account/delete", follow_redirects=True)
    assert b"Settle every balance" in response.data
    assert db.session.query(User).filter_by(username="alice").count() == 1


def test_deleting_an_account_with_shared_history_is_blocked(client, users, login):
    group = make_group(users["alice"], users["bob"])
    add_expense(group, users["alice"], "100.00", participants=[users["alice"]])
    login("alice")
    response = client.post("/account/delete", follow_redirects=True)
    assert b"expense history" in response.data
    assert db.session.query(User).filter_by(username="alice").count() == 1


def test_a_clean_account_is_deleted_and_solo_groups_go_with_it(client, users, login):
    solo = make_group(users["alice"], name="Solo")
    shared = make_group(users["alice"], users["bob"], name="Shared")
    solo_id, shared_id = solo.id, shared.id
    db.session.commit()

    login("alice")
    response = client.post("/account/delete", follow_redirects=True)
    assert b"deleted" in response.data
    assert db.session.query(User).filter_by(username="alice").count() == 0
    assert db.session.get(Group, solo_id) is None

    remaining = db.session.get(Group, shared_id)
    assert [m.user.username for m in remaining.members] == ["bob"]
    assert remaining.members[0].role == MemberRole.OWNER

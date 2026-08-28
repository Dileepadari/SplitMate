"""Registration, sign in, sign out and route protection."""

from splitmate.extensions import db
from splitmate.models import User


def test_landing_page_is_public(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Stop doing the maths" in response.data


def test_dashboard_requires_a_session(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_register_creates_a_user_and_signs_them_in(client, app):
    response = client.post(
        "/register",
        data={
            "username": "newbie",
            "email": "newbie@example.com",
            "first_name": "New",
            "last_name": "Bie",
            "password": "supersecret",
            "confirm": "supersecret",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Welcome to SplitMate" in response.data
    user = db.session.query(User).filter_by(username="newbie").one()
    assert user.password_hash != "supersecret"
    assert user.check_password("supersecret")


def test_register_rejects_a_duplicate_username(client, users):
    response = client.post(
        "/register",
        data={
            "username": "alice",
            "email": "other@example.com",
            "first_name": "A",
            "password": "supersecret",
            "confirm": "supersecret",
        },
    )
    assert b"already registered" in response.data


def test_register_rejects_mismatched_passwords(client):
    response = client.post(
        "/register",
        data={
            "username": "mismatch",
            "email": "m@example.com",
            "first_name": "M",
            "password": "supersecret",
            "confirm": "different1",
        },
    )
    assert b"Passwords do not match" in response.data


def test_login_accepts_username_or_email(client, users, login):
    assert b"Signed in as alice" in login("alice").data
    client.post("/logout")
    assert b"Signed in as alice" in login("alice@example.com").data


def test_login_rejects_a_bad_password(client, users):
    response = client.post(
        "/login", data={"identifier": "alice", "password": "wrong"}, follow_redirects=True
    )
    assert b"did not match an account" in response.data


def test_logout_ends_the_session(client, users, login):
    login("alice")
    client.post("/logout", follow_redirects=True)
    assert client.get("/dashboard").status_code == 302


def test_login_only_follows_a_local_next_url(client, users):
    response = client.post(
        "/login?next=https://evil.example.com",
        data={"identifier": "alice", "password": "password123"},
    )
    assert response.headers["Location"] == "/dashboard"


def test_health_check_is_public(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}


def test_unknown_page_renders_the_error_template(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert b"Nothing here" in response.data

"""Shared fixtures. Every test runs against an in-memory SQLite database."""

from __future__ import annotations

import pytest

from splitmate import create_app
from splitmate.extensions import db as _db

from .factories import make_user


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def users(app):
    """Three signed-up people, all with the password ``password123``."""
    people = {name: make_user(name) for name in ("alice", "bob", "carol")}
    _db.session.commit()
    return people


@pytest.fixture()
def login(client):
    def _login(username: str, password: str = "password123"):
        return client.post(
            "/login",
            data={"identifier": username, "password": password},
            follow_redirects=True,
        )

    return _login

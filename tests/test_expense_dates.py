"""The date on an expense or a payment is judged against UTC, not the server's clock.

Every datetime column stores UTC, but the "cannot be in the future" validators
compared against ``date.today()``, which is whatever the machine running the app
thinks. For a user east of the server that rejects their own today for several
hours a day.
"""

from datetime import timedelta

from splitmate.extensions import db
from splitmate.forms import latest_allowed_date
from splitmate.models import Expense, utcnow

from .factories import make_group


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


def test_a_user_ahead_of_the_server_can_still_date_an_expense_today(client, users, login):
    """A date one day ahead of UTC is accepted, because for some user it is today.

    Datetime columns store UTC, but the validator compared against the server's
    local ``date.today()``. A user in UTC+5:30 filing an expense at 2am was told
    their own today was in the future.
    """
    group = make_group(users["alice"], users["bob"])
    db.session.commit()
    login("alice")

    tomorrow_in_utc = utcnow().date() + timedelta(days=1)
    assert latest_allowed_date() == tomorrow_in_utc

    response = _post(client, group, users, spent_at=tomorrow_in_utc.isoformat())
    assert response.status_code in (200, 302)
    assert db.session.query(Expense).count() == 1

    too_far = (utcnow().date() + timedelta(days=2)).isoformat()
    response = _post(client, group, users, spent_at=too_far)
    assert response.status_code == 200
    assert db.session.query(Expense).count() == 1

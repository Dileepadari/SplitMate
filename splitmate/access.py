"""Access checks shared by the group and expense blueprints."""

from __future__ import annotations

from flask import abort
from flask_login import current_user

from .extensions import db
from .models import Expense, Group


def get_group_or_404(group_id: int) -> Group:
    """Fetch a group the signed-in user belongs to, or abort.

    A non-member gets a 404 rather than a 403 so the app does not confirm that
    a group id exists to someone who has no business knowing.
    """
    group = db.session.get(Group, group_id)
    if group is None or not group.has_member(current_user.id):
        abort(404)
    return group


def require_owner(group: Group) -> None:
    if not group.is_owner(current_user.id):
        abort(403)


def get_expense_or_404(group: Group, expense_id: int) -> Expense:
    expense = db.session.get(Expense, expense_id)
    if expense is None or expense.group_id != group.id:
        abort(404)
    return expense

"""A single reverse-chronological feed mixing expenses and settlements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..models import Expense, Group, Settlement, User


@dataclass(frozen=True)
class ActivityItem:
    kind: str  # "expense" or "settlement"
    when: date
    group: Group
    title: str
    amount: Decimal
    actor: User
    obj: Expense | Settlement

    @property
    def is_expense(self) -> bool:
        return self.kind == "expense"


def _from_expense(expense: Expense) -> ActivityItem:
    return ActivityItem(
        kind="expense",
        when=expense.spent_at,
        group=expense.group,
        title=expense.description,
        amount=expense.amount,
        actor=expense.payer,
        obj=expense,
    )


def _from_settlement(settlement: Settlement) -> ActivityItem:
    return ActivityItem(
        kind="settlement",
        when=settlement.settled_at,
        group=settlement.group,
        title=f"{settlement.from_user.display_name} paid {settlement.to_user.display_name}",
        amount=settlement.amount,
        actor=settlement.from_user,
        obj=settlement,
    )


def group_activity(group: Group, limit: int | None = None) -> list[ActivityItem]:
    items = [_from_expense(e) for e in group.expenses]
    items += [_from_settlement(s) for s in group.settlements]
    items.sort(key=lambda i: (i.when, i.obj.created_at), reverse=True)
    return items[:limit] if limit else items


def user_activity(user: User, limit: int = 15) -> list[ActivityItem]:
    """Recent activity across every group the user is still a member of."""
    items: list[ActivityItem] = []
    for membership in user.memberships:
        items.extend(group_activity(membership.group))
    items.sort(key=lambda i: (i.when, i.obj.created_at), reverse=True)
    return items[:limit]

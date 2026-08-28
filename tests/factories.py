"""Object factories used by the tests."""

from __future__ import annotations

from decimal import Decimal

from splitmate.extensions import db
from splitmate.models import Expense, Group, GroupMember, MemberRole, SplitType, User
from splitmate.services.expenses import apply_shares, build_shares


def make_user(username: str, password: str = "password123", **kwargs) -> User:
    user = User(
        username=username,
        email=kwargs.pop("email", f"{username}@example.com"),
        first_name=kwargs.pop("first_name", username.capitalize()),
        last_name=kwargs.pop("last_name", "Test"),
        **kwargs,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user


def make_group(owner: User, *members: User, name: str = "Trip", currency: str = "INR") -> Group:
    group = Group(name=name, currency=currency, created_by_id=owner.id)
    group.members.append(GroupMember(user_id=owner.id, role=MemberRole.OWNER))
    for member in members:
        group.members.append(GroupMember(user_id=member.id, role=MemberRole.MEMBER))
    db.session.add(group)
    db.session.flush()
    return group


def add_expense(
    group: Group,
    payer: User,
    amount: str,
    participants=None,
    split_type: SplitType = SplitType.EQUAL,
    description: str = "Dinner",
    **split_kwargs,
) -> Expense:
    """Create a committed expense, asserting the split is valid."""
    ids = [u.id for u in (participants if participants is not None else group.member_users)]
    result = build_shares(group, Decimal(amount), split_type, ids, **split_kwargs)
    assert result.ok, result.errors
    expense = Expense(
        group_id=group.id,
        payer_id=payer.id,
        description=description,
        amount=Decimal(amount),
        split_type=split_type,
    )
    apply_shares(expense, result.shares)
    db.session.add(expense)
    db.session.commit()
    return expense

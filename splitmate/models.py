"""SQLAlchemy models.

Money is stored as ``Numeric(12, 2)`` and handled as :class:`decimal.Decimal`
everywhere. Nothing in this app should ever put a float on a money column.
"""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

ZERO = Decimal("0.00")


def utcnow() -> datetime:
    """Timezone-aware UTC now. All datetime columns store UTC."""
    return datetime.now(UTC)


class SplitType(enum.StrEnum):
    """How an expense amount is divided among its participants."""

    EQUAL = "equal"
    EXACT = "exact"
    SHARES = "shares"


class MemberRole(enum.StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    theme: Mapped[str] = mapped_column(String(10), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list[GroupMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    expenses_paid: Mapped[list[Expense]] = relationship(
        back_populates="payer", foreign_keys="Expense.payer_id"
    )

    # -- password ---------------------------------------------------------
    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)

    # -- display ----------------------------------------------------------
    @property
    def full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.username

    @property
    def display_name(self) -> str:
        return self.first_name or self.username

    @property
    def initials(self) -> str:
        parts = [p for p in (self.first_name, self.last_name) if p]
        if parts:
            return "".join(p[0] for p in parts[:2]).upper()
        return self.username[:2].upper()

    @property
    def groups(self) -> list[Group]:
        return [m.group for m in self.memberships if not m.group.archived]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.username}>"


class Group(db.Model):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Historical metadata only: who is in charge is the OWNER role on
    # GroupMember. Nulled rather than blocking when the creator deletes their
    # account and the group lives on without them.
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    members: Mapped[list[GroupMember]] = relationship(
        back_populates="group", cascade="all, delete-orphan", order_by="GroupMember.joined_at"
    )
    expenses: Mapped[list[Expense]] = relationship(
        back_populates="group", cascade="all, delete-orphan", order_by="Expense.spent_at.desc()"
    )
    settlements: Mapped[list[Settlement]] = relationship(
        back_populates="group", cascade="all, delete-orphan", order_by="Settlement.settled_at.desc()"
    )

    @property
    def member_users(self) -> list[User]:
        return [m.user for m in self.members]

    def membership_for(self, user_id: int) -> GroupMember | None:
        return next((m for m in self.members if m.user_id == user_id), None)

    def has_member(self, user_id: int) -> bool:
        return self.membership_for(user_id) is not None

    def is_owner(self, user_id: int) -> bool:
        member = self.membership_for(user_id)
        return member is not None and member.role == MemberRole.OWNER

    @property
    def total_spend(self) -> Decimal:
        return sum((e.amount for e in self.expenses), ZERO)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Group {self.name!r}>"


class GroupMember(db.Model):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, native_enum=False, length=10), default=MemberRole.MEMBER, nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    group: Mapped[Group] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Expense(db.Model):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expense_amount_positive"),
        Index("ix_expense_group_date", "group_id", "spent_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    payer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    description: Mapped[str] = mapped_column(String(140), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="general")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    split_type: Mapped[SplitType] = mapped_column(
        Enum(SplitType, native_enum=False, length=10), default=SplitType.EQUAL, nullable=False
    )
    spent_at: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    group: Mapped[Group] = relationship(back_populates="expenses")
    payer: Mapped[User] = relationship(back_populates="expenses_paid", foreign_keys=[payer_id])
    shares: Mapped[list[ExpenseShare]] = relationship(
        back_populates="expense", cascade="all, delete-orphan"
    )

    def share_for(self, user_id: int) -> Decimal:
        return next((s.amount for s in self.shares if s.user_id == user_id), ZERO)

    @property
    def participants(self) -> list[User]:
        return [s.user for s in self.shares]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Expense {self.description!r} {self.amount}>"


class ExpenseShare(db.Model):
    """One participant's slice of an expense. Shares always sum to the expense amount."""

    __tablename__ = "expense_shares"
    __table_args__ = (UniqueConstraint("expense_id", "user_id", name="uq_expense_share"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    expense: Mapped[Expense] = relationship(back_populates="shares")
    user: Mapped[User] = relationship()


class Settlement(db.Model):
    """A real payment from one member to another, recorded to clear a debt."""

    __tablename__ = "settlements"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_settlement_amount_positive"),
        CheckConstraint("from_user_id != to_user_id", name="ck_settlement_distinct_parties"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    note: Mapped[str] = mapped_column(String(140), nullable=False, default="")
    settled_at: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    group: Mapped[Group] = relationship(back_populates="settlements")
    from_user: Mapped[User] = relationship(foreign_keys=[from_user_id])
    to_user: Mapped[User] = relationship(foreign_keys=[to_user_id])

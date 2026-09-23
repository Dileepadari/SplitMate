"""Custom ``flask`` CLI commands."""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

import click
from flask import Flask
from sqlalchemy import select

from .extensions import db
from .models import (
    Expense,
    Group,
    GroupMember,
    MemberRole,
    Settlement,
    SplitType,
    User,
    utcnow,
)
from .services.expenses import apply_shares, build_shares

DEMO_USERS = [
    ("dileep", "dileepkumar.adari@students.iiit.ac.in", "Dileep", "Adari"),
    ("aadi", "aadi.prasad@example.com", "Aadi", "Prasad"),
    ("chanukya", "satuluri.charyulu@students.iiit.ac.in", "Chanukya", "Charyulu"),
    ("riya", "riya@example.com", "Riya", "Menon"),
]

DEMO_EXPENSES = [
    ("Airport cab", "transport", "1840.00", SplitType.EQUAL),
    ("Hostel dinner", "food", "1260.50", SplitType.EQUAL),
    ("Weekend groceries", "groceries", "2310.00", SplitType.SHARES),
    ("Museum tickets", "entertainment", "900.00", SplitType.EQUAL),
    ("Internet bill", "rent", "1499.00", SplitType.EXACT),
]


def register_cli(app: Flask) -> None:
    """Attach ``init-db``, ``reset-db`` and ``seed-demo`` to the ``flask`` command."""
    @app.cli.command("init-db")
    def init_db() -> None:
        """Create every table. Safe to run repeatedly."""
        db.create_all()
        click.echo("Tables created.")

    @app.cli.command("reset-db")
    @click.confirmation_option(prompt="This drops every table. Continue?")
    def reset_db() -> None:
        """Drop and recreate the schema."""
        db.drop_all()
        db.create_all()
        click.echo("Database reset.")

    @app.cli.command("seed-demo")
    @click.option("--password", default="splitmate123", show_default=True)
    def seed_demo(password: str) -> None:
        """Load a small demo dataset: four users, two groups, expenses and a payment."""
        db.create_all()

        users = []
        for username, email, first, last in DEMO_USERS:
            user = db.session.scalar(select(User).where(User.username == username))
            if user is None:
                user = User(username=username, email=email, first_name=first, last_name=last)
                user.set_password(password)
                db.session.add(user)
            users.append(user)
        db.session.flush()

        if db.session.scalar(select(Group).where(Group.name == "Goa trip")) is not None:
            click.echo("Demo data already present.")
            return

        trip = Group(
            name="Goa trip",
            description="Four days, one shared wallet.",
            currency="INR",
            created_by_id=users[0].id,
        )
        trip.members.append(GroupMember(user_id=users[0].id, role=MemberRole.OWNER))
        for user in users[1:]:
            trip.members.append(GroupMember(user_id=user.id, role=MemberRole.MEMBER))

        flat = Group(
            name="Flat 402",
            description="Rent, bills and groceries.",
            currency="INR",
            created_by_id=users[1].id,
        )
        flat.members.append(GroupMember(user_id=users[1].id, role=MemberRole.OWNER))
        for user in (users[0], users[2]):
            flat.members.append(GroupMember(user_id=user.id, role=MemberRole.MEMBER))

        db.session.add_all([trip, flat])
        db.session.flush()

        rng = random.Random(42)
        for index, (title, category, amount, split_type) in enumerate(DEMO_EXPENSES):
            group = trip if index < 3 else flat
            member_ids = [m.user_id for m in group.members]
            payer = rng.choice(member_ids)
            total = Decimal(amount)

            exact = weights = None
            if split_type == SplitType.EXACT:
                even = (total / len(member_ids)).quantize(Decimal("0.01"))
                exact = {uid: str(even) for uid in member_ids[:-1]}
                exact[member_ids[-1]] = str(total - even * (len(member_ids) - 1))
            elif split_type == SplitType.SHARES:
                weights = {uid: str(i + 1) for i, uid in enumerate(member_ids)}

            result = build_shares(
                group, total, split_type, member_ids, exact_amounts=exact, weights=weights
            )
            if not result.ok:  # pragma: no cover - demo data is known-good
                raise click.ClickException("; ".join(result.errors))

            expense = Expense(
                group_id=group.id,
                payer_id=payer,
                description=title,
                category=category,
                amount=total,
                split_type=split_type,
                spent_at=utcnow().date() - timedelta(days=len(DEMO_EXPENSES) - index),
            )
            apply_shares(expense, result.shares)
            db.session.add(expense)

        db.session.add(
            Settlement(
                group_id=trip.id,
                from_user_id=users[3].id,
                to_user_id=users[0].id,
                amount=Decimal("400.00"),
                note="UPI",
                settled_at=utcnow().date() - timedelta(days=1),
            )
        )
        db.session.commit()

        click.echo("Seeded 4 users, 2 groups, 5 expenses and 1 payment.")
        click.echo(f"Sign in as any of {', '.join(u[0] for u in DEMO_USERS)} / {password}")

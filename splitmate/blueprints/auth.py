"""Registration, sign in and sign out."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_, select

from ..extensions import db
from ..forms import LoginForm, RegisterForm
from ..models import User

bp = Blueprint("auth", __name__)


def _safe_next(target: str | None) -> str:
    """Only follow a ``next`` parameter that stays on this site."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("main.dashboard")


@bp.route("/register", methods=["GET", "POST"])
def register():
    """Create an account, then sign the new user straight in.

    Username and email are checked in one query so the form can say which of the
    two is taken, and the username comparison is case-insensitive.
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = form.email.data.strip().lower()

        taken = db.session.scalar(
            select(User).where(
                or_(
                    func.lower(User.username) == username.lower(),
                    User.email == email,
                )
            )
        )
        if taken:
            field = "username" if taken.username.lower() == username.lower() else "email"
            getattr(form, field).errors.append(f"That {field} is already registered.")
        else:
            user = User(
                username=username,
                email=email,
                first_name=form.first_name.data.strip(),
                last_name=(form.last_name.data or "").strip(),
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash(f"Welcome to SplitMate, {user.display_name}.", "success")
            return redirect(url_for("main.dashboard"))

    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Sign in with either the username or the email address.

    A wrong password and an account that does not exist give the same message on
    purpose: telling them apart is a way to find out who has an account here.
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.identifier.data.strip()
        user = db.session.scalar(
            select(User).where(
                or_(
                    func.lower(User.username) == identifier.lower(),
                    User.email == identifier.lower(),
                )
            )
        )
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            flash(f"Signed in as {user.username}.", "success")
            return redirect(_safe_next(request.args.get("next")))
        flash("Those credentials did not match an account.", "error")

    return render_template("auth/login.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    """Sign out. POST only, so a link in an email cannot sign someone out."""
    logout_user()
    flash("Signed out.", "info")
    return redirect(url_for("auth.login"))

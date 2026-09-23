"""Profile settings, password change, theme and account deletion."""

from __future__ import annotations

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user
from sqlalchemy import select

from ..extensions import db
from ..forms import ConfirmForm, PasswordForm, ProfileForm
from ..models import MemberRole, User
from ..services.balances import summaries_for
from ..services.money import ZERO

bp = Blueprint("account", __name__, url_prefix="/account")


@bp.route("/", methods=["GET", "POST"])
@login_required
def settings():
    """Profile and password, as two forms on one page.

    Both are prefixed so their fields cannot collide, and each is processed only
    when its own submit button was the one pressed.
    """
    profile_form = ProfileForm(obj=current_user, prefix="profile")
    password_form = PasswordForm(prefix="password")

    if profile_form.submit.data and profile_form.validate_on_submit():
        email = profile_form.email.data.strip().lower()
        clash = db.session.scalar(
            select(User).where(User.email == email, User.id != current_user.id)
        )
        if clash:
            profile_form.email.errors.append("Another account already uses that email.")
        else:
            current_user.first_name = profile_form.first_name.data.strip()
            current_user.last_name = (profile_form.last_name.data or "").strip()
            current_user.email = email
            current_user.avatar_url = (profile_form.avatar_url.data or "").strip() or None
            current_user.currency = profile_form.currency.data
            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("account.settings"))

    if password_form.submit.data and password_form.validate_on_submit():
        if not current_user.check_password(password_form.current_password.data):
            password_form.current_password.errors.append("That is not your current password.")
        else:
            current_user.set_password(password_form.new_password.data)
            db.session.commit()
            flash("Password updated.", "success")
            return redirect(url_for("account.settings"))

    summaries = summaries_for(current_user, include_archived=True)
    return render_template(
        "account/settings.html",
        profile_form=profile_form,
        password_form=password_form,
        summaries=summaries,
        blocking=[s for s in summaries if s.net != ZERO],
    )


@bp.post("/theme")
@login_required
def set_theme():
    """Persist the light/dark preference chosen in the header."""
    theme = (request.get_json(silent=True) or {}).get("theme", "system")
    if theme not in {"light", "dark", "system"}:
        return jsonify({"error": "unknown theme"}), 400
    current_user.theme = theme
    db.session.commit()
    return jsonify({"theme": theme})


def _has_history(group, user_id: int) -> bool:
    """True when the user is attached to any expense or settlement in the group."""
    for expense in group.expenses:
        if expense.payer_id == user_id or any(s.user_id == user_id for s in expense.shares):
            return True
    return any(
        s.from_user_id == user_id or s.to_user_id == user_id for s in group.settlements
    )


@bp.post("/delete")
@login_required
def delete():
    """Close an account, once every balance is zero and no shared group is left.

    The zero-balance rule is the point: deleting someone who still owes money
    would silently rewrite what everyone else is owed.
    """
    if not ConfirmForm().validate_on_submit():
        abort(400)

    summaries = summaries_for(current_user, include_archived=True)
    if any(s.net != ZERO for s in summaries):
        flash("Settle every balance before deleting your account.", "error")
        return redirect(url_for("account.settings"))

    # Shared history cannot be unpicked: an expense the user paid for, or a
    # share they owed, is part of other members' records too. Groups where the
    # user is on their own go with them; anything shared has to be dealt with
    # first, so the remaining members keep a coherent ledger.
    for membership in list(current_user.memberships):
        group = membership.group
        others = [m for m in group.members if m.user_id != current_user.id]
        if not others:
            db.session.delete(group)
            continue
        if _has_history(group, current_user.id):
            flash(
                f"You still have expense history in {group.name}. "
                "Leave or delete that group first.",
                "error",
            )
            db.session.rollback()
            return redirect(url_for("account.settings"))
        group.members.remove(membership)
        if not any(m.role == MemberRole.OWNER for m in group.members):
            others[0].role = MemberRole.OWNER

    username = current_user.username
    db.session.delete(current_user)
    db.session.commit()
    logout_user()
    flash(f"Account {username} deleted.", "info")
    return redirect(url_for("main.index"))

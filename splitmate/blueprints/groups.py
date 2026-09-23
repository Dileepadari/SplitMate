"""Groups: create, view, edit, membership, settle up and export."""

from __future__ import annotations

import contextlib
import csv
import io
from decimal import Decimal

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, or_, select

from ..access import get_group_or_404, require_owner
from ..extensions import db
from ..forms import AddMemberForm, ConfirmForm, GroupForm, SettlementForm
from ..models import Group, GroupMember, MemberRole, Settlement, User
from ..services.activity import group_activity
from ..services.balances import group_balances, simplify
from ..services.money import ZERO

bp = Blueprint("groups", __name__, url_prefix="/groups")


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = GroupForm()
    if request.method == "GET":
        form.currency.data = current_user.currency

    if form.validate_on_submit():
        group = Group(
            name=form.name.data.strip(),
            description=(form.description.data or "").strip(),
            currency=form.currency.data,
            created_by_id=current_user.id,
        )
        group.members.append(GroupMember(user_id=current_user.id, role=MemberRole.OWNER))
        db.session.add(group)
        db.session.commit()
        flash(f"Group {group.name} created. Add the people you split with.", "success")
        return redirect(url_for("groups.members", group_id=group.id))

    return render_template("groups/form.html", form=form, group=None)


@bp.route("/<int:group_id>")
@login_required
def detail(group_id: int):
    group = get_group_or_404(group_id)
    balances = group_balances(group)
    transfers = simplify(balances)

    query = (request.args.get("q") or "").strip().lower()
    category = request.args.get("category") or ""
    expenses = group.expenses
    if query:
        expenses = [e for e in expenses if query in e.description.lower()
                    or query in e.notes.lower()
                    or query in e.payer.full_name.lower()]
    if category:
        expenses = [e for e in expenses if e.category == category]

    my_balance = next((b.net for b in balances if b.user.id == current_user.id), ZERO)
    return render_template(
        "groups/detail.html",
        group=group,
        balances=balances,
        transfers=transfers,
        expenses=expenses,
        activity=group_activity(group, limit=10),
        my_balance=my_balance,
        query=query,
        category=category,
        is_owner=group.is_owner(current_user.id),
    )


@bp.route("/<int:group_id>/edit", methods=["GET", "POST"])
@login_required
def edit(group_id: int):
    group = get_group_or_404(group_id)
    require_owner(group)

    form = GroupForm(obj=group)
    if form.validate_on_submit():
        group.name = form.name.data.strip()
        group.description = (form.description.data or "").strip()
        group.currency = form.currency.data
        db.session.commit()
        flash("Group updated.", "success")
        return redirect(url_for("groups.detail", group_id=group.id))

    return render_template("groups/form.html", form=form, group=group)


@bp.post("/<int:group_id>/archive")
@login_required
def archive(group_id: int):
    group = get_group_or_404(group_id)
    require_owner(group)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    group.archived = not group.archived
    db.session.commit()
    flash("Group archived." if group.archived else "Group restored.", "info")
    return redirect(url_for("groups.detail", group_id=group.id))


@bp.post("/<int:group_id>/delete")
@login_required
def delete(group_id: int):
    group = get_group_or_404(group_id)
    require_owner(group)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    name = group.name
    db.session.delete(group)
    db.session.commit()
    flash(f"Deleted {name} and everything in it.", "info")
    return redirect(url_for("main.dashboard"))


# -- membership -----------------------------------------------------------


@bp.route("/<int:group_id>/members", methods=["GET", "POST"])
@login_required
def members(group_id: int):
    group = get_group_or_404(group_id)
    form = AddMemberForm()

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
        if user is None:
            form.identifier.errors.append("No SplitMate account matches that username or email.")
        elif group.has_member(user.id):
            form.identifier.errors.append(f"{user.full_name} is already in this group.")
        else:
            group.members.append(GroupMember(user_id=user.id, role=MemberRole.MEMBER))
            db.session.commit()
            flash(f"Added {user.full_name} to {group.name}.", "success")
            return redirect(url_for("groups.members", group_id=group.id))

    balances = {b.user.id: b.net for b in group_balances(group)}
    return render_template(
        "groups/members.html",
        group=group,
        form=form,
        balances=balances,
        is_owner=group.is_owner(current_user.id),
    )


def _remove_member(group: Group, user_id: int) -> str | None:
    """Detach a member, refusing while they still have a non-zero balance."""
    membership = group.membership_for(user_id)
    if membership is None:
        return "That person is not in this group."

    balance = next((b.net for b in group_balances(group) if b.user.id == user_id), ZERO)
    if balance != ZERO:
        return "Settle their balance to zero before removing them."

    owners = [m for m in group.members if m.role == MemberRole.OWNER]
    if membership.role == MemberRole.OWNER and len(owners) == 1 and len(group.members) > 1:
        return "Promote another owner first, or delete the group."

    group.members.remove(membership)
    db.session.commit()
    return None


@bp.post("/<int:group_id>/members/<int:user_id>/remove")
@login_required
def remove_member(group_id: int, user_id: int):
    group = get_group_or_404(group_id)
    require_owner(group)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    if user_id == current_user.id:
        return redirect(url_for("groups.leave", group_id=group.id))

    error = _remove_member(group, user_id)
    flash(error or "Member removed.", "error" if error else "info")
    return redirect(url_for("groups.members", group_id=group.id))


@bp.post("/<int:group_id>/members/<int:user_id>/promote")
@login_required
def promote_member(group_id: int, user_id: int):
    group = get_group_or_404(group_id)
    require_owner(group)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    membership = group.membership_for(user_id)
    if membership is None:
        abort(404)
    membership.role = (
        MemberRole.MEMBER if membership.role == MemberRole.OWNER else MemberRole.OWNER
    )
    db.session.commit()
    flash(f"{membership.user.full_name} is now a {membership.role.value}.", "info")
    return redirect(url_for("groups.members", group_id=group.id))


@bp.post("/<int:group_id>/leave")
@login_required
def leave(group_id: int):
    group = get_group_or_404(group_id)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    if len(group.members) == 1:
        flash("You are the last member. Delete the group instead.", "error")
        return redirect(url_for("groups.detail", group_id=group.id))

    error = _remove_member(group, current_user.id)
    if error:
        flash(error, "error")
        return redirect(url_for("groups.detail", group_id=group.id))
    flash(f"You left {group.name}.", "info")
    return redirect(url_for("main.dashboard"))


# -- settling up ----------------------------------------------------------


@bp.route("/<int:group_id>/settle", methods=["GET", "POST"])
@login_required
def settle(group_id: int):
    group = get_group_or_404(group_id)
    choices = [(m.user_id, m.user.full_name) for m in group.members]

    form = SettlementForm()
    form.from_user_id.choices = choices
    form.to_user_id.choices = choices

    if request.method == "GET":
        form.from_user_id.data = request.args.get("from", type=int) or current_user.id
        form.to_user_id.data = request.args.get("to", type=int)
        suggested = request.args.get("amount", type=str)
        if suggested:
            # A junk ?amount= just means no prefill; the form validates it properly
            # on submit either way.
            with contextlib.suppress(ArithmeticError):
                form.amount.data = Decimal(suggested)

    if form.validate_on_submit():
        db.session.add(
            Settlement(
                group_id=group.id,
                from_user_id=form.from_user_id.data,
                to_user_id=form.to_user_id.data,
                amount=form.amount.data,
                note=(form.note.data or "").strip(),
                settled_at=form.settled_at.data,
            )
        )
        db.session.commit()
        flash("Payment recorded.", "success")
        return redirect(url_for("groups.detail", group_id=group.id))

    balances = group_balances(group)
    return render_template(
        "groups/settle.html",
        group=group,
        form=form,
        balances=balances,
        transfers=simplify(balances),
    )


@bp.post("/<int:group_id>/settlements/<int:settlement_id>/delete")
@login_required
def delete_settlement(group_id: int, settlement_id: int):
    group = get_group_or_404(group_id)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    settlement = db.session.get(Settlement, settlement_id)
    if settlement is None or settlement.group_id != group.id:
        abort(404)
    if not group.is_owner(current_user.id) and settlement.from_user_id != current_user.id:
        abort(403)
    db.session.delete(settlement)
    db.session.commit()
    flash("Payment removed.", "info")
    return redirect(url_for("groups.detail", group_id=group.id))


# -- export ---------------------------------------------------------------



#: Characters that make a spreadsheet treat a cell as a formula rather than text.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value) -> str:
    """Stop a cell being run as a formula when the export is opened.

    Descriptions, notes and usernames are written by group members, and Excel,
    LibreOffice and Sheets all execute a cell beginning ``=``, ``+``, ``-`` or
    ``@``. So one member typing ``=HYPERLINK(...)`` as an expense description
    attacks whoever opens the file. Prefixing with an apostrophe is the standard
    answer: the spreadsheet shows the original text and does not evaluate it.

    Numbers are left alone, otherwise every negative amount would arrive as text.
    """
    text = "" if value is None else str(value)
    if not text.startswith(_FORMULA_PREFIXES):
        return text
    try:
        Decimal(text)
    except (ArithmeticError, ValueError):
        return "'" + text
    return text


@bp.route("/<int:group_id>/export.csv")
@login_required
def export_csv(group_id: int):
    group = get_group_or_404(group_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["type", "date", "description", "category", "paid_by", "amount", "currency", "shares"]
    )
    for expense in sorted(group.expenses, key=lambda e: e.spent_at):
        shares = "; ".join(f"{s.user.username}={s.amount}" for s in expense.shares)
        writer.writerow(
            _csv_safe(cell)
            for cell in (
                "expense",
                expense.spent_at.isoformat(),
                expense.description,
                expense.category,
                expense.payer.username,
                f"{expense.amount}",
                group.currency,
                shares,
            )
        )
    for settlement in sorted(group.settlements, key=lambda s: s.settled_at):
        writer.writerow(
            _csv_safe(cell)
            for cell in (
                "settlement",
                settlement.settled_at.isoformat(),
                settlement.note or "Payment",
                "settlement",
                settlement.from_user.username,
                f"{settlement.amount}",
                group.currency,
                f"{settlement.to_user.username}={settlement.amount}",
            )
        )

    slug = "".join(c if c.isalnum() else "-" for c in group.name).strip("-").lower() or "group"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="splitmate-{slug}.csv"'},
    )

"""Adding, editing, viewing and deleting expenses inside a group."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..access import get_expense_or_404, get_group_or_404
from ..extensions import db
from ..forms import ConfirmForm, ExpenseForm
from ..models import Expense, SplitType
from ..services.expenses import apply_shares, build_shares, read_split_input

bp = Blueprint("expenses", __name__, url_prefix="/groups/<int:group_id>/expenses")


def _member_choices(group):
    return [(m.user_id, m.user.full_name) for m in group.members]


def _selected_state(group, expense: Expense | None):
    """Pre-tick the participant boxes: everyone for a new expense, the saved set for an edit."""
    if expense is None:
        return (
            [m.user_id for m in group.members],
            {},
            {m.user_id: "1" for m in group.members},
        )
    return (
        [s.user_id for s in expense.shares],
        {s.user_id: f"{s.amount}" for s in expense.shares},
        {s.user_id: str(s.weight) for s in expense.shares},
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new(group_id: int):
    group = get_group_or_404(group_id)
    if not group.members:
        abort(404)

    form = ExpenseForm()
    form.payer_id.choices = _member_choices(group)
    selected, exact, weights = _selected_state(group, None)

    if request.method == "GET":
        form.payer_id.data = current_user.id
    else:
        selected, exact, weights = read_split_input(request.form)

    if form.validate_on_submit():
        split_type = SplitType(form.split_type.data)
        result = build_shares(
            group, form.amount.data, split_type, selected, exact_amounts=exact, weights=weights
        )
        if result.ok:
            expense = Expense(
                group_id=group.id,
                payer_id=form.payer_id.data,
                description=form.description.data.strip(),
                notes=(form.notes.data or "").strip(),
                category=form.category.data,
                amount=form.amount.data,
                split_type=split_type,
                spent_at=form.spent_at.data,
            )
            apply_shares(expense, result.shares)
            db.session.add(expense)
            db.session.commit()
            flash(f"Added {expense.description}.", "success")
            return redirect(url_for("groups.detail", group_id=group.id))
        for message in result.errors:
            flash(message, "error")

    return render_template(
        "expenses/form.html",
        group=group,
        form=form,
        expense=None,
        selected=selected,
        exact=exact,
        weights=weights,
    )


@bp.route("/<int:expense_id>")
@login_required
def detail(group_id: int, expense_id: int):
    group = get_group_or_404(group_id)
    expense = get_expense_or_404(group, expense_id)
    return render_template("expenses/detail.html", group=group, expense=expense)


@bp.route("/<int:expense_id>/edit", methods=["GET", "POST"])
@login_required
def edit(group_id: int, expense_id: int):
    group = get_group_or_404(group_id)
    expense = get_expense_or_404(group, expense_id)

    form = ExpenseForm(obj=expense) if request.method == "GET" else ExpenseForm()
    form.payer_id.choices = _member_choices(group)
    selected, exact, weights = _selected_state(group, expense)

    if request.method == "GET":
        form.payer_id.data = expense.payer_id
        form.split_type.data = expense.split_type.value
    else:
        selected, exact, weights = read_split_input(request.form)

    if form.validate_on_submit():
        split_type = SplitType(form.split_type.data)
        result = build_shares(
            group, form.amount.data, split_type, selected, exact_amounts=exact, weights=weights
        )
        if result.ok:
            expense.payer_id = form.payer_id.data
            expense.description = form.description.data.strip()
            expense.notes = (form.notes.data or "").strip()
            expense.category = form.category.data
            expense.amount = form.amount.data
            expense.split_type = split_type
            expense.spent_at = form.spent_at.data
            apply_shares(expense, result.shares)
            db.session.commit()
            flash("Expense updated.", "success")
            return redirect(url_for("expenses.detail", group_id=group.id, expense_id=expense.id))
        for message in result.errors:
            flash(message, "error")

    return render_template(
        "expenses/form.html",
        group=group,
        form=form,
        expense=expense,
        selected=selected,
        exact=exact,
        weights=weights,
    )


@bp.post("/<int:expense_id>/delete")
@login_required
def delete(group_id: int, expense_id: int):
    group = get_group_or_404(group_id)
    expense = get_expense_or_404(group, expense_id)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    if expense.payer_id != current_user.id and not group.is_owner(current_user.id):
        abort(403)

    description = expense.description
    db.session.delete(expense)
    db.session.commit()
    flash(f"Deleted {description}.", "info")
    return redirect(url_for("groups.detail", group_id=group.id))

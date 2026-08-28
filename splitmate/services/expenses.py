"""Turning submitted form data into a valid set of expense shares.

The three split modes all end at the same invariant: the shares attached to an
expense sum exactly to the expense amount, and every participant is a current
member of the group.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..models import Expense, ExpenseShare, Group, SplitType
from .money import ZERO, quantize, split_by_weights, split_equal, to_decimal


@dataclass
class SplitResult:
    """Either a validated ``{user_id: (amount, weight)}`` map, or the errors that blocked it."""

    shares: dict[int, tuple[Decimal, int]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def build_shares(
    group: Group,
    amount: Decimal,
    split_type: SplitType,
    participant_ids: list[int],
    exact_amounts: dict[int, str] | None = None,
    weights: dict[int, str] | None = None,
) -> SplitResult:
    """Validate a split and return the per-participant amounts."""
    result = SplitResult()
    member_ids = {m.user_id for m in group.members}

    ordered = [uid for uid in dict.fromkeys(participant_ids) if uid in member_ids]
    unknown = set(participant_ids) - member_ids
    if unknown:
        result.errors.append("Someone in that split is not a member of this group.")
    if not ordered:
        result.errors.append("Pick at least one person to split between.")
        return result

    amount = quantize(amount)
    if amount <= ZERO:
        result.errors.append("Amount must be greater than zero.")
        return result

    if split_type == SplitType.EQUAL:
        amounts = split_equal(amount, len(ordered))
        result.shares = {uid: (amounts[i], 1) for i, uid in enumerate(ordered)}
        return result

    if split_type == SplitType.EXACT:
        exact_amounts = exact_amounts or {}
        parsed: dict[int, Decimal] = {}
        for uid in ordered:
            value = to_decimal(exact_amounts.get(uid))
            if value is None:
                result.errors.append("Every selected person needs an exact amount.")
                return result
            if value < ZERO:
                result.errors.append("Exact amounts cannot be negative.")
                return result
            parsed[uid] = value
        total = quantize(sum(parsed.values(), ZERO))
        if total != amount:
            result.errors.append(
                f"Exact amounts add up to {total}, but the expense is {amount}."
            )
            return result
        result.shares = {uid: (parsed[uid], 1) for uid in ordered}
        return result

    # SHARES
    weights = weights or {}
    parsed_weights: list[int] = []
    for uid in ordered:
        raw = weights.get(uid, "1")
        try:
            weight = int(str(raw).strip() or "1")
        except (TypeError, ValueError):
            result.errors.append("Shares must be whole numbers.")
            return result
        if weight < 0:
            result.errors.append("Shares cannot be negative.")
            return result
        parsed_weights.append(weight)

    if sum(parsed_weights) <= 0:
        result.errors.append("At least one person needs a share above zero.")
        return result

    amounts = split_by_weights(amount, parsed_weights)
    result.shares = {uid: (amounts[i], parsed_weights[i]) for i, uid in enumerate(ordered)}
    return result


def apply_shares(expense: Expense, shares: dict[int, tuple[Decimal, int]]) -> None:
    """Reconcile an expense's shares against ``shares``.

    Existing rows are updated in place rather than deleted and recreated. A
    delete-then-insert would put both versions of the same (expense, user) pair
    in one flush, and the unique constraint rejects that.
    """
    existing = {share.user_id: share for share in expense.shares}

    for user_id, (amount, weight) in shares.items():
        share = existing.pop(user_id, None)
        if share is None:
            expense.shares.append(ExpenseShare(user_id=user_id, amount=amount, weight=weight))
        else:
            share.amount = amount
            share.weight = weight

    for share in existing.values():
        expense.shares.remove(share)


def read_split_input(form_data) -> tuple[list[int], dict[int, str], dict[int, str]]:
    """Pull participants, exact amounts and weights out of a submitted form.

    Fields are named ``participant``, ``exact-<user_id>`` and ``weight-<user_id>``.
    """
    participants: list[int] = []
    for raw in form_data.getlist("participant"):
        try:
            participants.append(int(raw))
        except (TypeError, ValueError):
            continue

    exact = {}
    weights = {}
    for key, value in form_data.items():
        if key.startswith("exact-"):
            try:
                exact[int(key[6:])] = value
            except ValueError:
                continue
        elif key.startswith("weight-"):
            try:
                weights[int(key[7:])] = value
            except ValueError:
                continue
    return participants, exact, weights

"""Who owes whom.

A member's *net balance* in a group is what they paid out minus what they
consumed, adjusted by any settlements already recorded:

    net = expenses_paid - shares_owed + settlements_sent - settlements_received

A positive net means the group owes that member. Nets always sum to zero.
``simplify`` then turns those nets into the smallest set of payments that
clears everyone, rather than one payment per expense.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from ..models import Group, User
from .money import ZERO, quantize


@dataclass(frozen=True)
class Balance:
    """One member's net position in a group."""

    user: User
    paid: Decimal
    owed: Decimal
    settled_out: Decimal
    settled_in: Decimal

    @property
    def net(self) -> Decimal:
        """Positive when the group owes this member, negative when they owe the group."""
        return quantize(self.paid - self.owed + self.settled_out - self.settled_in)

    @property
    def is_creditor(self) -> bool:
        """They are owed money."""
        return self.net > ZERO

    @property
    def is_debtor(self) -> bool:
        """They owe money."""
        return self.net < ZERO


@dataclass(frozen=True)
class Transfer:
    """A suggested payment that moves the group closer to settled."""

    debtor: User
    creditor: User
    amount: Decimal


def group_balances(group: Group) -> list[Balance]:
    """Net position for every current member of ``group``, biggest creditor first."""
    paid: dict[int, Decimal] = defaultdict(lambda: ZERO)
    owed: dict[int, Decimal] = defaultdict(lambda: ZERO)
    sent: dict[int, Decimal] = defaultdict(lambda: ZERO)
    received: dict[int, Decimal] = defaultdict(lambda: ZERO)

    for expense in group.expenses:
        paid[expense.payer_id] += expense.amount
        for share in expense.shares:
            owed[share.user_id] += share.amount

    for settlement in group.settlements:
        sent[settlement.from_user_id] += settlement.amount
        received[settlement.to_user_id] += settlement.amount

    balances = [
        Balance(
            user=member.user,
            paid=quantize(paid[member.user_id]),
            owed=quantize(owed[member.user_id]),
            settled_out=quantize(sent[member.user_id]),
            settled_in=quantize(received[member.user_id]),
        )
        for member in group.members
    ]
    balances.sort(key=lambda b: (-b.net, b.user.full_name.lower()))
    return balances


def simplify(balances: list[Balance]) -> list[Transfer]:
    """Greedily match the largest debtor against the largest creditor.

    For n members this produces at most n-1 transfers, which is the minimum
    possible number in the general case.
    """
    creditors = sorted(
        [[b.user, b.net] for b in balances if b.net > ZERO], key=lambda p: -p[1]
    )
    debtors = sorted([[b.user, -b.net] for b in balances if b.net < ZERO], key=lambda p: -p[1])

    transfers: list[Transfer] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor, debt = debtors[i]
        creditor, credit = creditors[j]
        amount = quantize(min(debt, credit))
        if amount > ZERO:
            transfers.append(Transfer(debtor=debtor, creditor=creditor, amount=amount))
        debtors[i][1] -= amount
        creditors[j][1] -= amount
        if debtors[i][1] <= ZERO:
            i += 1
        if creditors[j][1] <= ZERO:
            j += 1
    return transfers


def balance_for(group: Group, user_id: int) -> Decimal:
    """Signed net balance of one user in one group."""
    for balance in group_balances(group):
        if balance.user.id == user_id:
            return balance.net
    return ZERO


@dataclass(frozen=True)
class GroupSummary:
    """A group as it appears on the dashboard and in the sidebar."""

    group: Group
    net: Decimal
    total_spend: Decimal
    member_count: int
    expense_count: int

    @property
    def owed_to_me(self) -> Decimal:
        """The credit side of the net, or zero. Kept separate so the dashboard can show both."""
        return self.net if self.net > ZERO else ZERO

    @property
    def i_owe(self) -> Decimal:
        """The debit side of the net, unsigned, or zero."""
        return -self.net if self.net < ZERO else ZERO


def summaries_for(user: User, include_archived: bool = False) -> list[GroupSummary]:
    """Summarise every group ``user`` belongs to, most recently active first."""
    summaries = []
    for membership in user.memberships:
        group = membership.group
        if group.archived and not include_archived:
            continue
        summaries.append(
            GroupSummary(
                group=group,
                net=balance_for(group, user.id),
                total_spend=group.total_spend,
                member_count=len(group.members),
                expense_count=len(group.expenses),
            )
        )
    summaries.sort(key=lambda s: (abs(s.net), s.group.created_at), reverse=True)
    return summaries


@dataclass(frozen=True)
class Totals:
    """The headline numbers on the dashboard."""

    owed_to_you: Decimal
    you_owe: Decimal

    @property
    def net(self) -> Decimal:
        """One number for the whole account: positive means ahead overall."""
        return quantize(self.owed_to_you - self.you_owe)


def totals_for(summaries: list[GroupSummary]) -> Totals:
    """Add the two sides up across every group, for the dashboard header."""
    return Totals(
        owed_to_you=quantize(sum((s.owed_to_me for s in summaries), ZERO)),
        you_owe=quantize(sum((s.i_owe for s in summaries), ZERO)),
    )

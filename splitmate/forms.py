"""WTForms definitions.

Split details (which members take part, and their exact amounts or shares) are
dynamic per group, so they are validated in
:mod:`splitmate.services.expenses` rather than declared as fields here.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    DecimalField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

from .models import utcnow
from .services.money import CURRENCY_SYMBOLS, MAX_AMOUNT, is_usable_amount


def latest_allowed_date() -> date:
    """The furthest date a user may put on an expense or a payment.

    Every datetime column stores UTC, but ``date.today()`` is whatever the
    *server's* clock says. Validating against it means a user in UTC+5:30
    recording an expense at 2am is told their own today is in the future,
    because the server is still on yesterday. No timezone is more than about
    fourteen hours from UTC, so allowing one extra day accepts a real "today"
    anywhere on the planet while still rejecting a date that is genuinely ahead.
    """
    return utcnow().date() + timedelta(days=1)


class UsableAmount:
    """Reject a money value the application cannot store.

    ``NumberRange`` is not enough on its own. ``Decimal`` accepts ``NaN`` and
    ``Infinity`` as ordinary values and puts no ceiling on the exponent, and
    comparing a ``NaN`` against the bound does not raise, it answers False, so
    the field validates and the failure surfaces later as a 500 from
    ``quantize``. This says what the field actually requires.
    """

    def __init__(self, message: str | None = None):
        self.message = message or f"Enter an amount between 0.01 and {MAX_AMOUNT}."

    def __call__(self, form, field):
        if field.data is None:
            return
        if not is_usable_amount(field.data):
            raise ValidationError(self.message)


USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

CURRENCY_CHOICES = [(code, f"{code} {sym.strip()}") for code, sym in CURRENCY_SYMBOLS.items()]

CATEGORY_CHOICES = [
    ("general", "General"),
    ("food", "Food and drink"),
    ("groceries", "Groceries"),
    ("rent", "Rent and bills"),
    ("travel", "Travel"),
    ("transport", "Transport"),
    ("entertainment", "Entertainment"),
    ("shopping", "Shopping"),
    ("health", "Health"),
    ("other", "Other"),
]

CATEGORY_ICONS = {
    "general": "receipt",
    "food": "utensils",
    "groceries": "basket",
    "rent": "home",
    "travel": "plane",
    "transport": "car",
    "entertainment": "ticket",
    "shopping": "bag",
    "health": "heart",
    "other": "tag",
}


class RegisterForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(3, 40),
            Regexp(USERNAME_RE, message="Letters, numbers, dot, dash and underscore only."),
        ],
    )
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    first_name = StringField("First name", validators=[DataRequired(), Length(max=60)])
    last_name = StringField("Last name", validators=[Optional(), Length(max=60)])
    password = PasswordField("Password", validators=[DataRequired(), Length(8, 128)])
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")],
    )
    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    identifier = StringField("Username or email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Keep me signed in")
    submit = SubmitField("Sign in")


class ProfileForm(FlaskForm):
    first_name = StringField("First name", validators=[DataRequired(), Length(max=60)])
    last_name = StringField("Last name", validators=[Optional(), Length(max=60)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    avatar_url = StringField("Avatar image URL", validators=[Optional(), Length(max=500)])
    currency = SelectField("Preferred currency", choices=CURRENCY_CHOICES)
    submit = SubmitField("Save changes")


class PasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField("New password", validators=[DataRequired(), Length(8, 128)])
    confirm = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords do not match.")],
    )
    submit = SubmitField("Update password")


class GroupForm(FlaskForm):
    name = StringField("Group name", validators=[DataRequired(), Length(2, 80)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=500)])
    currency = SelectField("Currency", choices=CURRENCY_CHOICES)
    submit = SubmitField("Save group")


class AddMemberForm(FlaskForm):
    identifier = StringField(
        "Username or email", validators=[DataRequired(), Length(max=255)]
    )
    submit = SubmitField("Add member")


class ExpenseForm(FlaskForm):
    """The fixed part of an expense. Participants are read from the raw form data."""

    description = StringField("Description", validators=[DataRequired(), Length(2, 140)])
    amount = DecimalField(
        "Amount",
        places=2,
        validators=[
            InputRequired(message="Enter an amount."),
            UsableAmount(),
            NumberRange(min=0.01, message="Amount must be positive."),
        ],
    )
    payer_id = SelectField("Paid by", coerce=int, validators=[DataRequired()])
    category = SelectField("Category", choices=CATEGORY_CHOICES, default="general")
    spent_at = DateField("Date", default=date.today, validators=[DataRequired()])
    split_type = SelectField(
        "Split",
        choices=[("equal", "Split equally"), ("exact", "Exact amounts"), ("shares", "By shares")],
        default="equal",
    )
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Save expense")

    def validate_spent_at(self, field):
        if field.data and field.data > latest_allowed_date():
            raise ValidationError("The date cannot be in the future.")


class SettlementForm(FlaskForm):
    from_user_id = SelectField("Paid by", coerce=int, validators=[DataRequired()])
    to_user_id = SelectField("Paid to", coerce=int, validators=[DataRequired()])
    amount = DecimalField(
        "Amount",
        places=2,
        validators=[
            InputRequired(message="Enter an amount."),
            UsableAmount(),
            NumberRange(min=0.01, message="Amount must be positive."),
        ],
    )
    note = StringField("Note", validators=[Optional(), Length(max=140)])
    settled_at = DateField("Date", default=date.today, validators=[DataRequired()])
    submit = SubmitField("Record payment")

    def validate_to_user_id(self, field):
        if field.data == self.from_user_id.data:
            raise ValidationError("Pick two different people.")

    def validate_settled_at(self, field):
        if field.data and field.data > latest_allowed_date():
            raise ValidationError("The date cannot be in the future.")


class ConfirmForm(FlaskForm):
    """Bare CSRF-protected form for destructive POST buttons."""

    submit = SubmitField("Confirm")

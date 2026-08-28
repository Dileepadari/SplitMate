# SplitMate - Developer Documentation

Technical reference for the SplitMate codebase: architecture, auth model, data model,
route surface, and setup/deployment. For what the app does from a user's point of view,
see [README.md](./README.md).

## Table of contents

- [Tech stack](#tech-stack)
- [Architecture overview](#architecture-overview)
- [Auth model](#auth-model)
- [Data model](#data-model)
- [Money handling](#money-handling)
- [Balance and settle-up algorithm](#balance-and-settle-up-algorithm)
- [Route surface](#route-surface)
- [Theming](#theming)
- [Project structure](#project-structure)
- [Testing](#testing)
- [Environment variables](#environment-variables)
- [Local development](#local-development)
- [Deployment](#deployment)
- [Known constraints and gotchas](#known-constraints-and-gotchas)

## Tech stack

Python 3.11+, Flask 3.1 with an application factory and blueprints, SQLAlchemy 2.0 through
Flask-SQLAlchemy 3.1 (typed `Mapped[...]` declarative models), Flask-Login for sessions,
Flask-WTF for forms and CSRF, Flask-Migrate/Alembic for schema migrations, and SQLite by
default through any SQLAlchemy URL.

The frontend is server-rendered Jinja with one hand-written stylesheet and one progressive
enhancement script. There is deliberately no bundler, no CSS framework and no CDN
dependency: icons are an inline SVG macro set, and the only external request is the Google
Fonts stylesheet. That keeps `pip install` plus `python wsgi.py` the entire setup.

## Architecture overview

```
  Browser
     |  HTML forms, one <form> per action, POST for anything that mutates
     v
  Flask app (splitmate/__init__.py: create_app)
     |
     +-- blueprints/        request handling, validation, redirects, flashes
     |      auth  main  groups  expenses  account
     |
     +-- forms.py           WTForms field definitions and field-level validation
     |
     +-- access.py          "is this user allowed to touch this group" checks
     |
     +-- services/          domain logic, no Flask imports
     |      money.py        Decimal arithmetic and splitting
     |      expenses.py     turning form input into a valid set of shares
     |      balances.py     nets, simplification, dashboard summaries
     |      activity.py     merged expense + settlement feed
     |
     +-- models.py          SQLAlchemy models
            |
            v
        SQLite / Postgres
```

Blueprints hold no arithmetic. Anything that computes a number lives in `services/` and is
importable without an app context, which is why the money and balance tests need no HTTP
layer at all.

## Auth model

Sessions are cookie-based via Flask-Login. `login_user` writes the user id into Flask's
signed session cookie; `@login_required` on a view redirects anonymous requests to
`/login?next=...`.

- Passwords are hashed with `werkzeug.security.generate_password_hash` (scrypt by default). Plaintext is never stored or logged.
- `SESSION_PROTECTION = "strong"` invalidates the session when the client identity changes.
- The session cookie is `HttpOnly` and `SameSite=Lax`. It is `Secure` in production, controlled by `SESSION_COOKIE_SECURE`.
- "Keep me signed in" issues a remember cookie valid for 14 days.
- CSRF protection is global via `CSRFProtect`. Every mutating form includes `{{ form.csrf_token }}`, including the single-button destructive actions, which use the bare `ConfirmForm`.
- The `next` parameter after login is only followed when it is a site-relative path, so the login form cannot be used as an open redirect (`auth._safe_next`).

Authorisation is separate from authentication and lives in `access.py`:

- `get_group_or_404` returns the group only if the current user is a member. A non-member gets **404, not 403**, so the app never confirms that a group id exists to someone with no business knowing.
- `require_owner` raises 403 for a member who is not an owner. This is a real 403 because the user already knows the group exists.
- `get_expense_or_404` additionally checks the expense belongs to the group in the URL, so `/groups/1/expenses/999` cannot reach another group's expense.

## Data model

All datetime columns store timezone-aware UTC (`models.utcnow`). `spent_at` and `settled_at`
are plain dates, because "which day was this expense" is a calendar fact, not an instant.

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `username` | str(40) | unique, indexed, case-insensitive on lookup |
| `email` | str(255) | unique, indexed, always stored lowercased |
| `password_hash` | str(255) | scrypt via Werkzeug |
| `first_name`, `last_name` | str(60) | `last_name` may be empty |
| `avatar_url` | str(500) nullable | falls back to initials in the UI |
| `currency` | str(3) | preferred currency, default from `DEFAULT_CURRENCY` |
| `theme` | str(10) | `light`, `dark` or `system` |
| `created_at` | datetime | UTC |

### `groups`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `name` | str(80) | not unique; two groups may share a name |
| `description` | text | may be empty |
| `currency` | str(3) | every amount in the group is in this currency |
| `archived` | bool | archived groups leave the sidebar and dashboard totals |
| `created_by_id` | FK users nullable | `ON DELETE SET NULL`, historical metadata only |
| `created_at` | datetime | UTC |

`created_by_id` is deliberately nullable. Who is in charge is the `OWNER` role on
`group_members`, not this column, so a creator deleting their account must not block or
cascade-delete a group that other people are still using.

### `group_members`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `group_id` | FK groups | `ON DELETE CASCADE` |
| `user_id` | FK users | `ON DELETE CASCADE` |
| `role` | enum | `owner` or `member`, stored as a string |
| `joined_at` | datetime | UTC |

Unique on `(group_id, user_id)`.

### `expenses`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `group_id` | FK groups | `ON DELETE CASCADE`, indexed |
| `payer_id` | FK users | who actually paid the bill |
| `description` | str(140) | |
| `notes` | text | |
| `category` | str(30) | one of `forms.CATEGORY_CHOICES` |
| `amount` | numeric(12,2) | check constraint `amount > 0` |
| `split_type` | enum | `equal`, `exact` or `shares` |
| `spent_at` | date | never in the future |
| `created_at`, `updated_at` | datetime | UTC |

Composite index on `(group_id, spent_at)`.

### `expense_shares`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `expense_id` | FK expenses | `ON DELETE CASCADE`, indexed |
| `user_id` | FK users | `ON DELETE CASCADE`, indexed |
| `amount` | numeric(12,2) | this participant's slice |
| `weight` | int | the share weight, 1 for equal and exact splits |

Unique on `(expense_id, user_id)`. **The shares of an expense always sum exactly to
`expenses.amount`.** Every write path goes through `services.expenses.build_shares`, which
is what enforces it.

The payer is not automatically a participant. Paying for a meal you did not eat is a real
case, and it is expressed by leaving the payer out of the participant list.

### `settlements`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `group_id` | FK groups | `ON DELETE CASCADE` |
| `from_user_id`, `to_user_id` | FK users | check constraint that they differ |
| `amount` | numeric(12,2) | check constraint `amount > 0` |
| `note` | str(140) | "UPI", "cash", etc |
| `settled_at` | date | never in the future |

A settlement is money that actually changed hands. It never edits an expense.

## Money handling

Every amount is a `Decimal` on a `Numeric(12, 2)` column. Nothing in the codebase puts a
float on a money column, and `services/money.py` is the only place arithmetic happens.

The problem it solves: dividing 100.00 three ways gives 33.33 each, which sums to 99.99. A
cent vanishes, and after a few expenses the balances no longer sum to zero.

- `split_equal(total, n)` floors each part, then hands out the leftover minor units one cent at a time to the earliest participants. Deterministic, and the parts always sum to `total`.
- `split_by_weights(total, weights)` uses the largest-remainder method: floor each proportional share, then give the remaining cents to the participants with the biggest fractional remainders.
- `quantize` rounds half-up to 2 places, matching how people round money rather than Python's default banker's rounding.
- `to_decimal` parses user input tolerantly (strips thousands separators) and returns `None` rather than raising on junk.

`tests/test_money.py` asserts the sum-to-total invariant across a parametrised set of awkward cases.

## Balance and settle-up algorithm

A member's **net balance** in a group:

```
net = expenses_paid - shares_owed + settlements_sent - settlements_received
```

Positive means the group owes them. Because every expense contributes its full amount to
one payer and distributes exactly that amount across shares, and every settlement adds and
subtracts the same figure, **the nets always sum to zero**. `test_balances_sum_to_zero`
guards this.

`balances.simplify` then converts nets into payments greedily: sort creditors and debtors
by size, match the largest of each, subtract the smaller amount, advance past whoever hit
zero, repeat. For n members this emits at most n-1 transfers, the minimum in the general
case, and applying every transfer drives every net to zero (`test_simplify_clears_every_balance`).

This is intentionally *not* the NP-hard minimum-transaction problem. The greedy result is
optimal in the common case and always correct; chasing the theoretical minimum for
pathological share structures is not worth the complexity here.

## Route surface

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/` | anyone | Landing page, or redirect to the dashboard when signed in |
| GET | `/dashboard` | member | Totals, group table, recent activity |
| GET | `/about` | anyone | Public or in-shell About page |
| GET | `/healthz` | anyone | `{"status": "ok"}` |
| GET POST | `/register` | anonymous | Create an account and sign in |
| GET POST | `/login` | anonymous | Sign in by username or email |
| POST | `/logout` | member | End the session |
| GET POST | `/groups/new` | member | Create a group, become its owner |
| GET | `/groups/<id>` | group member | Balances, transfers, expense list, filters |
| GET POST | `/groups/<id>/edit` | owner | Rename, describe, change currency |
| POST | `/groups/<id>/archive` | owner | Toggle archived |
| POST | `/groups/<id>/delete` | owner | Delete the group and everything in it |
| GET POST | `/groups/<id>/members` | group member | List members, add by username or email |
| POST | `/groups/<id>/members/<uid>/remove` | owner | Remove a settled member |
| POST | `/groups/<id>/members/<uid>/promote` | owner | Toggle owner and member |
| POST | `/groups/<id>/leave` | group member | Leave when settled |
| GET POST | `/groups/<id>/settle` | group member | Suggested transfers, record a payment |
| POST | `/groups/<id>/settlements/<sid>/delete` | owner or payer | Undo a recorded payment |
| GET | `/groups/<id>/export.csv` | group member | CSV of expenses, shares and payments |
| GET POST | `/groups/<id>/expenses/new` | group member | Add an expense |
| GET | `/groups/<id>/expenses/<eid>` | group member | Split breakdown |
| GET POST | `/groups/<id>/expenses/<eid>/edit` | group member | Edit an expense |
| POST | `/groups/<id>/expenses/<eid>/delete` | payer or owner | Delete an expense |
| GET POST | `/account/` | member | Profile and password, two prefixed forms on one page |
| POST | `/account/theme` | member | Persist the theme, JSON |
| POST | `/account/delete` | member | Delete the account when clear |

Every mutating route is POST-only and CSRF-protected. There are no destructive GET links.

### Dynamic split fields

Which members take part, and their exact amounts or weights, depend on the group, so they
are not WTForms fields. They are read from the raw form data by
`services.expenses.read_split_input`, which expects:

- `participant` - repeated, one per ticked member id
- `exact-<user_id>` - the amount for that member when `split_type=exact`
- `weight-<user_id>` - the share weight when `split_type=shares`

`build_shares` validates them and returns either a `{user_id: (amount, weight)}` map or a
list of human-readable errors, which the route flashes.

## Theming

Light and dark are the same CSS custom properties with different values, defined once in
two blocks at the top of `static/css/app.css`. Nothing below the token block hard-codes a
colour.

The theme is resolved before first paint by an inline script in `base.html`, in this order:

1. `data-theme` already on `<html>`, server-rendered from `users.theme` when it is not `system`
2. `localStorage['splitmate-theme']`
3. `prefers-color-scheme`

Toggling writes to `localStorage` immediately and POSTs to `/account/theme` in the
background, so the preference follows the account across devices but still works if that
request fails. Every `localStorage` access is wrapped in try/catch for private browsing.

The ADK DEV mark is a single purple-on-transparent PNG. It reads in both themes through
`--logo-filter`: `brightness(0)` in light mode and `brightness(0) invert(1)` in dark.
There is no second recoloured file.

## Project structure

```
splitmate/
  __init__.py          app factory, filters, context processor, error handlers
  config.py            Development / Testing / Production config classes
  extensions.py        db, migrate, csrf, login_manager, SQLite FK pragma
  models.py            SQLAlchemy models
  forms.py             WTForms definitions, category and currency choices
  access.py            group and expense authorisation helpers
  cli.py               flask init-db / reset-db / seed-demo
  blueprints/          one module per area of the app
  services/            domain logic with no Flask imports
  templates/
    base.html          document skeleton, theme bootstrap, flash region
    shell.html         signed-in layout: header, sidebar, main
    partials/          icons.html (SVG set), ui.html (macros), about_body.html
    auth/ groups/ expenses/ account/ errors/
  static/
    css/app.css        the whole design system
    js/app.js          theme toggle, mobile nav, live split calculator
    img/logo-mark.png  ADK DEV mark, favicon and app badge
migrations/            Alembic
tests/                 pytest
wsgi.py                entry point
```

## Testing

```bash
.venv/bin/pytest                              # 95 tests
.venv/bin/pytest --cov=splitmate --cov-report=term-missing
```

Tests run against an in-memory SQLite database with CSRF disabled (`TestingConfig`). Each
test gets a fresh schema through the `app` fixture. Coverage is around 93%.

| File | Covers |
|---|---|
| `test_money.py` | Splitting invariants, rounding, parsing, formatting. No app context needed |
| `test_balances.py` | Nets, settlements, all three split types, simplification, dashboard totals |
| `test_split_validation.py` | Every rejection path in `build_shares`, plus a smoke render of every page |
| `test_auth.py` | Registration, login, logout, route protection, open-redirect guard |
| `test_groups.py` | Group lifecycle, membership, permissions, settling, CSV export, filters |
| `test_expenses.py` | Expense CRUD over HTTP, split correctness, validation, delete permissions |
| `test_account.py` | Profile, password, theme, account deletion guards |

`tests/factories.py` holds `make_user`, `make_group` and `add_expense`. `add_expense`
asserts the split is valid, so a broken split fails loudly in the factory rather than
producing a confusing assertion later.

Not covered: the JavaScript split calculator (it only previews what the server recomputes
and validates), and `cli.py` seed data.

## Environment variables

All are server-side. There is no client bundle, so nothing here reaches the browser except
through rendered HTML.

| Variable | Default | Purpose |
|---|---|---|
| `SPLITMATE_CONFIG` | `development` | `development`, `testing` or `production` |
| `SECRET_KEY` | `dev-only-change-me` | Signs the session cookie and CSRF tokens. **Production refuses to boot on the default** |
| `DATABASE_URL` | `sqlite:///instance/splitmate.db` | Any SQLAlchemy URL |
| `DEFAULT_CURRENCY` | `INR` | Currency for new accounts and groups |
| `SESSION_COOKIE_SECURE` | `false` dev, `true` prod | Set false only when serving over plain HTTP |
| `ITEMS_PER_PAGE` | `20` | Reserved for pagination |

`.env` is loaded by `python-dotenv` at import time. `.env.example` is the template; `.env`
itself is gitignored, as is any file ending in `.env`.

## Local development

From a fresh clone:

```bash
cd SplitMate
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements-dev.txt      # runtime + pytest

cp .env.example .env                     # then edit SECRET_KEY if you like

export FLASK_APP=wsgi.py
flask db upgrade                         # creates instance/splitmate.db
flask seed-demo                          # optional sample data

python wsgi.py                           # http://127.0.0.1:5000
```

Seeded accounts: `dileep`, `aadi`, `chanukya`, `riya`, all with password `splitmate123`.

Other commands:

```bash
flask init-db                            # create tables without Alembic
flask reset-db                           # drop and recreate, prompts first
flask db migrate -m "what changed"       # after editing models.py
flask db upgrade
pytest
```

## Deployment

```bash
export SPLITMATE_CONFIG=production
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DATABASE_URL=postgresql+psycopg://user:pass@host/splitmate
export SESSION_COOKIE_SECURE=true

pip install -r requirements.txt
flask db upgrade
gunicorn --workers 4 --bind 0.0.0.0:8000 wsgi:app
```

Run `flask db upgrade` before starting the new workers, never after. Terminate TLS at a
reverse proxy; `SESSION_COOKIE_SECURE=true` means the session cookie will not be sent over
plain HTTP, so the app appears to silently reject every login if you set it without HTTPS.

## Known constraints and gotchas

**SQLite ignores foreign keys unless you ask.** Every `ON DELETE CASCADE` in the schema is
inert on SQLite without `PRAGMA foreign_keys=ON`. `extensions.py` registers a
`"connect"` event listener that issues it on every new connection. Remove that and deleting
a group silently orphans its expenses instead of cascading.

**Replacing an expense's shares cannot be delete-then-insert.** `expense_shares` is unique
on `(expense_id, user_id)`. Clearing the collection and appending new rows puts both
versions of the same pair in one flush, and SQLAlchemy emits the INSERT before the DELETE,
so the constraint fires. `services.expenses.apply_shares` reconciles in place instead:
update the rows that survive, append the new ones, remove the rest. This was a real bug
caught by `test_editing_an_expense_replaces_its_shares`.

**`DataRequired` treats a zero amount as missing.** WTForms' `DataRequired` is falsy-based,
so an amount of `0` failed with "this field is required" and `NumberRange` never ran. Both
money fields use `InputRequired` so a zero reaches the range validator and the user sees
"Amount must be positive."

**Two forms on one page need `prefix`.** `/account/` renders a profile form and a password
form. Without `prefix=`, both submit `csrf_token` and clash on any shared field name. The
route decides which one was submitted by checking `form.submit.data`, which is why both
templates render their own submit button with a distinct name.

**A group's creator can leave.** Do not use `created_by_id` for permission checks; it is
nullable and purely historical. Use `group.is_owner(user_id)`, which reads the role on
`group_members`.

**Account deletion is deliberately restrictive.** A user with expense history in a group
that still has other members cannot be deleted, because their shares are part of everyone
else's ledger and removing them would break the sum-to-zero invariant. The alternative,
a tombstone "deleted user" record, is not implemented. Groups where the user is the only
member are deleted along with them.

**The client-side split preview is not validation.** `static/js/app.js` mirrors the equal
and weighted split maths so the numbers update as you type, but the server recomputes and
revalidates everything in `build_shares`. If you change the splitting rules, change
`services/money.py` first; the JS is a convenience and may lag by a cent in edge cases
without affecting what is stored.

**`instance/` is gitignored, including the database.** A fresh clone has no database. Run
`flask db upgrade` before the first start or the app raises `no such table` on the first
query.

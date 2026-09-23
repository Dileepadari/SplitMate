# not_for_you.md

A personal working log. Nothing here is needed to run or contribute to SplitMate;
[README.md](README.md) and [DEVDOC.md](DEVDOC.md) cover that.

---

## The overhaul pass, 2026-09-23

The August rebuild (`34a1485`) had already done the hard part: app factory, typed models,
hashed passwords, a real split engine, 95 tests, ruff clean. So this pass is mostly about
things that were still true underneath a repository that looked finished.

### Seven passwords that are still public

`MyDatabase.db` was committed on 2023-05-06, the day the project started, at both
`MyDatabase.db` and `src/MyDatabase.db`. Fourteen blobs are reachable in history. Thirteen
of them hold user rows and **every password in every one of them is in clear text**, next
to a real first and last name.

Seven distinct accounts. Four of the passwords are four characters long, one has a digit,
none has a symbol, at least one is derived from the holder's own name. Six of the seven are
other people's.

The rebuild untracked the file and moved to `generate_password_hash`, five weeks before
this pass. HEAD is clean. **That does not remove the fourteen blobs**, and nothing in the
repository said they were there. A purge needs a rewrite and a force push, and the six
other people need telling either way, which is not something a commit does.

What this cost me is worth writing down: checking HEAD would have reported the repository
safe. The finding is entirely in history. Third repo in a row where a committed SQLite file
turned out to hold accounts, and text-grep secret scanning cannot see inside one of those.

### Four crashes reachable from an ordinary form field

`decimal.Decimal` accepts `NaN` and `Infinity` as ordinary values and puts no ceiling on
the exponent. None of the three survives contact with the rest of the app, and nothing
screened them out:

| Typed into | Value | What happened |
|---|---|---|
| Amount | `Infinity` | `quantize` raises `InvalidOperation`, uncaught, 500 |
| Amount | `1e999` | same |
| Amount | `1E+999` | same |
| An exact share | `NaN` | `value < ZERO` raises, because ordering against a NaN is an error, 500 |

The amount field survived `NumberRange(min=0.01)` because comparing a `Decimal("NaN")`
against a *float* bound quietly answers False rather than raising. `Infinity` passed
because infinity really is at least 0.01. The exact-share fields have no WTForms validator
at all: they are read straight off `request.form` by `read_split_input`, because how many
of them there are depends on the group.

So a field that looked twice-validated was not validated for this at all. `is_usable_amount`
now says what the requirement actually is, and it is applied in both places: a `UsableAmount`
validator on the two money fields, and a check in `build_shares` before anything is
quantized, so the service is safe even when a caller skips the form.

### The comma that multiplied by a hundred

`to_decimal` did `str(value).strip().replace(",", "")`. So `12,50`, which is how a large
part of the world writes twelve fifty, became **1250.00**. Silently. On a field the user
believed they had filled in correctly.

Worse, the two money fields on one form disagreed: the main Amount field rejected `12,50`
outright as an invalid decimal, and the exact-share field next to it turned it into 1250.
Same text, same form, two different meanings.

A comma only means "thousands separator" in the positions a grouped number puts it, three
digits after each one. `12,50` is not that. Grouped numbers still parse; anything else is
rejected and the user gets a message.

### A CSV export that runs formulas

Descriptions, notes and usernames are typed by group members and written into the export
unescaped. Excel, LibreOffice and Sheets all evaluate a cell that begins `=`, `+`, `-` or
`@`. So one member typing `=HYPERLINK("http://...","click")` as an expense description
attacks whoever opens the file.

Proved it first: put `=1+1` and `@SUM(A1:A9)` in two descriptions, exported, and both came
out raw. `_csv_safe` prefixes an apostrophe now.

The interesting part was the test. I wrote `+1` into the dangerous list and it failed,
because `+1` parses as a number and my exemption lets numbers through. The exemption is
right: escaping every leading sign would turn every refund into text. And `+1` in a cell
evaluates to 1, which is not an attack. The exemption is safe in general because a string
`Decimal` accepts is only digits, a sign, a point and an exponent, and there is no way to
smuggle a call into one. So I corrected the test rather than the code, and said so in its
docstring.

### The date that was in the future in Hyderabad

Every datetime column stores UTC. Both "cannot be in the future" validators compared
against `date.today()`, which is the *server's* local date. Deploy in UTC, sit in UTC+5:30,
open the app at 2am, and the app tells you your own today is in the future. For five and a
half hours a day you cannot record today's expense.

No timezone is more than about fourteen hours from UTC, so one extra day accepts a real
today anywhere and still rejects a date that is genuinely ahead.

### Two em dashes the sweep could not see

`sweep.sh` was clean. The interface drew an em dash anyway, in the PAYMENTS column and in
the sidebar, because they were written as the HTML entity for one. The file is pure ASCII;
the browser draws the character the rule exists to remove.

Same shape as the font ligature in the previous repository, and the same lesson twice in
two days: **look at the rendered page, not only at the grep output.** The sweep script now
checks for the entity forms too, and re-running it over the finished repositories found
four more that have the same thing. Those are recorded rather than fixed, because the rule
is to finish the repository in hand.

I nearly over-reached here. The first version of the check also flagged `&hellip;`, which
is not on the forbidden list at all, and `\x{2014}`, which only means anything to a PCRE
engine so every hit was a grep pattern doing this very sweep, including the hygiene job in
shopflow's own CI. Both removed. A check that cries wolf gets switched off.

### Two real university email addresses in the demo seed

`DEMO_USERS` hardcoded `dileepkumar.adari@students.iiit.ac.in` and
`satuluri.charyulu@students.iiit.ac.in`. The second is not mine. Both would have gone
straight into the settings screenshot in the README of a public repository.

All four are `@example.com` now, which is what RFC 2606 reserves it for.

The About page also prints both addresses as author contacts. I left that alone: it is a
deliberate credits block that the three of us presumably agreed to, and quietly deleting a
teammate's contact line is not mine to do on my own. It is in the report as a question.

### Lint that meant nothing

There was no `[tool.ruff]` section, so `ruff check` meant whatever the installed release
defaulted to. Ruff 0.16 has a far larger default set than whatever was current in August,
which is why a repository described as ruff-clean produced 28 findings the moment I ran it.

Rule set pinned in `pyproject.toml`, version pinned in `requirements-dev.txt`. Generated
Alembic files excluded, because ruff reorders their imports and alembic writes them back
its own way next time, so the diff just returns.

Of the 28, two were worth anything: the `date.today()` pair above, and an unused import.
The rest was quoted annotations and import order.

### Things I checked and did not change

- **`split_by_weights` does not distribute the remainder for a negative total.** The
  `for i in range(cents_left)` loop gets a negative count and does nothing, so the parts do
  not sum back to the total. Unreachable: `build_shares` rejects `amount <= 0` before it.
  `split_equal` handles negatives correctly, which is the inconsistency that made me look.
  Left alone rather than fixed, because fixing an unreachable path invites someone to rely
  on it.
- **Removing a member drops their paid and owed totals from the balance list.** That would
  break the sum-to-zero invariant, except removal already requires a net of exactly zero,
  and a zero net means their paid and owed cancel. It holds. Carefully done.
- **`/login` has no rate limit.** Real, and a deliberate scope choice for a single-instance
  app with no password reset. Written into the security table rather than half-solved.
- **The settle form defaults "Paid to" to the same person as "Paid by"**, so a plain GET
  shows a state the form will reject. A UX wart, one line to fix, but it changes behaviour
  a user might rely on and it is not a correctness bug. Reported instead.

### Capture notes

Seeded a throwaway database in the scratchpad and pointed the app at it with `DATABASE_URL`
on the command line. `instance/splitmate.db` from August is the owner's and was never
touched, never read, never pointed at.

The seeded data is deliberately used rather than real data: the real database would have
put actual names and actual spending into a public README.

The dashboard's group table overflows its card at 390px. Measured it before calling it a
bug, and it is not one: `.table-wrap` is `overflow-x: auto` and the page itself does not
scroll sideways. A deliberate swipeable table. The mobile screenshot shows it mid-scroll,
which is honest about what the app does.

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./docs/assets/adk_dev_logo_light.png">
  <img src="./docs/assets/adk_dev_logo_dark.png" width="150" alt="ADK DEV" loading="lazy">
</picture>

# SplitMate

**Shared expense tracking for groups. SplitMate records who paid for what, splits each cost the way the group actually agreed, and works out the fewest payments that clear everyone.**

<img alt="Python" src="https://img.shields.io/badge/Python_3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" loading="lazy">
<img alt="Flask" src="https://img.shields.io/badge/Flask_3-000000?style=for-the-badge&logo=flask&logoColor=white" loading="lazy">
<img alt="SQLAlchemy" src="https://img.shields.io/badge/SQLAlchemy_2-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" loading="lazy">
<br>
<img alt="SQLite" src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white" loading="lazy">
<img alt="Tests" src="https://img.shields.io/badge/pytest_182_tests-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white" loading="lazy">
<img alt="MIT License" src="https://img.shields.io/badge/License-MIT-3DA639?style=for-the-badge" loading="lazy">

<br><br>

[![CI](https://github.com/Dileepadari/SplitMate/actions/workflows/ci.yml/badge.svg)](https://github.com/Dileepadari/SplitMate/actions/workflows/ci.yml)

**[Developer documentation](./DEVDOC.md)** &middot; [Screenshots](#screenshots) &middot; [Features](#features) &middot; [Getting started](#getting-started)

<p><b>Dark mode</b> &middot; <a href="./README-light.md">View this page in light mode</a></p>

</div>

---

It exists because the arithmetic after a trip is tedious and error prone. Ten expenses
across four people is forty little debts; SplitMate collapses them into at most three
payments and never loses a cent to rounding.

---

## Screenshots

Every image is a real 1440x900 viewport render of the app against the seeded demo data. This page shows **dark mode**; the same gallery in light mode is at **[README-light.md](./README-light.md)**.

<table>
  <tr>
    <td width="33%" valign="top">
      <img src="./docs/screenshots/dark/01-dashboard.png" alt="Dashboard: totals owed and owing, the group list and recent activity" loading="lazy">
      <p align="center"><b>Dashboard</b><br><sub>Every group, what you are owed and what you owe, and recent activity.</sub></p>
    </td>
    <td width="33%" valign="top">
      <img src="./docs/screenshots/dark/02-group.png" alt="Group page: suggested payments above the balance table they came from" loading="lazy">
      <p align="center"><b>Inside a group</b><br><sub>Who owes whom, above the ledger those numbers came from.</sub></p>
    </td>
    <td width="33%" valign="top">
      <img src="./docs/screenshots/dark/03-add-expense.png" alt="Add expense: a weighted share split with live per-person amounts" loading="lazy">
      <p align="center"><b>Adding an expense</b><br><sub>Split by shares: a 2 pays twice what a 1 pays, live as you type.</sub></p>
    </td>
  </tr>
  <tr>
    <td width="33%" valign="top">
      <img src="./docs/screenshots/dark/04-settle-up.png" alt="Settle up: suggested payments and the record-a-payment form" loading="lazy">
      <p align="center"><b>Settling up</b><br><sub>The suggested payments, each one click from being recorded.</sub></p>
    </td>
    <td width="33%" valign="top">
      <img src="./docs/screenshots/dark/05-members.png" alt="Members: roles, join dates, balances and the add-member form" loading="lazy">
      <p align="center"><b>Members</b><br><sub>Roles, join dates and balances. Nobody leaves owing anything.</sub></p>
    </td>
    <td width="33%" valign="top">
      <img src="./docs/screenshots/dark/06-expense.png" alt="Expense detail: the split breakdown and each person's net effect" loading="lazy">
      <p align="center"><b>One expense</b><br><sub>Each person's share and what it did to their balance.</sub></p>
    </td>
  </tr>
</table>

<details>
<summary><b>Settings</b></summary>
<br>
<img src="./docs/screenshots/dark/07-settings.png" alt="Settings with profile, password and preferred currency" loading="lazy">
</details>

## Responsive layout

Above 1080px the forms and the expense page use two columns, so a whole expense fits on one
screen without scrolling. Below that everything stacks: the sidebar collapses behind the menu
button, the summary cards go one per row, and the wider tables scroll sideways inside their own
card rather than squeezing their columns or pushing the page out.

<table>
  <tr>
    <td width="25%" valign="top">
      <img src="./docs/screenshots/responsive/mobile-dashboard.png" alt="Dashboard at 390px wide" loading="lazy">
      <p align="center"><sub><b>Dashboard</b><br>390 x 844</sub></p>
    </td>
    <td width="25%" valign="top">
      <img src="./docs/screenshots/responsive/mobile-group.png" alt="Group page at 390px wide" loading="lazy">
      <p align="center"><sub><b>Inside a group</b><br>390 x 844</sub></p>
    </td>
    <td width="50%" valign="top">
      <img src="./docs/screenshots/responsive/tablet-group.png" alt="Group page at 820px wide" loading="lazy">
      <p align="center"><sub><b>Inside a group</b><br>820 x 1180</sub></p>
    </td>
  </tr>
</table>

---

## Features

### Groups
- Create a group for anything people share costs on: a trip, a flat, a dinner club
- Each group has its own currency, so a Goa trip in INR and a work trip in USD stay separate
- Add members by username or email, and see every member's balance at a glance
- Owners can rename a group, hand ownership to someone else, archive it when it is finished, or delete it outright
- Archived groups drop out of the sidebar and the dashboard totals but keep their history

### Expenses
- Record what it was, how much, who paid, the date, and a category
- **Split equally** between everyone ticked
- **Split by exact amounts** when people ordered different things. The amounts have to add up to the total, and SplitMate says so when they do not
- **Split by shares** when one person had the double room. A share of 2 pays twice what a share of 1 pays
- Leave the payer out of the split when they paid for other people but not themselves
- Edit or delete an expense later. The payer and the group owner can both delete one
- Search by description, note or payer, and filter by category

### Balances and settling up
- Every member has one number per group: what they paid, minus what they used, minus anything already repaid
- The **who owes whom** table turns those numbers into a concrete list of payments, one line per payment
- Record a real payment when money changes hands, and the balances move immediately
- Undo a payment that was recorded by mistake
- A member cannot be removed, and cannot leave, while their balance is not zero, so no debt disappears with them

### Your account
- Change your name, email, avatar and preferred currency
- Change your password
- Light and dark themes, remembered per account
- Delete your account once every balance is zero and you have left any group where you have expense history

### Data
- Export any group to CSV with its expenses, per-person shares and recorded payments
- Everything is stored locally in SQLite by default

## Roles

| Role | Can do |
|---|---|
| **Owner** | Everything a member can, plus rename, archive and delete the group, add and remove members, promote another owner, and delete anyone's expense |
| **Member** | Add, edit and delete their own expenses, record and undo payments, add members, leave the group when settled |

Whoever creates a group is its first owner. A group can have several owners.

## How a group settles

1. **Open.** Members add expenses. Each expense stores who paid and one share row per participant.
2. **Owing.** Each member's net balance is `paid - their share + payments they made - payments they received`. Nets always sum to zero.
3. **Settling.** SplitMate matches the largest debtor against the largest creditor until nothing is left. Four people need at most three payments, not one per expense.
4. **Settled.** Every net is zero. Members can now leave, or the group can be archived.

## Tech stack

Flask with server-rendered Jinja templates, SQLAlchemy over SQLite, and a hand-written
stylesheet. No Node toolchain and no build step. Details in [DEVDOC.md](./DEVDOC.md).

## Getting started

See [DEVDOC.md - Local development](./DEVDOC.md#local-development). The short version:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask db upgrade
flask seed-demo      # optional: four users, two groups, sample expenses
python wsgi.py
```

Then open http://127.0.0.1:5000. If you seeded, sign in as `dileep` with `splitmate123`.

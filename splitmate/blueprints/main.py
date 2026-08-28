"""Dashboard, about page and health check."""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..services.activity import user_activity
from ..services.balances import summaries_for, totals_for

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("landing.html")


@bp.route("/dashboard")
@login_required
def dashboard():
    summaries = summaries_for(current_user)
    archived = [s for s in summaries_for(current_user, include_archived=True) if s.group.archived]
    return render_template(
        "dashboard.html",
        summaries=summaries,
        archived=archived,
        totals=totals_for(summaries),
        activity=user_activity(current_user, limit=12),
    )


@bp.route("/about")
def about():
    """Signed-in visitors get the app shell around it; everyone else gets a public page."""
    template = "about.html" if current_user.is_authenticated else "about_public.html"
    return render_template(template)


@bp.route("/healthz")
def healthz():
    return {"status": "ok"}

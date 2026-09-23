"""SplitMate application factory."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template

from .config import INSTANCE_DIR, get_config
from .extensions import csrf, db, login_manager, migrate

__version__ = "2.0.0"

load_dotenv()


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name)())

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///"):
        Path(INSTANCE_DIR).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(app.root_path).parent / "migrations"))
    csrf.init_app(app)
    login_manager.init_app(app)

    _register_loaders()
    _register_blueprints(app)
    _register_filters(app)
    _register_context(app)
    _register_errors(app)
    _register_cli(app)

    return app


def _register_loaders() -> None:
    from .models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))


def _register_blueprints(app: Flask) -> None:
    from .blueprints.account import bp as account_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.expenses import bp as expenses_bp
    from .blueprints.groups import bp as groups_bp
    from .blueprints.main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(account_bp)


def _register_filters(app: Flask) -> None:
    from .forms import CATEGORY_ICONS
    from .services.money import format_money, symbol_for

    @app.template_filter("money")
    def money_filter(value, currency: str = "INR") -> str:
        return format_money(value, currency)

    @app.template_filter("abs_money")
    def abs_money_filter(value, currency: str = "INR") -> str:
        return format_money(abs(value) if value is not None else 0, currency)

    @app.template_filter("symbol")
    def symbol_filter(currency: str) -> str:
        return symbol_for(currency)

    @app.template_filter("category_icon")
    def category_icon_filter(category: str) -> str:
        return CATEGORY_ICONS.get(category, "receipt")

    @app.template_filter("day")
    def day_filter(value) -> str:
        return value.strftime("%d %b %Y") if value else ""


def _register_context(app: Flask) -> None:
    from flask_login import current_user

    from .forms import ConfirmForm
    from .services.balances import summaries_for, totals_for

    @app.context_processor
    def inject_globals():
        summaries = summaries_for(current_user) if current_user.is_authenticated else []
        return {
            "app_name": "SplitMate",
            "app_version": __version__,
            "sidebar_groups": summaries,
            "sidebar_totals": totals_for(summaries),
            "user_currency": (
                current_user.currency if current_user.is_authenticated else app.config["DEFAULT_CURRENCY"]
            ),
            "confirm_form": ConfirmForm(),
        }


def _register_errors(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/error.html", code=403,
                               title="Not your group",
                               message="You do not have access to that page."), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/error.html", code=404,
                               title="Nothing here",
                               message="That page does not exist."), 404

    @app.errorhandler(413)
    def too_large(error):
        return render_template("errors/error.html", code=413,
                               title="Too large",
                               message="That upload is bigger than the limit."), 413

    @app.errorhandler(500)
    def server_error(error):  # pragma: no cover - exercised only on real failures
        db.session.rollback()
        return render_template("errors/error.html", code=500,
                               title="Something broke",
                               message="An unexpected error occurred and has been logged."), 500


def _register_cli(app: Flask) -> None:
    from .cli import register_cli

    register_cli(app)

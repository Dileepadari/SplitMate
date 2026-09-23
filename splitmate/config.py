"""Configuration objects, selected by the ``SPLITMATE_CONFIG`` environment variable."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import ClassVar

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class BaseConfig:
    """Settings shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'splitmate.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS: ClassVar[dict] = {"pool_pre_ping": True}

    # Session and CSRF
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = None

    # App behaviour
    DEFAULT_CURRENCY = os.environ.get("DEFAULT_CURRENCY", "INR")
    ITEMS_PER_PAGE = int(os.environ.get("ITEMS_PER_PAGE", "20"))
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "testing"


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", True)

    def __init__(self) -> None:
        if self.SECRET_KEY == "dev-only-change-me":
            raise RuntimeError("SECRET_KEY must be set to a real value in production")


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    """Return the config class for ``name``, falling back to the env var then development."""
    key = (name or os.environ.get("SPLITMATE_CONFIG") or "development").lower()
    return CONFIGS.get(key, DevelopmentConfig)

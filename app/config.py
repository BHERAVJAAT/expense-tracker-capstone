"""Environment-based configuration for the Expense Tracker API."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"

# Load variables from .env (if present). Real environment variables win.
load_dotenv(BASE_DIR / ".env")


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_uri():
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        # Some hosts still hand out the legacy "postgres://" scheme.
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    # Absolute path -> works the same on Windows, macOS, Linux and Render.
    return "sqlite:///" + (INSTANCE_DIR / "expenses.db").as_posix()


class Config:
    """Base configuration shared by all environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # reject request bodies over 1 MB

    DEBUG = False
    TESTING = False

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOG_DIR = os.environ.get("LOG_DIR", str(BASE_DIR / "logs"))
    LOG_FILE = os.environ.get("LOG_FILE", "app.log")
    LOG_TO_FILE = _env_bool("LOG_TO_FILE", True)


class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG").upper()


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    LOG_TO_FILE = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
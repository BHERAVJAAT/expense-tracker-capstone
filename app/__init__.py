"""Application factory for the Personal Expense Tracker & Analytics API."""
import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import OperationalError
from werkzeug.exceptions import HTTPException

from app.config import INSTANCE_DIR, config_by_name
from app.logger import logger, register_request_logging, setup_logging

db = SQLAlchemy()


def create_app(config_name=None):
    """Create and configure the Flask application."""
    env = (config_name or os.environ.get("APP_ENV") or "production").strip().lower()
    if env not in config_by_name:
        valid = ", ".join(sorted(config_by_name))
        raise ValueError(f"Unknown APP_ENV '{env}'. Valid options: {valid}")

    app = Flask(__name__, instance_path=str(INSTANCE_DIR))
    app.config.from_object(config_by_name[env])
    app.json.sort_keys = False  # keep JSON keys in the order we define them

    os.makedirs(app.instance_path, exist_ok=True)

    setup_logging(app)
    register_request_logging(app)
    db.init_app(app)

    from app.routes import api_bp

    app.register_blueprint(api_bp)
    register_error_handlers(app)
    init_database(app)

    if env == "production" and app.config["SECRET_KEY"] == "change-me-in-production":
        logger.warning("SECRET_KEY is using the default value. Set a real one in production.")

    logger.info("Application started (env=%s)", env)
    return app


def init_database(app):
    """Create tables on startup (safe to run repeatedly)."""
    from app import models  # noqa: F401  (importing registers the tables)

    with app.app_context():
        try:
            db.create_all()
        except OperationalError as exc:
            # Another worker may have created the tables a moment earlier.
            db.session.rollback()
            if "already exists" in str(exc).lower():
                logger.warning("Tables already exist, continuing: %s", exc)
            else:
                logger.exception("Database initialisation failed")
                raise
        logger.info("Database ready (dialect=%s)", db.engine.dialect.name)


def register_error_handlers(app):
    """Return every error as {"error": "...", "status": <code>}."""
    from app.routes import ApiError, error_response

    @app.errorhandler(ApiError)
    def handle_api_error(err):
        if err.status_code >= 500:
            logger.error("API error %s: %s", err.status_code, err.message)
        else:
            logger.warning("API error %s: %s", err.status_code, err.message)
        return error_response(err.message, err.status_code)

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        logger.warning("HTTP error %s: %s", err.code, err.name)
        message = {
            404: "The requested URL was not found on this server",
            405: "Method not allowed for this URL",
            413: "Request body is too large (max 1 MB)",
        }.get(err.code, err.description or err.name)
        return error_response(message, err.code or 500)

    @app.errorhandler(Exception)
    def handle_unexpected_error(err):
        db.session.rollback()
        logger.exception("Unhandled exception: %s", err)
        return error_response("Internal server error", 500)
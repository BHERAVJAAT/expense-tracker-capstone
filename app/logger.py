"""Central logging setup: console + rotating log file + request logging."""
import logging
import os
import time
from logging.handlers import RotatingFileHandler

from flask import g, request

LOGGER_NAME = "expense_tracker"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Module-level logger used across the whole project:
#   from app.logger import logger
logger = logging.getLogger(LOGGER_NAME)


def setup_logging(app):
    """Attach a console handler and (optionally) a rotating file handler."""
    level_name = str(app.config.get("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    # Avoid duplicate handlers if create_app() is called more than once.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if app.config.get("LOG_TO_FILE", True):
        log_dir = app.config.get("LOG_DIR", "logs")
        log_path = os.path.join(log_dir, app.config.get("LOG_FILE", "app.log"))
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            file_handler = RotatingFileHandler(
                log_path, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as exc:
            logger.warning("File logging disabled (%s). Using console only.", exc)

    logger.info("Logging initialised (level=%s)", logging.getLevelName(level))


def register_request_logging(app):
    """Log every API request with method, path, status code and duration."""

    @app.before_request
    def _start_timer():
        g.request_started_at = time.perf_counter()

    @app.after_request
    def _log_request(response):
        started = g.get("request_started_at")
        duration_ms = (time.perf_counter() - started) * 1000 if started else 0.0
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        logger.info(
            "%s %s -> %s (%.1f ms) ip=%s",
            request.method,
            request.full_path.rstrip("?"),
            response.status_code,
            duration_ms,
            client_ip,
        )
        return response
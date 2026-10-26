"""All REST API endpoints, request validation helpers and the ApiError type."""
import datetime as dt
import math
import re

from flask import Blueprint, jsonify, request
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import db
from app.logger import logger
from app.models import Category, Expense

api_bp = Blueprint("api", __name__)

CATEGORY_TYPES = ("income", "expense")
CATEGORY_FIELDS = {"name", "type"}
EXPENSE_FIELDS = {"title", "amount", "category_id", "date", "notes"}

MAX_AMOUNT = 1_000_000_000
MAX_DB_INTEGER = 2**63 - 1
MIN_DATE = dt.date(1900, 1, 1)
MAX_DATE = dt.date(2100, 12, 31)
MAX_PAGE = 1_000_000
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
class ApiError(Exception):
    """Raised anywhere in a route to return a uniform JSON error."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def error_response(message, status_code):
    return jsonify({"error": message, "status": status_code}), status_code


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def get_json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(
            "Request body must be a valid JSON object (send Content-Type: application/json)",
            400,
        )
    return data


def commit_session():
    """Commit with rollback + clean errors so the DB is never left half-written."""
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        logger.warning("Integrity error: %s", exc.orig)
        raise ApiError("Database constraint violated (duplicate or invalid reference)", 409)
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error("Database error: %s", exc, exc_info=True)
        raise ApiError("A database error occurred", 500)


def parse_date_value(value, field):
    """Strict YYYY-MM-DD parser. Raises ValueError with a friendly message."""
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a date in YYYY-MM-DD format")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} is not a valid calendar date")
    if not MIN_DATE <= parsed <= MAX_DATE:
        raise ValueError(f"{field} must be between {MIN_DATE} and {MAX_DATE}")
    return parsed


def parse_query_date(name):
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return parse_date_value(raw.strip(), name)
    except ValueError as exc:
        raise ApiError(str(exc), 400)


def parse_date_range():
    start = parse_query_date("start_date")
    end = parse_query_date("end_date")
    if start and end and start > end:
        raise ApiError("start_date must be on or before end_date", 400)
    return start, end


def parse_int_arg(name, default, minimum, maximum):
    raw = request.args.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(f"{name} must be an integer", 400)
    if not minimum <= value <= maximum:
        raise ApiError(f"{name} must be between {minimum} and {maximum}", 400)
    return value


def validate_category_payload(data):
    errors, clean = [], {}

    unknown = set(data) - CATEGORY_FIELDS
    if unknown:
        errors.append("Unknown field(s): " + ", ".join(sorted(unknown)))

    if "name" not in data:
        errors.append("name is required")
    else:
        name = data["name"]
        if not isinstance(name, str) or not name.strip():
            errors.append("name must be a non-empty string")
        elif len(name.strip()) > 50:
            errors.append("name must be at most 50 characters")
        else:
            clean["name"] = name.strip()

    category_type = data.get("type", "expense")
    if not isinstance(category_type, str) or category_type.strip().lower() not in CATEGORY_TYPES:
        errors.append("type must be one of: income, expense")
    else:
        clean["type"] = category_type.strip().lower()

    return clean, errors


def validate_expense_payload(data, partial=False):
    """Validate a create (partial=False) or update (partial=True) payload."""
    errors, clean = [], {}

    unknown = set(data) - EXPENSE_FIELDS
    if unknown:
        errors.append("Unknown field(s): " + ", ".join(sorted(unknown)))

    if partial:
        if not data:
            errors.append("Provide at least one field to update")
    else:
        for field in ("title", "amount", "category_id"):
            if field not in data:
                errors.append(f"{field} is required")

    if "title" in data:
        title = data["title"]
        if not isinstance(title, str) or not title.strip():
            errors.append("title must be a non-empty string")
        elif len(title.strip()) > 100:
            errors.append("title must be at most 100 characters")
        else:
            clean["title"] = title.strip()

    if "amount" in data:
        amount = data["amount"]
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            errors.append("amount must be a number")
        elif isinstance(amount, float) and not math.isfinite(amount):
            errors.append("amount must be a finite number")
        elif amount < 0:
            errors.append("amount must not be negative")
        elif amount > MAX_AMOUNT:
            errors.append(f"amount must not exceed {MAX_AMOUNT}")
        else:
            clean["amount"] = round(float(amount), 2)

    if "category_id" in data:
        category_id = data["category_id"]
        if (
            isinstance(category_id, bool)
            or not isinstance(category_id, int)
            or not 1 <= category_id <= MAX_DB_INTEGER
        ):
            errors.append("category_id must be a positive integer")
        elif db.session.get(Category, category_id) is None:
            errors.append(f"category_id {category_id} does not exist")
        else:
            clean["category_id"] = category_id

    if "date" in data:
        try:
            clean["date"] = parse_date_value(data["date"], "date")
        except ValueError as exc:
            errors.append(str(exc))
    elif not partial:
        clean["date"] = dt.date.today()

    if "notes" in data:
        notes = data["notes"]
        if notes is None:
            clean["notes"] = None
        elif not isinstance(notes, str):
            errors.append("notes must be a string or null")
        elif len(notes) > 500:
            errors.append("notes must be at most 500 characters")
        else:
            clean["notes"] = notes.strip() or None

    return clean, errors


def get_expense_or_404(expense_id):
    expense = None
    if 1 <= expense_id <= MAX_DB_INTEGER:
        expense = db.session.get(Expense, expense_id)
    if expense is None:
        raise ApiError(f"Expense with id {expense_id} not found", 404)
    return expense


# --------------------------------------------------------------------------
# System endpoints
# --------------------------------------------------------------------------
@api_bp.route("/", methods=["GET"])
def index():
    return jsonify(
        {
            "service": "Personal Expense Tracker & Analytics API",
            "health": "/health",
            "endpoints": [
                "POST /api/categories",
                "GET /api/categories",
                "POST /api/expenses",
                "GET /api/expenses",
                "GET /api/expenses/<id>",
                "PUT /api/expenses/<id>",
                "DELETE /api/expenses/<id>",
                "GET /api/expenses/summary",
            ],
        }
    ), 200


@api_bp.route("/health", methods=["GET"])
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("Health check failed: %s", exc)
        raise ApiError("Database connection failed", 500)
    return jsonify(
        {
            "status": "ok",
            "database": "connected",
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
    ), 200


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------
@api_bp.route("/api/categories", methods=["POST"])
def create_category():
    data = get_json_body()
    clean, errors = validate_category_payload(data)
    if errors:
        raise ApiError("; ".join(errors), 400)

    existing = Category.query.filter(func.lower(Category.name) == clean["name"].lower()).first()
    if existing:
        raise ApiError(f"Category '{existing.name}' already exists", 409)

    category = Category(**clean)
    db.session.add(category)
    commit_session()
    logger.info("Created category id=%s name=%s type=%s", category.id, category.name, category.type)
    return jsonify(category.to_dict()), 201


@api_bp.route("/api/categories", methods=["GET"])
def list_categories():
    query = Category.query
    type_filter = request.args.get("type", "").strip().lower()
    if type_filter:
        if type_filter not in CATEGORY_TYPES:
            raise ApiError("type must be one of: income, expense", 400)
        query = query.filter(Category.type == type_filter)
    categories = query.order_by(Category.name).all()
    return jsonify(
        {"count": len(categories), "categories": [c.to_dict() for c in categories]}
    ), 200


# --------------------------------------------------------------------------
# Expenses
# --------------------------------------------------------------------------
@api_bp.route("/api/expenses", methods=["POST"])
def create_expense():
    data = get_json_body()
    clean, errors = validate_expense_payload(data)
    if errors:
        raise ApiError("; ".join(errors), 400)

    expense = Expense(**clean)
    db.session.add(expense)
    commit_session()
    logger.info("Created expense id=%s amount=%s", expense.id, expense.amount)
    return jsonify(expense.to_dict()), 201


@api_bp.route("/api/expenses", methods=["GET"])
def list_expenses():
    start_date, end_date = parse_date_range()
    page = parse_int_arg("page", 1, 1, MAX_PAGE)
    per_page = parse_int_arg("per_page", 20, 1, 100)

    query = Expense.query.join(Category, Expense.category_id == Category.id)

    category_name = request.args.get("category", "").strip()
    if category_name:
        query = query.filter(func.lower(Category.name) == category_name.lower())
    if start_date:
        query = query.filter(Expense.date >= start_date)
    if end_date:
        query = query.filter(Expense.date <= end_date)

    total = query.count()
    expenses = (
        query.order_by(Expense.date.desc(), Expense.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return jsonify(
        {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": math.ceil(total / per_page) if total else 0,
            "count": len(expenses),
            "expenses": [e.to_dict() for e in expenses],
        }
    ), 200


@api_bp.route("/api/expenses/summary", methods=["GET"])
def expense_summary():
    start_date, end_date = parse_date_range()

    query = (
        db.session.query(
            Expense.date, Expense.amount, Category.id, Category.name, Category.type
        )
        .select_from(Expense)
        .join(Category, Expense.category_id == Category.id)
    )
    if start_date:
        query = query.filter(Expense.date >= start_date)
    if end_date:
        query = query.filter(Expense.date <= end_date)

    totals = {"expense": 0.0, "income": 0.0}
    by_category = {}
    by_month = {}

    for exp_date, amount, cat_id, cat_name, cat_type in query.all():
        amount = float(amount)
        totals[cat_type] = totals.get(cat_type, 0.0) + amount

        entry = by_category.setdefault(
            cat_id, {"category": cat_name, "type": cat_type, "total": 0.0, "count": 0}
        )
        entry["total"] += amount
        entry["count"] += 1

        month_key = f"{exp_date.year:04d}-{exp_date.month:02d}"
        month = by_month.setdefault(
            month_key, {"month": month_key, "spent": 0.0, "income": 0.0, "count": 0}
        )
        month["spent" if cat_type == "expense" else "income"] += amount
        month["count"] += 1

    category_breakdown = []
    for entry in sorted(by_category.values(), key=lambda e: e["total"], reverse=True):
        type_total = totals.get(entry["type"], 0.0)
        percentage = round(entry["total"] / type_total * 100, 2) if type_total else 0.0
        category_breakdown.append(
            {
                "category": entry["category"],
                "type": entry["type"],
                "total": round(entry["total"], 2),
                "count": entry["count"],
                "percentage": percentage,
            }
        )

    monthly_summary = [
        {
            "month": m["month"],
            "spent": round(m["spent"], 2),
            "income": round(m["income"], 2),
            "net": round(m["income"] - m["spent"], 2),
            "count": m["count"],
        }
        for m in sorted(by_month.values(), key=lambda m: m["month"])
    ]

    return jsonify(
        {
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
            },
            "total_spent": round(totals["expense"], 2),
            "total_income": round(totals["income"], 2),
            "net_balance": round(totals["income"] - totals["expense"], 2),
            "transaction_count": sum(e["count"] for e in by_category.values()),
            "by_category": category_breakdown,
            "monthly_summary": monthly_summary,
        }
    ), 200


@api_bp.route("/api/expenses/<int:expense_id>", methods=["GET"])
def get_expense(expense_id):
    return jsonify(get_expense_or_404(expense_id).to_dict()), 200


@api_bp.route("/api/expenses/<int:expense_id>", methods=["PUT"])
def update_expense(expense_id):
    expense = get_expense_or_404(expense_id)
    data = get_json_body()
    clean, errors = validate_expense_payload(data, partial=True)
    if errors:
        raise ApiError("; ".join(errors), 400)

    for field, value in clean.items():
        setattr(expense, field, value)
    commit_session()
    logger.info("Updated expense id=%s fields=%s", expense.id, sorted(clean))
    return jsonify(expense.to_dict()), 200


@api_bp.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    expense = get_expense_or_404(expense_id)
    db.session.delete(expense)
    commit_session()
    logger.info("Deleted expense id=%s", expense_id)
    return jsonify({"message": "Expense deleted successfully", "id": expense_id}), 200
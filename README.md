# Personal Expense Tracker & Analytics API

A modular REST API built with **Flask**, **Flask-SQLAlchemy** and **SQLite**. Track income and expenses, filter them, and get analytics (totals, category breakdown, monthly summary).

## Features
- Application Factory pattern, modular structure
- SQLite via Flask-SQLAlchemy (`Category`, `Expense` models)
- Strict JSON validation (types, required fields, non-negative amounts, `YYYY-MM-DD` dates)
- Uniform error format: `{"error": "message", "status": 400}`
- Logging to console and `logs/app.log` (requests, errors, system events)
- Filtering + pagination, analytics summary
- Ready for Render (gunicorn)

## Project structure
```
expense-tracker-capstone/
├── app/
│   ├── __init__.py   # app factory, DB init, error handlers
│   ├── config.py     # environment configuration
│   ├── models.py     # SQLAlchemy models
│   ├── routes.py     # all endpoints + validation
│   └── logger.py     # logging setup
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
└── README.md
```

## Setup (local)
```bash
python -m venv venv
# Windows:  venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
python run.py
```
Server: http://127.0.0.1:5000 — check http://127.0.0.1:5000/health

## Environment variables
| Variable | Default | Purpose |
|---|---|---|
| APP_ENV | production | development / production / testing |
| SECRET_KEY | change-me-in-production | Flask secret key |
| DATABASE_URL | sqlite file in `instance/` | Database connection string |
| LOG_LEVEL | INFO | DEBUG / INFO / WARNING / ERROR |
| LOG_TO_FILE | true | Write logs to `logs/app.log` |
| HOST / PORT | 127.0.0.1 / 5000 | Local dev server only |

## Endpoints
| Method | Path | Description |
|---|---|---|
| GET | /health | Health check |
| POST | /api/categories | Create category |
| GET | /api/categories | List categories (`?type=income\|expense`) |
| POST | /api/expenses | Add expense |
| GET | /api/expenses | List expenses |
| GET | /api/expenses/<id> | Get one expense |
| PUT | /api/expenses/<id> | Update expense (send any subset of fields) |
| DELETE | /api/expenses/<id> | Delete expense |
| GET | /api/expenses/summary | Totals, category breakdown, monthly summary |

**List filters:** `category` (name), `start_date`, `end_date` (YYYY-MM-DD), `page`, `per_page` (max 100).
**Summary filters:** `start_date`, `end_date`.

## Example payloads and curl (Mac/Linux/Git Bash)
Create category:
```bash
curl -X POST http://127.0.0.1:5000/api/categories \
  -H "Content-Type: application/json" \
  -d '{"name": "Food", "type": "expense"}'
```
Create expense:
```bash
curl -X POST http://127.0.0.1:5000/api/expenses \
  -H "Content-Type: application/json" \
  -d '{"title": "Lunch", "amount": 12.5, "category_id": 1, "date": "2026-10-20", "notes": "Office canteen"}'
```
List with filters:
```bash
curl "http://127.0.0.1:5000/api/expenses?category=Food&start_date=2026-10-01&end_date=2026-10-31"
```
Update:
```bash
curl -X PUT http://127.0.0.1:5000/api/expenses/1 \
  -H "Content-Type: application/json" \
  -d '{"amount": 15, "notes": "Updated"}'
```
Delete / Summary:
```bash
curl -X DELETE http://127.0.0.1:5000/api/expenses/1
curl http://127.0.0.1:5000/api/expenses/summary
```
On Windows, use Thunder Client or Postman and paste the JSON bodies above.

## Response examples
Error (all errors use this shape):
```json
{"error": "amount must not be negative", "status": 400}
```
Summary:
```json
{
  "period": {"start_date": null, "end_date": null},
  "total_spent": 27.5,
  "total_income": 1000.0,
  "net_balance": 972.5,
  "transaction_count": 3,
  "by_category": [
    {"category": "Food", "type": "expense", "total": 27.5, "count": 2, "percentage": 100.0}
  ],
  "monthly_summary": [
    {"month": "2026-10", "spent": 27.5, "income": 1000.0, "net": 972.5, "count": 3}
  ]
}
```

## Database schema
**categories**
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| name | VARCHAR(50) | NOT NULL, UNIQUE |
| type | VARCHAR(10) | NOT NULL, `income` or `expense` |

**expenses**
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| title | VARCHAR(100) | NOT NULL |
| amount | FLOAT | NOT NULL, >= 0 |
| category_id | INTEGER | FK -> categories.id, NOT NULL |
| date | DATE | NOT NULL, default today |
| notes | VARCHAR(500) | nullable |
| created_at | DATETIME | NOT NULL, UTC |

## Deploy on Render
1. Push the project to GitHub.
2. Render -> New -> Web Service -> connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn run:app --bind 0.0.0.0:$PORT`
5. Environment: `APP_ENV=production`, `SECRET_KEY=<random string>`, `PYTHON_VERSION=3.12.3`
6. Health check path: `/health`

Note: on Render's free plan the disk is ephemeral, so the SQLite file resets on redeploy. For permanent data use a persistent disk, or a PostgreSQL `DATABASE_URL` (add `psycopg2-binary` to requirements.txt).
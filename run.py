"""Entry point.

Development : python run.py
Production  : gunicorn run:app --bind 0.0.0.0:$PORT
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=app.config["DEBUG"],
    )
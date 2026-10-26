"""SQLAlchemy database models."""
import datetime as dt

from app import db


def _utc_now():
    return dt.datetime.now(dt.timezone.utc)


class Category(db.Model):
    __tablename__ = "categories"
    __table_args__ = (
        db.CheckConstraint("type IN ('income', 'expense')", name="ck_categories_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    type = db.Column(db.String(10), nullable=False, default="expense")

    expenses = db.relationship("Expense", backref="category", lazy=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "type": self.type}

    def __repr__(self):
        return f"<Category {self.id} {self.name} ({self.type})>"


class Expense(db.Model):
    __tablename__ = "expenses"
    __table_args__ = (
        db.CheckConstraint("amount >= 0", name="ck_expenses_amount_non_negative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True
    )
    date = db.Column(db.Date, nullable=False, default=dt.date.today, index=True)
    notes = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "amount": round(float(self.amount), 2),
            "category_id": self.category_id,
            "category": self.category.name if self.category else None,
            "category_type": self.category.type if self.category else None,
            "date": self.date.isoformat() if self.date else None,
            "notes": self.notes,
            "created_at": (
                self.created_at.isoformat(timespec="seconds") if self.created_at else None
            ),
        }

    def __repr__(self):
        return f"<Expense {self.id} {self.title} {self.amount}>"
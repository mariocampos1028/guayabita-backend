"""Lightweight schema patches for columns added after initial deploy."""

from sqlalchemy import text

from app.db.database import engine


def run_startup_migrations() -> None:
    """Apply idempotent ALTER TABLE statements for existing databases."""
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ",
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))

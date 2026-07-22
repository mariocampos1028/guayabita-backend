"""Lightweight schema patches for columns added after initial deploy."""

import os

from sqlalchemy import text

from app.db.database import engine


def run_startup_migrations() -> None:
    """Apply idempotent ALTER TABLE statements for existing databases."""
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(80) NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR(80) NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(30) NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS address VARCHAR(255) NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date DATE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500)",
        "UPDATE users SET avatar_url = '/images/avatar-default.png' WHERE avatar_url IS NULL",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS tournament_balance DOUBLE PRECISION NOT NULL DEFAULT 0",
        "ALTER TABLE game_history ADD COLUMN IF NOT EXISTS audit_log TEXT",
        """
        CREATE TABLE IF NOT EXISTS tournaments (
            id SERIAL PRIMARY KEY,
            title VARCHAR(120) NOT NULL DEFAULT 'Premio del torneo',
            description TEXT NOT NULL DEFAULT '',
            image_url VARCHAR(500),
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ends_at TIMESTAMPTZ,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            winner_user_id INTEGER REFERENCES users(id),
            winner_username VARCHAR(50),
            winner_avatar_url VARCHAR(500),
            winner_balance DOUBLE PRECISION,
            winner_prize_title VARCHAR(120),
            created_by_id INTEGER REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS recharge_packages (
            id SERIAL PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            price DOUBLE PRECISION NOT NULL,
            guayabits DOUBLE PRECISION NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            popular BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by_id INTEGER REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS recharge_purchases (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            package_id INTEGER REFERENCES recharge_packages(id),
            package_name VARCHAR(120) NOT NULL,
            price DOUBLE PRECISION NOT NULL,
            guayabits DOUBLE PRECISION NOT NULL,
            reference VARCHAR(64) NOT NULL UNIQUE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            wompi_transaction_id VARCHAR(80),
            wompi_status VARCHAR(30),
            wompi_payment_method VARCHAR(40),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))

        admin_username = os.getenv("INITIAL_ADMIN_USERNAME", "").strip()
        if admin_username:
            conn.execute(
                text("UPDATE users SET is_admin = TRUE WHERE username = :username"),
                {"username": admin_username},
            )

"""Lightweight schema patches for columns added after initial deploy."""

import os

from sqlalchemy import text

from app.db.database import engine


def run_startup_migrations() -> None:
    """Apply idempotent ALTER TABLE statements for existing databases."""
    statements = [
        # ── Tablas base (antes creadas por Base.metadata.create_all) ─────────────
        # Deben ir primero: las sentencias ALTER TABLE siguientes asumen que
        # 'users' y 'game_history' ya existen en una base de datos nueva.
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            email VARCHAR(120) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            first_name VARCHAR(80) NOT NULL DEFAULT '',
            last_name VARCHAR(80) NOT NULL DEFAULT '',
            phone VARCHAR(30) NOT NULL DEFAULT '',
            address VARCHAR(255) NOT NULL DEFAULT '',
            birth_date DATE,
            avatar_url VARCHAR(500),
            id_document VARCHAR(20),
            is_admin BOOLEAN NOT NULL DEFAULT FALSE,
            balance DOUBLE PRECISION NOT NULL DEFAULT 5000,
            tournament_balance DOUBLE PRECISION NOT NULL DEFAULT 0,
            email_verified BOOLEAN NOT NULL DEFAULT FALSE,
            email_verified_at TIMESTAMPTZ,
            last_login_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            referral_link_generations INTEGER NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS game_history (
            id SERIAL PRIMARY KEY,
            room_code VARCHAR(10) NOT NULL,
            winner_id INTEGER REFERENCES users(id),
            players_json TEXT NOT NULL,
            audit_log TEXT,
            finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_game_history_room_code ON game_history(room_code)",
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
        """
        UPDATE recharge_purchases
        SET reference = 'GUA-' || id::text || '-FIXED'
        WHERE reference = 'pending'
        """,
        """
        CREATE TABLE IF NOT EXISTS store_products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(160) NOT NULL,
            category VARCHAR(80) NOT NULL,
            short_description VARCHAR(300) NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            price DOUBLE PRECISION NOT NULL,
            guayabits_reward DOUBLE PRECISION NOT NULL DEFAULT 0,
            allow_cash_on_delivery BOOLEAN NOT NULL DEFAULT TRUE,
            allow_direct_payment BOOLEAN NOT NULL DEFAULT TRUE,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by_id INTEGER REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS store_product_media (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES store_products(id) ON DELETE CASCADE,
            media_type VARCHAR(10) NOT NULL,
            object_key VARCHAR(500) NOT NULL UNIQUE,
            url VARCHAR(700) NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS store_payment_methods (
            id SERIAL PRIMARY KEY,
            method_type VARCHAR(20) NOT NULL,
            display_name VARCHAR(80) NOT NULL,
            owner_name VARCHAR(160) NOT NULL,
            identifier VARCHAR(160) NOT NULL,
            instructions TEXT NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by_id INTEGER REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS store_orders (
            id SERIAL PRIMARY KEY,
            reference VARCHAR(64) NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            product_id INTEGER REFERENCES store_products(id),
            product_name VARCHAR(160) NOT NULL,
            product_price DOUBLE PRECISION NOT NULL,
            guayabits_reward DOUBLE PRECISION NOT NULL DEFAULT 0,
            quantity INTEGER NOT NULL DEFAULT 1,
            customer_first_name VARCHAR(80) NOT NULL,
            customer_last_name VARCHAR(80) NOT NULL,
            customer_email VARCHAR(120) NOT NULL,
            customer_phone VARCHAR(30) NOT NULL,
            shipping_address VARCHAR(255) NOT NULL,
            department VARCHAR(80) NOT NULL,
            city VARCHAR(100) NOT NULL,
            reference_point VARCHAR(300),
            customer_notes TEXT,
            payment_type VARCHAR(30) NOT NULL,
            payment_method_id INTEGER REFERENCES store_payment_methods(id),
            payment_method_name VARCHAR(80),
            payment_receipt_key VARCHAR(500),
            payment_receipt_url VARCHAR(700),
            status VARCHAR(30) NOT NULL DEFAULT 'en_proceso',
            admin_observations TEXT,
            guayabits_credited BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_store_products_status ON store_products(status)",
        "CREATE INDEX IF NOT EXISTS ix_store_orders_user_id ON store_orders(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_store_orders_status ON store_orders(status)",
        """
        CREATE TABLE IF NOT EXISTS support_tickets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            category VARCHAR(20) NOT NULL,
            title VARCHAR(160) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'open',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS support_messages (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
            sender_id INTEGER NOT NULL REFERENCES users(id),
            sender_role VARCHAR(10) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_user_id ON support_tickets(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_status ON support_tickets(status)",
        "CREATE INDEX IF NOT EXISTS ix_support_messages_ticket_id ON support_messages(ticket_id)",
        """
        CREATE TABLE IF NOT EXISTS balance_adjustment_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            admin_id INTEGER NOT NULL REFERENCES users(id),
            previous_balance DOUBLE PRECISION NOT NULL,
            new_balance DOUBLE PRECISION NOT NULL,
            delta DOUBLE PRECISION NOT NULL,
            justification TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_balance_adjustment_logs_user_id ON balance_adjustment_logs(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_balance_adjustment_logs_admin_id ON balance_adjustment_logs(admin_id)",
        """
        CREATE TABLE IF NOT EXISTS store_guayabits_reward_tiers (
            id SERIAL PRIMARY KEY,
            amount_from DOUBLE PRECISION NOT NULL,
            amount_to DOUBLE PRECISION NOT NULL,
            guayabits_reward DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "ALTER TABLE store_products ADD COLUMN IF NOT EXISTS product_code VARCHAR(80) NOT NULL DEFAULT ''",
        "ALTER TABLE store_products ADD COLUMN IF NOT EXISTS is_popular BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE store_product_media ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT FALSE",
        "CREATE INDEX IF NOT EXISTS ix_store_products_product_code ON store_products(product_code)",
        "CREATE INDEX IF NOT EXISTS ix_store_products_is_popular ON store_products(is_popular)",
        """
        UPDATE store_product_media AS m
        SET is_primary = TRUE
        FROM (
            SELECT DISTINCT ON (product_id) id
            FROM store_product_media
            ORDER BY product_id, sort_order, id
        ) AS first_media
        WHERE m.id = first_media.id
          AND NOT EXISTS (
            SELECT 1 FROM store_product_media p
            WHERE p.product_id = m.product_id AND p.is_primary = TRUE
          )
        """,
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_link_generations INTEGER NOT NULL DEFAULT 0",
        """
        CREATE TABLE IF NOT EXISTS referral_settings (
            id INTEGER PRIMARY KEY,
            max_referrals_per_user INTEGER NOT NULL DEFAULT 10,
            guayabits_per_referral DOUBLE PRECISION NOT NULL DEFAULT 1000,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "ALTER TABLE referral_settings ALTER COLUMN updated_at SET DEFAULT NOW()",
        "UPDATE referral_settings SET updated_at = NOW() WHERE updated_at IS NULL",
        """
        INSERT INTO referral_settings (
            id, max_referrals_per_user, guayabits_per_referral, is_enabled, updated_at
        )
        VALUES (1, 10, 1000, TRUE, NOW())
        ON CONFLICT (id) DO NOTHING
        """,
        """
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id INTEGER NOT NULL REFERENCES users(id),
            referred_user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
            status VARCHAR(20) NOT NULL DEFAULT 'pendiente',
            guayabits_rewarded DOUBLE PRECISION NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            activated_at TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_referrals_referrer_id ON referrals(referrer_id)",
        "CREATE INDEX IF NOT EXISTS ix_referrals_status ON referrals(status)",
        """
        CREATE TABLE IF NOT EXISTS platform_settings (
            id INTEGER PRIMARY KEY,
            lobby_inactivity_minutes INTEGER NOT NULL DEFAULT 3,
            verification_resend_cooldown_minutes INTEGER NOT NULL DEFAULT 5,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "ALTER TABLE platform_settings ALTER COLUMN updated_at SET DEFAULT NOW()",
        """
        INSERT INTO platform_settings (
            id, lobby_inactivity_minutes, verification_resend_cooldown_minutes, updated_at
        )
        VALUES (1, 3, 5, NOW())
        ON CONFLICT (id) DO NOTHING
        """,
        """
        CREATE TABLE IF NOT EXISTS balance_movements (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            movement_type VARCHAR(30) NOT NULL,
            concept VARCHAR(255) NOT NULL,
            previous_balance DOUBLE PRECISION NOT NULL,
            new_balance DOUBLE PRECISION NOT NULL,
            delta DOUBLE PRECISION NOT NULL,
            reference_id INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_balance_movements_user_id ON balance_movements(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_balance_movements_movement_type ON balance_movements(movement_type)",
        "CREATE INDEX IF NOT EXISTS ix_balance_movements_created_at ON balance_movements(created_at)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS id_document VARCHAR(20)",
        "CREATE INDEX IF NOT EXISTS ix_users_id_document ON users(id_document)",
        # ── Publicidad ────────────────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS advertisement_banners (
            id SERIAL PRIMARY KEY,
            original_name VARCHAR(255) NOT NULL,
            object_key VARCHAR(500) NOT NULL UNIQUE,
            public_url VARCHAR(700) NOT NULL,
            mime_type VARCHAR(50) NOT NULL DEFAULT 'image/webp',
            file_size INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_adv_banners_object_key ON advertisement_banners(object_key)",
        """
        CREATE TABLE IF NOT EXISTS advertisements (
            id SERIAL PRIMARY KEY,
            banner_id INTEGER NOT NULL REFERENCES advertisement_banners(id),
            balance_threshold DOUBLE PRECISION NOT NULL,
            frequency VARCHAR(30) NOT NULL DEFAULT 'once_per_session',
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by_id INTEGER REFERENCES users(id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_advertisements_is_active ON advertisements(is_active)",
        "CREATE INDEX IF NOT EXISTS ix_advertisements_banner_id ON advertisements(banner_id)",
        """
        CREATE TABLE IF NOT EXISTS advertisement_sections (
            id SERIAL PRIMARY KEY,
            advertisement_id INTEGER NOT NULL REFERENCES advertisements(id) ON DELETE CASCADE,
            section VARCHAR(30) NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_adv_sections_advertisement_id ON advertisement_sections(advertisement_id)",
        "CREATE INDEX IF NOT EXISTS ix_adv_sections_section ON advertisement_sections(section)",
        # ── Descuento y urgencia en productos de tienda ───────────────────────────
        "ALTER TABLE store_products ADD COLUMN IF NOT EXISTS discount_percent DOUBLE PRECISION",
        "ALTER TABLE store_products ADD COLUMN IF NOT EXISTS urgency_text VARCHAR(120)",
        # ── Índices para listados paginados ─────────────────────────────────────
        "CREATE INDEX IF NOT EXISTS ix_store_products_public_list ON store_products(status, is_popular DESC, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_store_orders_user_created ON store_orders(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_store_orders_status_created ON store_orders(status, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_game_history_finished_at ON game_history(finished_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_balance_movements_user_created ON balance_movements(user_id, created_at DESC)",
        # ── Categorías múltiples por producto ────────────────────────────────────
        # store_products.category se mantiene poblada con la primera categoría
        # por compatibilidad, pero deja de ser la fuente de verdad: la relación
        # N:M en store_product_categories es la real desde aquí.
        """
        CREATE TABLE IF NOT EXISTS store_product_categories (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES store_products(id) ON DELETE CASCADE,
            category VARCHAR(80) NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_store_product_categories_product_id ON store_product_categories(product_id)",
        "CREATE INDEX IF NOT EXISTS ix_store_product_categories_category ON store_product_categories(category)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_store_product_categories_product_category ON store_product_categories(product_id, category)",
        # Backfill idempotente: solo inserta para productos que aún no tengan
        # ningún vínculo en la tabla nueva, así no duplica ni pisa asignaciones
        # de varias categorías hechas después de este despliegue.
        """
        INSERT INTO store_product_categories (product_id, category)
        SELECT sp.id, sp.category
        FROM store_products sp
        WHERE NOT EXISTS (
            SELECT 1 FROM store_product_categories spc WHERE spc.product_id = sp.id
        )
        """,
        # ── Fase 2: contadores incrementales del ranking de torneo ──────────────
        # Sustituyen el recorrido completo de game_history en cada cálculo del
        # ranking. Ver scripts/backfill_tournament_counters.py para poblarlos
        # con el historial ya existente.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS tournament_games_played INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS tournament_games_won INTEGER NOT NULL DEFAULT 0",
        # ── Fase 2: paginación de auditoría de saldo y ranking de torneo ─────────
        "CREATE INDEX IF NOT EXISTS ix_balance_adjustment_logs_user_created ON balance_adjustment_logs(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS ix_users_tournament_balance_active ON users(tournament_balance) WHERE tournament_balance > 0",
        # ── Atribución de campaña (Meta Ads: captura de UTM) ─────────────────────
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS utm_source VARCHAR(120)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS utm_medium VARCHAR(120)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS utm_campaign VARCHAR(120)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS utm_term VARCHAR(120)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS utm_content VARCHAR(120)",
        "ALTER TABLE store_orders ADD COLUMN IF NOT EXISTS utm_source VARCHAR(120)",
        "ALTER TABLE store_orders ADD COLUMN IF NOT EXISTS utm_medium VARCHAR(120)",
        "ALTER TABLE store_orders ADD COLUMN IF NOT EXISTS utm_campaign VARCHAR(120)",
        "ALTER TABLE store_orders ADD COLUMN IF NOT EXISTS utm_term VARCHAR(120)",
        "ALTER TABLE store_orders ADD COLUMN IF NOT EXISTS utm_content VARCHAR(120)",
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

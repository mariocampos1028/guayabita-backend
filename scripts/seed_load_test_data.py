"""Genera datos sintéticos para medir el rendimiento con volumen realista.

Las bases de datos de desarrollo y producción están prácticamente vacías, así que
``EXPLAIN ANALYZE`` sobre ellas no dice nada: Postgres elige ``Seq Scan`` con
razón cuando una tabla cabe en unas pocas páginas. Este script llena las tablas
que más crecen con el uso hasta el volumen proyectado, para poder comprobar si
los índices se usan de verdad y cuánto tarda cada consulta a escala.

Todo lo que inserta queda marcado (usuarios ``loadtest_*``, salas ``LT*``) para
poder borrarlo por completo con ``--clean``.

USO — nunca contra producción:

    python scripts/seed_load_test_data.py --scale small --confirm-host <host-dev>
    python scripts/seed_load_test_data.py --clean --confirm-host <host-dev>

``--confirm-host`` debe coincidir con el host de DATABASE_URL. Es deliberado:
obliga a mirar a qué base apuntas antes de escribir millones de filas.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

# users, partidas. Los movimientos de saldo se derivan: ~10 por partida
# (2 por jugador), que es la proporción real que produce el juego.
SCALES = {
    "micro": (500, 5_000),
    "small": (1_000, 20_000),
    "medium": (5_000, 150_000),
    "large": (20_000, 600_000),
}

USER_PREFIX = "loadtest_"
ROOM_PREFIX = "LT"

SEEDED_TABLES = [
    "users",
    "game_history",
    "balance_movements",
    "store_orders",
    "balance_adjustment_logs",
]


def _seed_users(cur, count: int) -> None:
    cur.execute(
        """
        INSERT INTO users (
            username, email, password_hash, first_name, last_name, phone, address,
            is_admin, balance, tournament_balance, email_verified, email_verified_at,
            last_login_at, created_at, referral_link_generations
        )
        SELECT
            %(prefix)s || g,
            %(prefix)s || g || '@loadtest.invalid',
            '$2b$12$loadtestloadtestloadtestloadtestloadtestloadtestloa',
            'Nombre' || g,
            'Apellido' || g,
            '300' || lpad(g::text, 7, '0'),
            'Calle ' || g || ' # 45-67',
            false,
            (1000 + random() * 50000)::double precision,
            -- Solo una parte de los usuarios participa en el torneo activo, que es
            -- lo que hace que el índice parcial de ranking tenga sentido.
            CASE WHEN g %% 4 = 0 THEN (random() * 20000)::double precision ELSE 0 END,
            true,
            NOW(),
            NOW() - (random() * 30)::int * INTERVAL '1 day',
            NOW() - (random() * 365)::int * INTERVAL '1 day',
            0
        FROM generate_series(1, %(count)s) AS g
        """,
        {"prefix": USER_PREFIX, "count": count},
    )


def _user_id_range(cur) -> tuple[int, int]:
    cur.execute(
        "SELECT MIN(id), MAX(id) FROM users WHERE username LIKE %s",
        (USER_PREFIX + "%",),
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        raise SystemExit("No hay usuarios de prueba: ejecuta primero sin --clean.")
    return int(row[0]), int(row[1])


def _seed_game_history(cur, count: int, min_id: int, span: int) -> None:
    cur.execute(
        """
        INSERT INTO game_history (room_code, winner_id, players_json, audit_log, finished_at)
        SELECT
            %(room_prefix)s || upper(substr(md5(g::text), 1, 6)),
            %(min_id)s + (random() * %(span)s)::int,
            (
                SELECT json_agg(json_build_object(
                    'player_index', p - 1,
                    'user_id', %(min_id)s + ((g * 31 + p * 7) %% (%(span)s + 1)),
                    'name', 'loadtest_u' || p,
                    'final_balance', (random() * 30000)::int
                ))::text
                FROM generate_series(1, 4 + (g %% 7)) AS p
            ),
            repeat('{"e":"roll1","n":"jugador","r":3,"tbl":1500,"b":4200},', 20 + (g %% 40)),
            NOW() - (random() * 365)::int * INTERVAL '1 day'
                   - (random() * 86400)::int * INTERVAL '1 second'
        FROM generate_series(1, %(count)s) AS g
        """,
        {"room_prefix": ROOM_PREFIX, "count": count, "min_id": min_id, "span": span},
    )


def _seed_balance_movements(cur, count: int, min_id: int, span: int) -> None:
    cur.execute(
        """
        INSERT INTO balance_movements (
            user_id, movement_type, concept, previous_balance, new_balance, delta,
            reference_id, created_at
        )
        SELECT
            %(min_id)s + (random() * %(span)s)::int,
            (ARRAY[
                'partida_entrada','partida_resultado','partida_resultado',
                'recarga','tienda_regalo','referido','torneo'
            ])[1 + (random() * 6)::int],
            'Movimiento de prueba de carga #' || g,
            prev.balance,
            prev.balance + mov.delta,
            mov.delta,
            NULL,
            NOW() - (random() * 365)::int * INTERVAL '1 day'
                   - (random() * 86400)::int * INTERVAL '1 second'
        FROM generate_series(1, %(count)s) AS g
        CROSS JOIN LATERAL (SELECT (random() * 50000)::double precision AS balance) prev
        CROSS JOIN LATERAL (SELECT ((random() - 0.5) * 5000)::double precision AS delta) mov
        """,
        {"count": count, "min_id": min_id, "span": span},
    )


def _seed_store_orders(cur, count: int, min_id: int, span: int) -> None:
    cur.execute(
        """
        INSERT INTO store_orders (
            reference, user_id, product_id, product_name, product_price, guayabits_reward,
            quantity, customer_first_name, customer_last_name, customer_email, customer_phone,
            shipping_address, department, city, payment_type, status, guayabits_credited,
            created_at, updated_at
        )
        SELECT
            'LT-' || lpad(g::text, 10, '0'),
            %(min_id)s + (random() * %(span)s)::int,
            NULL,
            'Producto de prueba ' || (g %% 50),
            (20000 + random() * 500000)::double precision,
            (random() * 5000)::double precision,
            1,
            'Nombre' || g,
            'Apellido' || g,
            'loadtest_o' || g || '@loadtest.invalid',
            '300' || lpad(g::text, 7, '0'),
            'Calle ' || g || ' # 45-67',
            'Antioquia',
            'Medellín',
            CASE WHEN g %% 2 = 0 THEN 'contraentrega' ELSE 'directo' END,
            (ARRAY[
                'en_validacion','en_proceso','en_alistamiento',
                'en_reparto','entregado','rechazado'
            ])[1 + (random() * 5)::int],
            false,
            NOW() - (random() * 365)::int * INTERVAL '1 day',
            NOW() - (random() * 30)::int * INTERVAL '1 day'
        FROM generate_series(1, %(count)s) AS g
        """,
        {"count": count, "min_id": min_id, "span": span},
    )


def _seed_balance_adjustment_logs(cur, count: int, min_id: int, span: int) -> None:
    cur.execute(
        """
        INSERT INTO balance_adjustment_logs (
            user_id, admin_id, previous_balance, new_balance, delta, justification, created_at
        )
        SELECT
            %(min_id)s + (random() * %(span)s)::int,
            %(min_id)s,
            prev.balance,
            prev.balance + adj.delta,
            adj.delta,
            'Ajuste de prueba de carga #' || g,
            NOW() - (random() * 365)::int * INTERVAL '1 day'
        FROM generate_series(1, %(count)s) AS g
        CROSS JOIN LATERAL (SELECT (random() * 30000)::double precision AS balance) prev
        CROSS JOIN LATERAL (SELECT ((random() - 0.5) * 8000)::double precision AS delta) adj
        """,
        {"count": count, "min_id": min_id, "span": span},
    )


def seed(conn, users: int, games: int) -> None:
    movements = games * 10
    orders = max(1, users // 10)
    adjustments = max(1, users // 50)

    steps = [
        ("usuarios", users, lambda cur: _seed_users(cur, users)),
    ]
    with conn.cursor() as cur:
        for label, total, run in steps:
            started = time.perf_counter()
            run(cur)
            conn.commit()
            print(f"  {label:24} {total:>10,}  ({time.perf_counter() - started:.1f}s)")

        min_id, max_id = _user_id_range(cur)
        span = max(0, max_id - min_id)

        remaining = [
            ("partidas", games, lambda cur: _seed_game_history(cur, games, min_id, span)),
            ("movimientos de saldo", movements, lambda cur: _seed_balance_movements(cur, movements, min_id, span)),
            ("pedidos de tienda", orders, lambda cur: _seed_store_orders(cur, orders, min_id, span)),
            ("ajustes de saldo", adjustments, lambda cur: _seed_balance_adjustment_logs(cur, adjustments, min_id, span)),
        ]
        for label, total, run in remaining:
            started = time.perf_counter()
            run(cur)
            conn.commit()
            print(f"  {label:24} {total:>10,}  ({time.perf_counter() - started:.1f}s)")

        # Sin estadísticas frescas el planificador sigue creyendo que las tablas
        # están vacías y elegiría Seq Scan igual: sin esto la medición no vale.
        print("  actualizando estadísticas (ANALYZE)…")
        cur.execute("ANALYZE users, game_history, balance_movements, store_orders, balance_adjustment_logs")
        conn.commit()


def _database_size(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        return cur.fetchone()[0]


def _vacuum_full(conn) -> None:
    """Devuelve el espacio al disco.

    ``DELETE`` solo marca las filas como muertas: los archivos de la tabla siguen
    ocupando el mismo espacio en el volumen. En un plan medido eso importa, así
    que reescribimos las tablas para liberarlo de verdad.
    """
    previous_autocommit = conn.autocommit
    conn.autocommit = True  # VACUUM FULL no puede correr dentro de una transacción
    try:
        with conn.cursor() as cur:
            for table in SEEDED_TABLES:  # lista fija en código, no viene del usuario
                print(f"  liberando espacio de {table}…")
                cur.execute(f"VACUUM (FULL, ANALYZE) {table}")
    finally:
        conn.autocommit = previous_autocommit


def clean(conn) -> None:
    like_user = USER_PREFIX + "%"
    like_room = ROOM_PREFIX + "%"
    with conn.cursor() as cur:
        statements = [
            ("movimientos de saldo",
             "DELETE FROM balance_movements WHERE user_id IN (SELECT id FROM users WHERE username LIKE %s)",
             (like_user,)),
            ("ajustes de saldo",
             "DELETE FROM balance_adjustment_logs WHERE user_id IN (SELECT id FROM users WHERE username LIKE %s)"
             " OR admin_id IN (SELECT id FROM users WHERE username LIKE %s)",
             (like_user, like_user)),
            ("pedidos de tienda",
             "DELETE FROM store_orders WHERE user_id IN (SELECT id FROM users WHERE username LIKE %s)",
             (like_user,)),
            # Las salas reales tienen 6 caracteres y las sintéticas 8: exigir la
            # longitud evita borrar una partida real cuyo código empiece por 'LT'.
            ("partidas",
             "DELETE FROM game_history WHERE room_code LIKE %s AND length(room_code) = 8",
             (like_room,)),
            ("usuarios", "DELETE FROM users WHERE username LIKE %s", (like_user,)),
        ]
        for label, sql, params in statements:
            cur.execute(sql, params)
            print(f"  {label:24} {cur.rowcount:>10,} filas borradas")
        conn.commit()
    _vacuum_full(conn)


def report(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT relname,
                   n_live_tup,
                   pg_size_pretty(pg_total_relation_size(relid))
            FROM pg_stat_user_tables
            WHERE relname IN ('users','game_history','balance_movements','store_orders','balance_adjustment_logs')
            ORDER BY n_live_tup DESC
            """
        )
        print("\n  Tabla                      Filas        Tamaño total")
        for name, rows, size in cur.fetchall():
            print(f"  {name:24} {rows:>10,}  {size}")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", choices=sorted(SCALES), default="small")
    parser.add_argument("--clean", action="store_true", help="Borra todos los datos de prueba")
    parser.add_argument("--confirm-host", required=True,
                        help="Fragmento del host de DATABASE_URL; evita apuntar a producción por accidente")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL no está definida.", file=sys.stderr)
        return 1

    host = urlparse(database_url).hostname or ""
    if args.confirm_host not in host:
        print(
            f"El host de DATABASE_URL es '{host}' y no contiene '{args.confirm_host}'.\n"
            "Verifica a qué base de datos estás apuntando antes de continuar.",
            file=sys.stderr,
        )
        return 1

    conn = psycopg2.connect(database_url)
    try:
        size_before = _database_size(conn)
        print(f"Base de datos: {host}  (tamaño actual: {size_before})")

        if args.clean:
            print("Borrando datos de prueba…")
            clean(conn)
        else:
            users, games = SCALES[args.scale]
            print(f"Generando escala '{args.scale}'…")
            seed(conn, users, games)

        report(conn)
        print(f"\n  Tamaño de la base: {size_before} → {_database_size(conn)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

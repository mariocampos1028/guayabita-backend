"""Puebla los contadores de torneo con el historial de partidas ya existente.

Hasta ahora el ranking contaba partidas recorriendo ``game_history`` en cada
cálculo. Ahora esos conteos viven en ``users.tournament_games_played`` y
``users.tournament_games_won``, que se incrementan al cerrar cada partida.

Este script rellena esos contadores una sola vez, después de desplegar las
columnas nuevas, para que el ranking del torneo en curso no cambie. Sin él,
todos los jugadores arrancarían en cero y se perderían los desempates.

Usa exactamente la misma lógica de conteo que tenía el ranking antes
(``tournament_service._count_user_game_stats``, que ignora historiales
duplicados), así que el resultado es idéntico al que devolvía el código viejo.

Es idempotente: recalcula desde cero y sobrescribe, se puede correr las veces
que haga falta.

    python scripts/backfill_tournament_counters.py --confirm-host <host>
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal  # noqa: E402
from app.services import tournament_service  # noqa: E402


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-host",
        required=True,
        help="Fragmento del host de DATABASE_URL, para confirmar a qué base apuntas",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL no está definida.", file=sys.stderr)
        return 1

    host = urlparse(database_url).hostname or ""
    if args.confirm_host not in host:
        print(
            f"El host de DATABASE_URL es '{host}' y no contiene '{args.confirm_host}'.",
            file=sys.stderr,
        )
        return 1

    print(f"Base de datos: {host}")
    db = SessionLocal()
    try:
        active = tournament_service.get_active_tournament(db)
        if active:
            print(f"Torneo activo: '{active.title}' (desde {active.started_at})")
        else:
            print("No hay torneo activo: se cuenta todo el historial.")

        updated, total_participations = tournament_service.backfill_tournament_counters(db)
        print(f"Usuarios actualizados: {updated}")
        print(f"Participaciones contadas: {total_participations}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

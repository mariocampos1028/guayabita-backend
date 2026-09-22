"""Pruebas del ranking de torneo con contadores incrementales.

El ranking dejó de recorrer ``game_history`` en cada cálculo y ahora lee
contadores en ``users``. Lo que importa comprobar es que el resultado sea
idéntico al del código anterior, por eso la prueba central compara el orden
nuevo contra una copia literal de la implementación vieja.

Cubre:
  - Mismo orden que la lógica anterior, sobre los mismos datos
  - Desempates: saldo > partidas jugadas > partidas ganadas > alfabético > id
  - Incremento al cerrar una partida (participantes y ganador)
  - Historiales duplicados no se cuentan dos veces (backfill)
  - Reinicio de contadores al activar un torneo
  - Solo cuentan las partidas posteriores al inicio del torneo
  - Los administradores quedan fuera del ranking
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.db.models_db import GameHistory, Tournament, User
from app.services import tournament_service as svc


@pytest.fixture(scope="function")
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_user(db: Session, username: str, tournament_balance: float = 0.0,
               is_admin: bool = False) -> User:
    user = User(
        username=username,
        email=f"{username}@test.com",
        password_hash="hashed",
        balance=5000.0,
        tournament_balance=tournament_balance,
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_game(db: Session, participants: list[User], winner: User | None,
               finished_at: datetime | None = None, room_code: str = "ABC123") -> GameHistory:
    players = [
        {"player_index": i, "user_id": u.id, "name": u.username, "final_balance": 1000}
        for i, u in enumerate(participants)
    ]
    history = GameHistory(
        room_code=room_code,
        winner_id=winner.id if winner else None,
        players_json=json.dumps(players),
        finished_at=finished_at or _now(),
    )
    db.add(history)
    db.commit()
    return history


def _activate_tournament(db: Session, started_at: datetime | None = None) -> Tournament:
    tournament = Tournament(
        title="Torneo de prueba",
        status="active",
        is_active=True,
        started_at=started_at or (_now() - timedelta(days=1)),
        ends_at=_now() + timedelta(days=1),
    )
    db.add(tournament)
    db.commit()
    db.refresh(tournament)
    return tournament


def _legacy_ranking(db: Session, limit: int | None = None) -> list[User]:
    """Copia literal del ranking anterior, que contaba recorriendo el historial."""
    users = db.query(User).filter(User.is_admin == False, User.tournament_balance > 0).all()  # noqa: E712
    if not users:
        return []
    user_ids = {user.id for user in users}
    active = svc.get_active_tournament(db)
    since = active.started_at if active else None
    games_played, games_won = svc._count_user_game_stats(db, user_ids, since=since)
    ranked = sorted(
        users,
        key=lambda user: (
            -user.tournament_balance,
            -games_played[user.id],
            -games_won[user.id],
            svc._alphabetical_rank_key(user.username),
            user.id,
        ),
    )
    return ranked[:limit] if limit is not None else ranked


# ── La prueba que importa: el resultado no cambia ──────────────────────────────

def test_ranking_nuevo_coincide_con_el_anterior(db: Session):
    _activate_tournament(db)
    ana = _make_user(db, "ana", tournament_balance=5000)
    beto = _make_user(db, "beto", tournament_balance=5000)
    caro = _make_user(db, "caro", tournament_balance=9000)
    dani = _make_user(db, "dani", tournament_balance=1000)

    # Beto juega más que Ana con el mismo saldo, así que debe quedar por encima.
    _make_game(db, [ana, beto, caro], winner=beto, room_code="G00001")
    _make_game(db, [beto, dani], winner=dani, room_code="G00002")
    _make_game(db, [beto, caro], winner=caro, room_code="G00003")

    esperado = [u.id for u in _legacy_ranking(db)]

    svc.backfill_tournament_counters(db)
    obtenido = [u.id for u in svc.get_ranked_tournament_players(db)]

    assert obtenido == esperado
    assert obtenido == [caro.id, beto.id, ana.id, dani.id]


def test_backfill_ignora_historiales_duplicados(db: Session):
    _activate_tournament(db)
    ana = _make_user(db, "ana", tournament_balance=1000)
    beto = _make_user(db, "beto", tournament_balance=1000)

    # Mismo código, mismo ganador, mismos jugadores: es el mismo historial repetido.
    _make_game(db, [ana, beto], winner=ana, room_code="DUP001")
    _make_game(db, [ana, beto], winner=ana, room_code="DUP001")

    svc.backfill_tournament_counters(db)
    db.refresh(ana)

    assert ana.tournament_games_played == 1
    assert ana.tournament_games_won == 1


def test_backfill_solo_cuenta_partidas_del_torneo_activo(db: Session):
    inicio = _now() - timedelta(days=2)
    _activate_tournament(db, started_at=inicio)
    ana = _make_user(db, "ana", tournament_balance=1000)

    _make_game(db, [ana], winner=ana, finished_at=inicio - timedelta(days=5), room_code="OLD001")
    _make_game(db, [ana], winner=ana, finished_at=inicio + timedelta(hours=1), room_code="NEW001")

    svc.backfill_tournament_counters(db)
    db.refresh(ana)

    assert ana.tournament_games_played == 1
    assert ana.tournament_games_won == 1


# ── Incremento al cerrar una partida ───────────────────────────────────────────

def test_register_finished_game_incrementa_participantes_y_ganador(db: Session):
    ana = _make_user(db, "ana")
    beto = _make_user(db, "beto")

    svc.register_finished_game(db, participant_ids=[ana.id, beto.id], winner_id=beto.id)
    db.commit()
    db.refresh(ana)
    db.refresh(beto)

    assert (ana.tournament_games_played, ana.tournament_games_won) == (1, 0)
    assert (beto.tournament_games_played, beto.tournament_games_won) == (1, 1)


def test_register_finished_game_acumula_varias_partidas(db: Session):
    ana = _make_user(db, "ana")
    for _ in range(3):
        svc.register_finished_game(db, participant_ids=[ana.id], winner_id=ana.id)
    db.commit()
    db.refresh(ana)

    assert ana.tournament_games_played == 3
    assert ana.tournament_games_won == 3


def test_register_finished_game_sin_ganador_no_falla(db: Session):
    ana = _make_user(db, "ana")
    svc.register_finished_game(db, participant_ids=[ana.id], winner_id=None)
    db.commit()
    db.refresh(ana)

    assert ana.tournament_games_played == 1
    assert ana.tournament_games_won == 0


def test_register_finished_game_ignora_ids_vacios(db: Session):
    ana = _make_user(db, "ana")
    # Un invitado sin cuenta llega como None en la lista de participantes.
    svc.register_finished_game(db, participant_ids=[ana.id, None], winner_id=ana.id)
    db.commit()
    db.refresh(ana)

    assert ana.tournament_games_played == 1


# ── Reinicio ───────────────────────────────────────────────────────────────────

def test_reset_pone_contadores_en_cero(db: Session):
    ana = _make_user(db, "ana")
    svc.register_finished_game(db, participant_ids=[ana.id], winner_id=ana.id)
    db.commit()

    svc.reset_tournament_counters(db)
    db.commit()
    db.refresh(ana)

    assert ana.tournament_games_played == 0
    assert ana.tournament_games_won == 0


# ── Desempates y filtros ───────────────────────────────────────────────────────

def test_desempate_por_partidas_jugadas_y_luego_ganadas(db: Session):
    _activate_tournament(db)
    ana = _make_user(db, "ana", tournament_balance=1000)
    beto = _make_user(db, "beto", tournament_balance=1000)
    caro = _make_user(db, "caro", tournament_balance=1000)

    # Mismo saldo. Ana juega más; Beto y Caro empatan en jugadas pero Beto gana más.
    for _ in range(3):
        svc.register_finished_game(db, participant_ids=[ana.id], winner_id=None)
    for _ in range(2):
        svc.register_finished_game(db, participant_ids=[beto.id], winner_id=beto.id)
        svc.register_finished_game(db, participant_ids=[caro.id], winner_id=None)
    db.commit()

    ranking = [u.username for u in svc.get_ranked_tournament_players(db)]
    assert ranking == ["ana", "beto", "caro"]


def test_desempate_alfabetico_ignora_tildes_y_mayusculas(db: Session):
    _activate_tournament(db)
    _make_user(db, "Zeta", tournament_balance=1000)
    _make_user(db, "álvaro", tournament_balance=1000)

    ranking = [u.username for u in svc.get_ranked_tournament_players(db)]
    assert ranking == ["álvaro", "Zeta"]


def test_administradores_y_saldo_cero_quedan_fuera(db: Session):
    _activate_tournament(db)
    jugador = _make_user(db, "jugador", tournament_balance=1000)
    _make_user(db, "admin", tournament_balance=5000, is_admin=True)
    _make_user(db, "sin_saldo", tournament_balance=0)

    ranking = svc.get_ranked_tournament_players(db)
    assert [u.id for u in ranking] == [jugador.id]


def test_limite_recorta_el_ranking(db: Session):
    _activate_tournament(db)
    _make_user(db, "ana", tournament_balance=3000)
    _make_user(db, "beto", tournament_balance=2000)
    _make_user(db, "caro", tournament_balance=1000)

    assert len(svc.get_ranked_tournament_players(db, limit=2)) == 2
    assert svc.get_leaderboard_winner(db).username == "ana"


def test_ranking_vacio_sin_participantes(db: Session):
    _activate_tournament(db)
    _make_user(db, "sin_saldo", tournament_balance=0)

    assert svc.get_ranked_tournament_players(db) == []
    assert svc.get_leaderboard_winner(db) is None

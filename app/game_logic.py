import random
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.models import GameState, TurnState, Player, StartGameRequest

TURN_TIMEOUT_SECONDS = 120


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _empty_turn(player_index: int, bet: float, message: str) -> TurnState:
    return TurnState(
        current_player_index=player_index,
        phase="first-roll",
        current_bet=bet,
        first_roll=None,
        second_roll=None,
        message=message,
        deadline_at=_now() + timedelta(seconds=TURN_TIMEOUT_SECONDS),
    )


def _update_player(players: list[Player], player_id: int, delta: float) -> list[Player]:
    return [
        Player(**{**p.model_dump(), "balance": p.balance + delta}) if p.id == player_id else p
        for p in players
    ]


def _mark_eliminated(players: list[Player], player_id: int) -> list[Player]:
    return [
        Player(**{**p.model_dump(), "eliminated": True}) if p.id == player_id else p
        for p in players
    ]


def _players_with_balance(state: GameState) -> list[Player]:
    return [p for p in state.players if not p.eliminated and p.balance > 0]


def _eligible_players(state: GameState) -> list[Player]:
    return [p for p in state.players if not p.eliminated and p.balance >= state.case_value]


def _eliminate_player(state: GameState, player: Player, reason: str) -> GameState:
    players = _mark_eliminated(state.players, player.id)
    return state.model_copy(update={
        "players": players,
        "turn": state.turn.model_copy(update={
            "message": f"{player.name} quedó eliminado por {reason}.",
        }),
    })


def _eliminate_insolvent_players(state: GameState) -> GameState:
    messages: list[str] = []
    players = state.players
    for player in players:
        if not player.eliminated and 0 < player.balance < state.case_value:
            players = _mark_eliminated(players, player.id)
            messages.append(f"{player.name} quedó eliminado por falta de fondos.")
    if not messages:
        return state
    return state.model_copy(update={
        "players": players,
        "turn": state.turn.model_copy(update={"message": " ".join(messages)}),
    })


def _finish_table_empty(state: GameState, winner: Player) -> GameState:
    return state.model_copy(update={
        "status": "finished",
        "winner": winner,
        "turn": state.turn.model_copy(update={
            "phase": "result",
            "message": f"{winner.name} gana la partida por mesa sin saldo",
        }),
    })


def _award_pot_to_winner(state: GameState, winner: Player) -> GameState:
    pot = state.table_balance
    players = _update_player(state.players, winner.id, pot)
    updated_winner = next(p for p in players if p.id == winner.id)
    return state.model_copy(update={
        "players": players,
        "table_balance": 0,
        "status": "finished",
        "winner": updated_winner,
        "turn": state.turn.model_copy(update={
            "phase": "result",
            "message": (
                f"¡{updated_winner.name} gana la partida! "
                f"Se adjudicó el pozo de ${pot:.0f}."
            ),
        }),
    })


def _resolve_endgame(state: GameState, *, table_winner: Player | None = None) -> GameState:
    state = _eliminate_insolvent_players(state)

    if table_winner and state.table_balance <= 0:
        return _finish_table_empty(state, table_winner)

    survivors = _players_with_balance(state)
    if len(survivors) == 1:
        only = survivors[0]
        if state.table_balance > 0:
            return _award_pot_to_winner(state, only)
        return state.model_copy(update={
            "status": "finished",
            "winner": only,
            "turn": state.turn.model_copy(update={
                "phase": "result",
                "message": f"¡{only.name} gana la partida!",
            }),
        })

    if len(survivors) == 0 and state.table_balance <= 0:
        return state.model_copy(update={"status": "finished", "winner": None})

    return state


def _advance_to_next_turn(state: GameState) -> GameState:
    state = _eliminate_insolvent_players(state)
    ended = _resolve_endgame(state)
    if ended.status == "finished":
        return ended

    eligible = _eligible_players(state)
    if not eligible:
        survivors = _players_with_balance(state)
        if len(survivors) == 1:
            return _resolve_endgame(state)
        raise HTTPException(400, "No hay jugadores elegibles para continuar")

    current = state.players[state.turn.current_player_index]
    try:
        cur_pos = next(i for i, p in enumerate(eligible) if p.id == current.id)
    except StopIteration:
        cur_pos = -1

    next_player = eligible[(cur_pos + 1) % len(eligible)] if cur_pos >= 0 else eligible[0]
    next_index = next(i for i, p in enumerate(state.players) if p.id == next_player.id)
    return state.model_copy(update={
        "turn": _empty_turn(
            next_index,
            state.case_value,
            f"Turno de {next_player.name}. ¡Lanza el dado!",
        ),
    })


def apply_turn_timeout(state: GameState) -> GameState:
    if state.status != "playing":
        return state

    deadline = state.turn.deadline_at
    if deadline is None or _ensure_aware(deadline) > _now():
        return state

    player = state.players[state.turn.current_player_index]
    if player.eliminated:
        return state

    state = _eliminate_player(state, player, "tiempo agotado (2 min)")
    ended = _resolve_endgame(state)
    if ended.status == "finished":
        return ended
    return _advance_to_next_turn(state)


def start_game(req: StartGameRequest) -> GameState:
    players = [
        Player(id=i, name=p.name, balance=p.balance, eliminated=False)
        for i, p in enumerate(req.players)
    ]
    table_balance = len(players) * req.case_value
    players = [
        Player(**{**p.model_dump(), "balance": p.balance - req.case_value})
        for p in players
    ]
    first = players[0]
    return GameState(
        players=players,
        table_balance=table_balance,
        case_value=req.case_value,
        turn=_empty_turn(0, req.case_value, f"Turno de {first.name}. ¡Lanza el dado!"),
        status="playing",
        winner=None,
    )


def place_bet(state: GameState, amount: float) -> GameState:
    if state.turn.phase != "betting":
        raise HTTPException(400, "No es el momento de apostar")
    player = state.players[state.turn.current_player_index]
    if player.eliminated:
        raise HTTPException(400, "El jugador está eliminado")
    max_bet = min(player.balance, state.table_balance)
    if max_bet < state.case_value:
        raise HTTPException(400, "Saldo insuficiente para apostar")
    bet = max(state.case_value, min(amount, max_bet))
    new_turn = state.turn.model_copy(update={
        "current_bet": bet,
        "phase": "second-roll",
        "message": (
            f"{player.name} apuesta ${bet:.0f}. "
            f"¡Lanza de nuevo — debes sacar más de {state.turn.first_roll}!"
        ),
    })
    return state.model_copy(update={"turn": new_turn})


def roll_dice(state: GameState) -> GameState:
    if state.status != "playing":
        raise HTTPException(400, "El juego no está en curso")
    player = state.players[state.turn.current_player_index]
    if player.eliminated:
        raise HTTPException(400, "El jugador está eliminado")
    if player.balance < state.case_value:
        raise HTTPException(400, "Saldo insuficiente para jugar")

    roll = random.randint(1, 6)
    if state.turn.phase == "first-roll":
        return _handle_first_roll(state, roll)
    if state.turn.phase == "second-roll":
        return _handle_second_roll(state, roll)
    raise HTTPException(400, "No es el momento de lanzar el dado")


def _handle_first_roll(state: GameState, roll: int) -> GameState:
    player = state.players[state.turn.current_player_index]
    bet = state.case_value

    if roll == 1:
        players = _update_player(state.players, player.id, +bet)
        new_table = state.table_balance - bet
        updated_player = next(p for p in players if p.id == player.id)
        new_state = state.model_copy(update={
            "players": players,
            "table_balance": new_table,
            "turn": state.turn.model_copy(update={
                "first_roll": roll,
                "phase": "result",
                "message": f"{player.name} sacó 1 🎉 y ganó ${bet:.0f} de la mesa.",
            }),
        })
        if new_table <= 0:
            return _finish_table_empty(new_state, updated_player)
        return _resolve_endgame(new_state)

    if roll == 6:
        players = _update_player(state.players, player.id, -bet)
        new_state = state.model_copy(update={
            "players": players,
            "table_balance": state.table_balance + bet,
            "turn": state.turn.model_copy(update={
                "first_roll": roll,
                "phase": "result",
                "message": f"{player.name} sacó 6 😬 y puso ${bet:.0f} en la mesa.",
            }),
        })
        return _resolve_endgame(new_state)

    new_turn = state.turn.model_copy(update={
        "first_roll": roll,
        "phase": "betting",
        "current_bet": state.case_value,
        "message": f"{player.name} sacó {roll}. Define cuánto apostás para el segundo lanzamiento.",
    })
    return state.model_copy(update={"turn": new_turn})


def _handle_second_roll(state: GameState, roll: int) -> GameState:
    player = state.players[state.turn.current_player_index]
    first_roll = state.turn.first_roll
    bet = state.turn.current_bet

    if roll > first_roll:
        players = _update_player(state.players, player.id, +bet)
        new_table = state.table_balance - bet
        updated_player = next(p for p in players if p.id == player.id)
        new_state = state.model_copy(update={
            "players": players,
            "table_balance": new_table,
            "turn": state.turn.model_copy(update={
                "second_roll": roll,
                "phase": "result",
                "message": f"{player.name} sacó {roll} > {first_roll} 🎉 y ganó ${bet:.0f}.",
            }),
        })
        if new_table <= 0:
            return _finish_table_empty(new_state, updated_player)
        return _resolve_endgame(new_state)

    players = _update_player(state.players, player.id, -bet)
    new_state = state.model_copy(update={
        "players": players,
        "table_balance": state.table_balance + bet,
        "turn": state.turn.model_copy(update={
            "second_roll": roll,
            "phase": "result",
            "message": f"{player.name} sacó {roll} ≤ {first_roll} 😢 y perdió ${bet:.0f}.",
        }),
    })
    return _resolve_endgame(new_state)


def next_turn(state: GameState) -> GameState:
    if state.status != "playing" or state.turn.phase != "result":
        raise HTTPException(400, "No es el momento de pasar turno")
    return _advance_to_next_turn(state)

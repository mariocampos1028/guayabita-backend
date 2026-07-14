import random
from fastapi import HTTPException
from app.models import GameState, TurnState, Player, StartGameRequest


def _empty_turn(player_index: int, bet: float, message: str) -> TurnState:
    return TurnState(
        current_player_index=player_index,
        phase="first-roll",
        current_bet=bet,
        first_roll=None,
        second_roll=None,
        message=message,
    )


def _update_player(players: list[Player], player_id: int, delta: float) -> list[Player]:
    return [
        Player(**{**p.model_dump(), "balance": p.balance + delta}) if p.id == player_id else p
        for p in players
    ]


def _check_game_over(state: GameState) -> GameState:
    active = [p for p in state.players if p.balance > 0]
    if state.table_balance <= 0 or len(active) <= 1:
        winner = active[0] if len(active) == 1 else None
        return state.model_copy(update={"status": "finished", "winner": winner})
    return state


def start_game(req: StartGameRequest) -> GameState:
    players = [Player(id=i, name=p.name, balance=p.balance) for i, p in enumerate(req.players)]
    table_balance = len(players) * req.case_value
    players = [Player(**{**p.model_dump(), "balance": p.balance - req.case_value}) for p in players]
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
    max_bet = min(player.balance, state.table_balance)
    bet = max(state.case_value, min(amount, max_bet))
    new_turn = state.turn.model_copy(update={
        "current_bet": bet,
        "phase": "second-roll",
        "message": f"{player.name} apuesta ${bet:.0f}. ¡Lanza de nuevo — debes sacar más de {state.turn.first_roll}!",
    })
    return state.model_copy(update={"turn": new_turn})


def roll_dice(state: GameState) -> GameState:
    if state.status != "playing":
        raise HTTPException(400, "El juego no está en curso")
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
        new_state = state.model_copy(update={
            "players": players,
            "table_balance": state.table_balance - bet,
            "turn": state.turn.model_copy(update={
                "first_roll": roll, "phase": "result",
                "message": f"{player.name} sacó 1 🎉 y ganó ${bet:.0f} de la mesa.",
            }),
        })
        return _check_game_over(new_state)

    if roll == 6:
        players = _update_player(state.players, player.id, -bet)
        new_state = state.model_copy(update={
            "players": players,
            "table_balance": state.table_balance + bet,
            "turn": state.turn.model_copy(update={
                "first_roll": roll, "phase": "result",
                "message": f"{player.name} sacó 6 😬 y puso ${bet:.0f} en la mesa.",
            }),
        })
        return _check_game_over(new_state)

    # 2-5: betting phase
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
        new_state = state.model_copy(update={
            "players": players,
            "table_balance": state.table_balance - bet,
            "turn": state.turn.model_copy(update={
                "second_roll": roll, "phase": "result",
                "message": f"{player.name} sacó {roll} > {first_roll} 🎉 y ganó ${bet:.0f}.",
            }),
        })
    else:
        players = _update_player(state.players, player.id, -bet)
        new_state = state.model_copy(update={
            "players": players,
            "table_balance": state.table_balance + bet,
            "turn": state.turn.model_copy(update={
                "second_roll": roll, "phase": "result",
                "message": f"{player.name} sacó {roll} ≤ {first_roll} 😢 y perdió ${bet:.0f}.",
            }),
        })
    return _check_game_over(new_state)


def next_turn(state: GameState) -> GameState:
    if state.status != "playing" or state.turn.phase != "result":
        raise HTTPException(400, "No es el momento de pasar turno")
    active = [p for p in state.players if p.balance > 0]
    cur_id = state.players[state.turn.current_player_index].id
    cur_idx = next(i for i, p in enumerate(active) if p.id == cur_id)
    next_active = active[(cur_idx + 1) % len(active)]
    next_global_idx = next(i for i, p in enumerate(state.players) if p.id == next_active.id)
    return state.model_copy(update={
        "turn": _empty_turn(next_global_idx, state.case_value, f"Turno de {next_active.name}. ¡Lanza el dado!"),
    })

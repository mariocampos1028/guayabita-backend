"""Construcción de entradas compactas para el log de auditoría de partidas."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models import GameState


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _player_snapshot(state: GameState, index: int, user_id: int | None, username: str) -> dict:
    player = state.players[index]
    entry: dict = {
        "i": index,
        "n": username,
        "b": round(player.balance, 2),
    }
    if user_id is not None:
        entry["u"] = user_id
    return entry


def build_game_start(
    *,
    case_value: float,
    state: GameState,
    players_meta: list[dict],
    user_ids: list[int],
) -> dict:
    return {
        "at": _now_iso(),
        "e": "start",
        "case": case_value,
        "tbl": round(state.table_balance, 2),
        "pl": [
            {
                "i": i,
                "u": user_ids[i],
                "n": players_meta[i]["username"],
                "b0": round(players_meta[i].get("original_balance", state.players[i].balance + case_value), 2),
                "b": round(state.players[i].balance, 2),
            }
            for i in range(len(state.players))
        ],
    }


def build_bet(state: GameState, user_id: int | None, username: str) -> dict:
    idx = state.turn.current_player_index
    return {
        "at": _now_iso(),
        "e": "bet",
        "i": idx,
        "u": user_id,
        "n": username,
        "amt": round(state.turn.current_bet, 2),
        "r1": state.turn.first_roll,
        "tbl": round(state.table_balance, 2),
        "b": round(state.players[idx].balance, 2),
    }


def build_roll(before: GameState, after: GameState, user_id: int | None, username: str) -> dict:
    idx = before.turn.current_player_index

    if before.turn.phase == "first-roll":
        roll = after.turn.first_roll
        entry: dict = {
            "at": _now_iso(),
            "e": "roll1",
            "i": idx,
            "u": user_id,
            "n": username,
            "r": roll,
            "tbl0": round(before.table_balance, 2),
            "tbl": round(after.table_balance, 2),
            "b0": round(before.players[idx].balance, 2),
            "b": round(after.players[idx].balance, 2),
            "ph": after.turn.phase,
            "msg": after.turn.message,
        }
        if roll == 1:
            entry["out"] = "win_case"
            entry["amt"] = round(before.case_value, 2)
        elif roll == 6:
            entry["out"] = "lose_case"
            entry["amt"] = round(before.case_value, 2)
        return entry

    roll = after.turn.second_roll
    won = after.players[idx].balance > before.players[idx].balance
    return {
        "at": _now_iso(),
        "e": "roll2",
        "i": idx,
        "u": user_id,
        "n": username,
        "r": roll,
        "r1": before.turn.first_roll,
        "bet": round(before.turn.current_bet, 2),
        "win": won,
        "tbl0": round(before.table_balance, 2),
        "tbl": round(after.table_balance, 2),
        "b0": round(before.players[idx].balance, 2),
        "b": round(after.players[idx].balance, 2),
        "ph": after.turn.phase,
        "msg": after.turn.message,
    }


def build_next_turn(before: GameState, after: GameState, user_id: int | None, username: str) -> dict:
    idx = after.turn.current_player_index
    return {
        "at": _now_iso(),
        "e": "turn",
        "i": idx,
        "u": user_id,
        "n": username,
        "tbl": round(after.table_balance, 2),
        "b": round(after.players[idx].balance, 2),
        "prev": before.turn.message,
    }


def build_game_end(state: GameState, user_ids: list[int], usernames: list[str]) -> dict:
    winner = None
    if state.winner:
        winner = _player_snapshot(
            state,
            state.winner.id,
            user_ids[state.winner.id] if state.winner.id < len(user_ids) else None,
            state.winner.name,
        )

    return {
        "at": _now_iso(),
        "e": "end",
        "tbl": round(state.table_balance, 2),
        "w": winner,
        "pl": [
            _player_snapshot(state, i, user_ids[i] if i < len(user_ids) else None, usernames[i])
            for i in range(len(state.players))
        ],
        "msg": state.turn.message,
    }

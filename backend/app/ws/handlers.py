from fastapi import WebSocket, WebSocketDisconnect, Query, Depends
from app.ws.manager import ConnectionManager
from app.services.auth_service import AuthService
from app.services.tournament_service import TournamentService

ws_manager = ConnectionManager()
auth_service = AuthService()
active_tournament: TournamentService | None = None
active_tournaments: dict[str, TournamentService] = {}


async def get_auth_service() -> AuthService:
    return auth_service


async def spectate_endpoint(
    ws: WebSocket,
    token: str = Query(...),
    tournament_id: str = "",
):
    """WebSocket endpoint for spectating a tournament."""
    try:
        user = auth_service.verify_jwt(token)
    except Exception:
        await ws.close(code=4001, reason="Invalid token")
        return

    room = tournament_id or "main"
    await ws_manager.connect(ws, room, {"user_id": user["sub"], "username": user["username"]})

    # Send initial state if tournament is running
    tournament = get_active_tournament("poker")
    if tournament and tournament.is_running:
        state = tournament.engine.get_state()
        await ws_manager.broadcast_state(room, state)
        await ws_manager.broadcast(room, {
            "type": "spectator_count",
            "data": {"count": ws_manager.spectator_count(room)},
            "timestamp": 0,
        })

    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "pong":
                pass  # keepalive
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(ws)


def get_active_tournament(game_type: str = "poker") -> TournamentService | None:
    return active_tournaments.get(game_type)


def set_active_tournament(t: TournamentService | None, game_type: str | None = None):
    global active_tournament
    resolved_game_type = game_type or getattr(getattr(t, "engine", None), "game_type", "poker")
    if t is None:
        active_tournaments.pop(resolved_game_type, None)
        if active_tournament and getattr(active_tournament.engine, "game_type", "poker") == resolved_game_type:
            active_tournament = None
        return

    active_tournaments[resolved_game_type] = t
    active_tournament = t


def clear_active_tournaments():
    global active_tournament
    active_tournaments.clear()
    active_tournament = None

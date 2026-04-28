from fastapi import WebSocket, WebSocketDisconnect, Query, Depends
from app.ws.manager import ConnectionManager
from app.services.auth_service import AuthService
from app.services.tournament_service import TournamentService

ws_manager = ConnectionManager()
auth_service = AuthService()
active_tournament: TournamentService | None = None


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
    if active_tournament and active_tournament.is_running:
        state = active_tournament.engine._build_state([])
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


def set_active_tournament(t: TournamentService | None):
    global active_tournament
    active_tournament = t

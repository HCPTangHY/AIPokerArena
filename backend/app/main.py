import mimetypes
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from app.api.routes_auth import router as auth_router
from app.api.routes_config import router as config_router
from app.api.routes_tournament import router as tournament_router
from app.ws.handlers import auth_service, ws_manager
from app.ws import handlers as ws_handlers
from app.core.engine import PokerEngine  # noqa: F401 - registers poker
from app.core.werewolf_engine import WerewolfEngine  # noqa: F401 - registers werewolf

STATIC_DIR = Path(__file__).parent.parent / "static"

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")


class StaticFilesWithMime(StaticFiles):
    def _guess_type(self, path: str) -> str:
        mime, _ = mimetypes.guess_type(path)
        return mime or "application/octet-stream"


def build_ws_endpoint(game_type: str = "poker"):
    """Create a WebSocket endpoint function for a specific game type."""

    async def ws_spectate(ws: WebSocket, token: str = Query(...), tournament_id: str = Query("")):
        from app.ws.handlers import WebSocketDisconnect

        try:
            user = auth_service.verify_jwt(token)
        except Exception:
            await ws.close(code=4001, reason="Invalid token")
            return

        room = tournament_id or "main"
        await ws_manager.connect(ws, room, {"user_id": user["sub"], "username": user["username"]})

        tourney = ws_handlers.get_active_tournament(game_type)
        if tourney and tourney.is_running:
            state = tourney.engine.get_state()
            await ws_manager.broadcast_state(room, state)
        await ws_manager.send_room_snapshot(ws, room)
        await ws_manager.broadcast(room, {
            "type": "spectator_count",
            "data": {"count": ws_manager.spectator_count(room)},
            "timestamp": 0,
        })

        try:
            while True:
                data = await ws.receive_json()
                msg_type = data.get("type", "")
                if msg_type == "pong":
                    pass
                elif msg_type == "chat":
                    chat_text = (data.get("message") or "").strip()
                    if chat_text:
                        await ws_manager.broadcast_chat(
                            room,
                            user["sub"],
                            user.get("global_name", user["username"]),
                            chat_text,
                            is_thinking=False,
                            is_spectator=True,
                        )
                elif msg_type == "spectator_join":
                    await ws_manager.broadcast(room, {
                        "type": "spectator_count",
                        "data": {"count": ws_manager.spectator_count(room)},
                        "timestamp": 0,
                    })
        except WebSocketDisconnect:
            pass
        finally:
            ws_manager.disconnect(ws)

    return ws_spectate


def build_game_app(game_type: str) -> FastAPI:
    """Build a sub-app for a given game type."""
    title = {"poker": "AI Poker Arena", "werewolf": "AI Werewolf Arena"}.get(game_type, f"AI {game_type} Arena")
    app = FastAPI(title=title)

    # API routes
    app.include_router(auth_router)
    app.include_router(config_router)
    app.include_router(tournament_router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "game_type": game_type}

    # WebSocket
    ws_handler = build_ws_endpoint(game_type)
    app.websocket("/ws/spectate")(ws_handler)

    # Static files + SPA
    if STATIC_DIR.exists() and list(STATIC_DIR.iterdir()):
        app.mount("/assets", StaticFilesWithMime(directory=STATIC_DIR / "assets"), name=f"assets_{game_type}")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = STATIC_DIR / full_path
            if file_path.is_file():
                mime, _ = mimetypes.guess_type(str(file_path))
                content = file_path.read_bytes()
                return Response(content=content, media_type=mime or "application/octet-stream")
            return FileResponse(STATIC_DIR / "index.html")

    return app


def create_app() -> FastAPI:
    app = FastAPI(title="AI Game Arena")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
        yield
        from app.ws.handlers import clear_active_tournaments
        clear_active_tournaments()

    app.router.lifespan_context = lifespan

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount game sub-apps
    app.mount("/poker", build_game_app("poker"))
    app.mount("/werewolf", build_game_app("werewolf"))

    return app


app = create_app()

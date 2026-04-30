import asyncio
from fastapi import APIRouter, HTTPException, Depends, Query
from app.core.game_registry import get_engine_class
from app.services.ai_service import AIService
from app.services.tournament_service import TournamentService
from app.ws.handlers import ws_manager, set_active_tournament
from app.api.routes_config import get_tournament_config, get_player_configs
from app.api.deps import require_admin

router = APIRouter(prefix="/api/tournament", tags=["tournament"])

_active_tournaments: dict[str, TournamentService] = {}
_ai_service: AIService | None = None


def _ensure_ai_service(timeout: float = 120.0):
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService(timeout=timeout)
    elif _ai_service.timeout != timeout:
        _ai_service.timeout = timeout
        _ai_service.client = None
    return _ai_service


@router.post("/start")
async def start_tournament(
    game_type: str = Query("poker"),
    _user: dict = Depends(require_admin),
):
    global _active_tournaments

    active_tournament = _active_tournaments.get(game_type)
    if active_tournament and active_tournament.is_running:
        raise HTTPException(status_code=400, detail="Tournament already running")

    config = get_tournament_config(game_type)
    players = get_player_configs(game_type)

    if len(players) < 2:
        raise HTTPException(status_code=400, detail="At least 2 players required")

    engine_class = get_engine_class(game_type)
    engine = engine_class(config, players)
    timeout = float(getattr(config, 'action_timeout_seconds', 120) or 120)
    ai = _ensure_ai_service(timeout=timeout)

    tournament = TournamentService(
        engine=engine,
        players=players,
        ai_service=ai,
        ws_manager=ws_manager,
        delay_between_actions=0.5,
    )

    _active_tournaments[game_type] = tournament
    set_active_tournament(tournament, game_type)

    asyncio.create_task(tournament.run())

    return {
        "status": "started",
        "game_type": game_type,
        "tournament_id": engine.tournament_id,
    }


@router.post("/stop")
async def stop_tournament(
    game_type: str = Query("poker"),
    _user: dict = Depends(require_admin),
):
    global _active_tournaments

    active_tournament = _active_tournaments.get(game_type)
    if not active_tournament or not active_tournament.is_running:
        raise HTTPException(status_code=400, detail="No tournament running")

    await active_tournament.stop()
    set_active_tournament(None, game_type)
    _active_tournaments.pop(game_type, None)
    return {"status": "stopped"}


@router.get("/status")
async def get_status(game_type: str = Query("poker")):
    active_tournament = _active_tournaments.get(game_type)
    if not active_tournament or not active_tournament.is_running:
        return {"running": False, "state": None}

    state = active_tournament.engine.get_state()
    return {
        "running": True,
        "game_type": getattr(active_tournament.engine, 'game_type', 'poker'),
        "tournament_id": active_tournament.engine.tournament_id,
        "state": state.to_public_dict(),
    }

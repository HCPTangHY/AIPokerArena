import asyncio
from fastapi import APIRouter, HTTPException, Depends
from app.core.engine import PokerEngine
from app.services.ai_service import AIService
from app.services.tournament_service import TournamentService
from app.ws.handlers import ws_manager, set_active_tournament
from app.api.routes_config import get_tournament_config, get_player_configs
from app.api.deps import require_admin

router = APIRouter(prefix="/api/tournament", tags=["tournament"])

_active_tournament: TournamentService | None = None
_ai_service: AIService | None = None


def _ensure_ai_service(timeout: float = 120.0):
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService(timeout=timeout)
    elif _ai_service.timeout != timeout:
        _ai_service.timeout = timeout
        _ai_service.client = None  # recreate client with new timeout
    return _ai_service


@router.post("/start")
async def start_tournament(_user: dict = Depends(require_admin)):
    global _active_tournament

    if _active_tournament and _active_tournament.is_running:
        raise HTTPException(status_code=400, detail="Tournament already running")

    config = get_tournament_config()
    players = get_player_configs()

    if len(players) < 2:
        raise HTTPException(status_code=400, detail="At least 2 players required")

    engine = PokerEngine(config, players)
    timeout = float(getattr(config, 'action_timeout_seconds', 120) or 120)
    ai = _ensure_ai_service(timeout=timeout)

    _active_tournament = TournamentService(
        engine=engine,
        players=players,
        ai_service=ai,
        ws_manager=ws_manager,
        delay_between_actions=0.5,
    )

    set_active_tournament(_active_tournament)

    # Run in background
    asyncio.create_task(_active_tournament.run())

    return {
        "status": "started",
        "tournament_id": engine.tournament_id,
    }


@router.post("/stop")
async def stop_tournament(_user: dict = Depends(require_admin)):
    global _active_tournament

    if not _active_tournament or not _active_tournament.is_running:
        raise HTTPException(status_code=400, detail="No tournament running")

    await _active_tournament.stop()
    set_active_tournament(None)
    _active_tournament = None
    return {"status": "stopped"}


@router.get("/status")
async def get_status():
    if not _active_tournament or not _active_tournament.is_running:
        return {"running": False, "state": None}

    state = _active_tournament.engine._build_state([])
    return {
        "running": True,
        "tournament_id": _active_tournament.engine.tournament_id,
        "state": state.to_public_dict(),
    }

from fastapi import APIRouter, HTTPException, Depends
from app.models.tournament import TournamentConfig
from app.models.player import AIPlayerConfig
from app.services.config_service import (
    load_tournament_config,
    load_player_configs,
    save_tournament_config,
)
from app.config import settings
from app.api.deps import require_admin

router = APIRouter(prefix="/api/config", tags=["config"])


def get_tournament_config() -> TournamentConfig:
    return load_tournament_config()


def get_player_configs() -> list[AIPlayerConfig]:
    return load_player_configs()


@router.get("/tournament")
async def get_tournament():
    return get_tournament_config().model_dump()


@router.put("/tournament")
async def update_tournament(config: TournamentConfig, _user: dict = Depends(require_admin)):
    save_tournament_config(config, get_player_configs())
    return {"status": "ok", "config": config.model_dump()}


@router.get("/players")
async def get_players():
    return [p.model_dump() for p in get_player_configs()]


@router.post("/players")
async def add_player(player: AIPlayerConfig, _user: dict = Depends(require_admin)):
    players = get_player_configs()
    if len(players) >= 10:
        raise HTTPException(status_code=400, detail="Max 10 players")
    if any(p.id == player.id for p in players):
        raise HTTPException(status_code=400, detail=f"Player ID '{player.id}' already exists")
    players.append(player)
    save_tournament_config(get_tournament_config(), players)
    return {"status": "ok", "player": player.model_dump()}


@router.put("/players/{player_id}")
async def update_player(player_id: str, player: AIPlayerConfig, _user: dict = Depends(require_admin)):
    players = get_player_configs()
    for i, p in enumerate(players):
        if p.id == player_id:
            players[i] = player
            save_tournament_config(get_tournament_config(), players)
            return {"status": "ok", "player": player.model_dump()}
    raise HTTPException(status_code=404, detail="Player not found")


@router.delete("/players/{player_id}")
async def delete_player(player_id: str, _user: dict = Depends(require_admin)):
    players = get_player_configs()
    players = [p for p in players if p.id != player_id]
    save_tournament_config(get_tournament_config(), players)
    return {"status": "ok"}

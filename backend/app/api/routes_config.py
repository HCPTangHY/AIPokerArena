from fastapi import APIRouter, HTTPException, Depends, Query
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

DEFAULT_GAME = "poker"


def get_tournament_config(game_type: str = DEFAULT_GAME) -> TournamentConfig:
    return load_tournament_config(game_type=game_type)


def get_player_configs(game_type: str = DEFAULT_GAME) -> list[AIPlayerConfig]:
    return load_player_configs(game_type=game_type)


@router.get("/tournament")
async def get_tournament(game_type: str = Query(DEFAULT_GAME)):
    return get_tournament_config(game_type).model_dump()


@router.put("/tournament")
async def update_tournament(config: TournamentConfig, _user: dict = Depends(require_admin)):
    game_type = config.game_type or DEFAULT_GAME
    save_tournament_config(config, get_player_configs(game_type), game_type=game_type)
    return {"status": "ok", "config": config.model_dump()}


@router.get("/players")
async def get_players(game_type: str = Query(DEFAULT_GAME)):
    return [p.model_dump() for p in get_player_configs(game_type)]


@router.post("/players")
async def add_player(
    player: AIPlayerConfig,
    game_type: str = Query(DEFAULT_GAME),
    _user: dict = Depends(require_admin),
):
    players = get_player_configs(game_type)
    if len(players) >= 10:
        raise HTTPException(status_code=400, detail="Max 10 players")
    if any(p.id == player.id for p in players):
        raise HTTPException(status_code=400, detail=f"Player ID '{player.id}' already exists")
    players.append(player)
    save_tournament_config(get_tournament_config(game_type), players, game_type=game_type)
    return {"status": "ok", "player": player.model_dump()}


@router.put("/players/{player_id}")
async def update_player(
    player_id: str,
    player: AIPlayerConfig,
    game_type: str = Query(DEFAULT_GAME),
    _user: dict = Depends(require_admin),
):
    players = get_player_configs(game_type)
    for i, p in enumerate(players):
        if p.id == player_id:
            players[i] = player
            save_tournament_config(get_tournament_config(game_type), players, game_type=game_type)
            return {"status": "ok", "player": player.model_dump()}
    raise HTTPException(status_code=404, detail="Player not found")


@router.delete("/players/{player_id}")
async def delete_player(
    player_id: str,
    game_type: str = Query(DEFAULT_GAME),
    _user: dict = Depends(require_admin),
):
    players = get_player_configs(game_type)
    players = [p for p in players if p.id != player_id]
    save_tournament_config(get_tournament_config(game_type), players, game_type=game_type)
    return {"status": "ok"}

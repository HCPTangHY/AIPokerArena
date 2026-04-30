from enum import Enum
from pydantic import BaseModel, Field


class GameType(str, Enum):
    POKER = "poker"
    WEREWOLF = "werewolf"


class GameConfigBase(BaseModel):
    """所有游戏配置的基类。"""
    game_type: str = ""
    name: str = "Game"
    max_players: int = Field(ge=2, le=20, default=10)
    action_timeout_seconds: int = Field(ge=10, le=600, default=120)

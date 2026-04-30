from enum import Enum
from pydantic import BaseModel, Field


class GameType(str, Enum):
    POKER = "poker"
    WEREWOLF = "werewolf"


class Phase(str, Enum):
    PRE_FLOP = "pre_flop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"


class ActionType(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"
    ALL_IN = "all_in"
    SMALL_BLIND = "small_blind"
    BIG_BLIND = "big_blind"


class BlindLevel(BaseModel):
    level: int
    small_blind: int
    big_blind: int
    ante: int = 0


class TournamentConfig(BaseModel):
    game_type: str = "poker"
    name: str = "AI Poker Tournament"
    initial_chips: int = Field(ge=100, le=1000000, default=5000)
    small_blind_initial: int = Field(ge=1, default=10)
    big_blind_initial: int = Field(ge=2, default=20)
    blind_level_minutes: int = Field(ge=1, le=120, default=5)
    blind_levels: list[BlindLevel] = []
    ante_enabled: bool = False
    ante_start_level: int = 0
    max_players: int = Field(ge=2, le=10, default=10)
    action_timeout_seconds: int = Field(ge=10, le=600, default=120)

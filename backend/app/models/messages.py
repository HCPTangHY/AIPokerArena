from enum import Enum
from pydantic import BaseModel
from app.models.tournament import Phase, ActionType


class WSMessageType(str, Enum):
    # Server -> Client
    GAME_STATE = "game_state"
    GAME_EVENT = "game_event"
    CHAT = "chat"
    TOURNAMENT_START = "tournament_start"
    TOURNAMENT_OVER = "tournament_over"
    SPECTATOR_COUNT = "spectator_count"
    ERROR = "error"
    # Client -> Server
    PONG = "pong"


class WSMessage(BaseModel):
    type: WSMessageType
    data: dict | None = None
    timestamp: float | None = None

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")  # 玩家状态类型
A = TypeVar("A")  # 行动类型


@dataclass
class BasePlayerState:
    """所有游戏玩家状态的基类。"""
    player_id: str
    display_name: str
    is_alive: bool = True
    seat_index: int = 0
    avatar_url: str = ""


@dataclass
class BaseGameState:
    """所有游戏状态的基类。"""
    tournament_id: str
    game_type: str
    round_number: int
    players: list[BasePlayerState]
    phase: str
    events: list[dict] = field(default_factory=list)
    is_over: bool = False

    def to_public_dict(self) -> dict:
        """序列化为前端可用的字典。子类应重写此方法。"""
        return {
            "tournament_id": self.tournament_id,
            "game_type": self.game_type,
            "round_number": self.round_number,
            "phase": self.phase,
            "is_over": self.is_over,
            "players": [
                {
                    "id": p.player_id,
                    "display_name": p.display_name,
                    "is_alive": p.is_alive,
                    "seat_index": p.seat_index,
                    "avatar_url": p.avatar_url,
                }
                for p in self.players
            ],
            "events": self.events[-20:],
        }


class GameEngine(ABC):
    """所有游戏引擎的抽象基类。"""

    game_type: str = ""

    def __init__(self, config: Any, players: list[Any]):
        self.config = config
        self.tournament_id: str = ""
        self.is_running: bool = False

    @abstractmethod
    def start_game(self) -> BaseGameState:
        """启动游戏，返回初始状态。"""
        ...

    @abstractmethod
    def apply_action(self, action: Any) -> BaseGameState:
        """执行一个游戏行动，返回更新后的状态。"""
        ...

    @abstractmethod
    def get_state(self) -> BaseGameState:
        """返回当前游戏状态快照。"""
        ...

    @abstractmethod
    def is_game_over(self) -> bool:
        """检查游戏是否结束。"""
        ...

    @abstractmethod
    def get_winner(self) -> dict | None:
        """返回胜利者信息。"""
        ...

    def get_history(self) -> list[dict]:
        """返回游戏历史记录，子类可重写。"""
        return []

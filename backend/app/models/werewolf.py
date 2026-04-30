"""狼人杀游戏模型：角色、板子、阶段、行动"""

from enum import Enum
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


# ============================================================
# 游戏阶段
# ============================================================

class WerewolfPhase(str, Enum):
    ROLE_ASSIGN = "role_assign"        # 分配角色
    SHERIFF_ELECTION = "sheriff_election"  # 上警环节
    NIGHT = "night"                    # 夜晚
    DAY = "day"                        # 白天讨论
    VOTE = "vote"                      # 放逐投票
    GAME_OVER = "game_over"            # 游戏结束


# ============================================================
# 角色定义
# ============================================================

class Team(str, Enum):
    WEREWOLF = "werewolf"    # 狼人阵营
    VILLAGER = "villager"    # 好人阵营
    THIRD_PARTY = "third_party"  # 第三方


class NightActionType(str, Enum):
    KILL = "kill"            # 狼人刀人
    CHECK = "check"          # 预言家查验
    SAVE = "save"            # 女巫解药
    POISON = "poison"        # 女巫毒药
    GUARD = "guard"          # 守卫守人
    NONE = "none"            # 无行动


class RoleID(str, Enum):
    WEREWOLF = "werewolf"
    VILLAGER = "villager"
    SEER = "seer"
    WITCH = "witch"
    HUNTER = "hunter"
    IDIOT = "idiot"
    GUARD = "guard"


@dataclass
class RoleDefinition:
    """角色模板定义"""
    role_id: RoleID
    name: str                          # 中文名
    team: Team                         # 阵营
    night_priority: int                # 夜晚行动优先级（越小越先行动）
    night_action: NightActionType      # 夜晚行动类型
    max_uses: int                      # 最大使用次数（0=无限）
    can_be_sheriff: bool = True        # 是否能竞选警长
    description: str = ""              # 角色描述
    kills_on_elimination: bool = False # 被淘汰时是否触发技能（如猎人）


# 角色库
ROLE_LIBRARY: dict[RoleID, RoleDefinition] = {
    RoleID.WEREWOLF: RoleDefinition(
        role_id=RoleID.WEREWOLF, name="狼人", team=Team.WEREWOLF,
        night_priority=1, night_action=NightActionType.KILL,
        max_uses=0, description="每晚可以刀杀一名玩家",
    ),
    RoleID.SEER: RoleDefinition(
        role_id=RoleID.SEER, name="预言家", team=Team.VILLAGER,
        night_priority=2, night_action=NightActionType.CHECK,
        max_uses=0, description="每晚可以查验一名玩家的身份",
    ),
    RoleID.WITCH: RoleDefinition(
        role_id=RoleID.WITCH, name="女巫", team=Team.VILLAGER,
        night_priority=3, night_action=NightActionType.SAVE,  # 解药优先
        max_uses=2, description="拥有一瓶解药和一瓶毒药，各限一次",
    ),
    RoleID.GUARD: RoleDefinition(
        role_id=RoleID.GUARD, name="守卫", team=Team.VILLAGER,
        night_priority=4, night_action=NightActionType.GUARD,
        max_uses=0, description="每晚可以守护一名玩家（不能连续守护同一人）",
    ),
    RoleID.HUNTER: RoleDefinition(
        role_id=RoleID.HUNTER, name="猎人", team=Team.VILLAGER,
        night_priority=100, night_action=NightActionType.NONE,
        max_uses=0, description="被放逐或刀杀时可以开枪带走一名玩家",
        kills_on_elimination=True,
    ),
    RoleID.IDIOT: RoleDefinition(
        role_id=RoleID.IDIOT, name="白痴", team=Team.VILLAGER,
        night_priority=100, night_action=NightActionType.NONE,
        max_uses=0, description="被放逐时可以翻牌免死，但失去投票权",
    ),
    RoleID.VILLAGER: RoleDefinition(
        role_id=RoleID.VILLAGER, name="村民", team=Team.VILLAGER,
        night_priority=100, night_action=NightActionType.NONE,
        max_uses=0, description="无特殊能力，通过发言和投票找出狼人",
    ),
}


# ============================================================
# 板子定义
# ============================================================

class BoardPreset(BaseModel):
    """预置板子配置"""
    name: str
    description: str = ""
    roles: dict[str, int] = Field(default_factory=dict)  # role_id -> count

    @classmethod
    def get_preset(cls, preset_name: str) -> "BoardPreset":
        presets = {
            "预女猎白-6人": BoardPreset(
                name="预女猎白-6人", description="6人局：预言家、女巫、猎人、白痴各1，狼人2，村民1",
                roles={"werewolf": 2, "seer": 1, "witch": 1, "hunter": 1, "idiot": 0, "guard": 0, "villager": 1},
            ),
            "预女猎白-9人": BoardPreset(
                name="预女猎白-9人", description="9人局：预言家、女巫、猎人、白痴各1，狼人3，村民3",
                roles={"werewolf": 3, "seer": 1, "witch": 1, "hunter": 1, "idiot": 0, "guard": 0, "villager": 3},
            ),
            "预女猎白-12人": BoardPreset(
                name="预女猎白-12人", description="12人局：预言家、女巫、猎人、白痴各1，狼人4，村民4",
                roles={"werewolf": 4, "seer": 1, "witch": 1, "hunter": 1, "idiot": 1, "guard": 0, "villager": 4},
            ),
            "预女猎守-12人": BoardPreset(
                name="预女猎守-12人", description="12人局：预言家、女巫、猎人、守卫各1，狼人4，村民4",
                roles={"werewolf": 4, "seer": 1, "witch": 1, "hunter": 1, "idiot": 0, "guard": 1, "villager": 4},
            ),
        }
        return presets.get(preset_name)


# ============================================================
# 游戏配置
# ============================================================

class WerewolfConfig(BaseModel):
    """狼人杀游戏配置"""
    game_type: str = "werewolf"
    name: str = "AI Werewolf Tournament"
    board_preset: str = "预女猎白-9人"       # 预置板子名
    custom_roles: dict[str, int] = Field(default_factory=dict)  # 自定义角色数量（覆盖预置）
    discussion_rounds: int = Field(ge=1, le=5, default=2)       # 讨论轮数
    sheriff_election: bool = True           # 是否启用上警环节
    allow_sheriff_campaign: bool = True     # 是否允许AI自主决定是否参选
    max_players: int = Field(ge=6, le=18, default=12)
    action_timeout_seconds: int = Field(ge=10, le=600, default=120)
    night_duration_seconds: float = 2.0     # 夜晚动画时长
    day_duration_seconds: float = 1.0       # 白天过渡时长


# ============================================================
# 玩家状态（扩展）
# ============================================================

@dataclass
class WerewolfPlayerState:
    """狼人杀玩家状态"""
    player_id: str
    display_name: str
    role_id: RoleID | None = None        # 角色ID（观战者看不到）
    role_name: str = ""                   # 角色名（死后公开）
    team: Team | None = None
    is_alive: bool = True
    is_sheriff: bool = False              # 是否为警长
    has_voted: bool = False               # 本轮是否已投票
    vote_target: str | None = None        # 投票目标
    speech_history: list[str] = field(default_factory=list)  # 发言记录
    seat_index: int = 0
    avatar_url: str = ""
    # 角色能力状态
    witch_save_used: bool = False
    witch_poison_used: bool = False
    guard_last_protected: str | None = None  # 守卫上一轮守护对象
    # 猎人/白痴标记
    hunter_can_shoot: bool = False
    idiot_revealed: bool = False
    # 笔记
    notes: str = ""                       # AI私人笔记（跨轮记忆）
    # 死亡信息
    death_cause: str = ""                 # "killed" / "voted_out" / "poisoned" / ""
    death_round: int = 0

    def to_public_dict(self, reveal_role: bool = False) -> dict:
        d = {
            "id": self.player_id,
            "display_name": self.display_name,
            "role_name": self.role_name if reveal_role or not self.is_alive else "???",
            "team": self.team.value if (reveal_role or not self.is_alive) and self.team else None,
            "spectator_role_name": self.role_name,
            "spectator_team": self.team.value if self.team else None,
            "is_alive": self.is_alive,
            "is_sheriff": self.is_sheriff,
            "has_voted": self.has_voted,
            "vote_target": self.vote_target,
            "seat_index": self.seat_index,
            "avatar_url": self.avatar_url,
            "speech_count": len(self.speech_history),
            "death_cause": self.death_cause,
        }
        return d


# ============================================================
# 游戏状态
# ============================================================

@dataclass
class WerewolfGameState:
    """狼人杀游戏状态"""
    tournament_id: str
    game_type: str = "werewolf"
    round_number: int = 0
    phase: WerewolfPhase = WerewolfPhase.ROLE_ASSIGN
    players: list[WerewolfPlayerState] = field(default_factory=list)
    # 夜晚信息
    night_kill_target: str | None = None       # 狼人刀口
    night_check_result: dict | None = None     # 预言家查验结果 {target_id: role_name}
    night_save_target: str | None = None       # 女巫解救对象
    night_poison_target: str | None = None     # 女巫毒杀对象
    night_guard_target: str | None = None      # 守卫守护对象
    # 白天信息
    sheriff_id: str | None = None              # 警长ID
    sheriff_candidates: list[str] = field(default_factory=list)  # 警长候选人
    speaking_order: list[str] = field(default_factory=list)      # 发言顺序
    current_speaker: str | None = None         # 当前发言者
    # 投票信息
    votes: dict[str, str] = field(default_factory=dict)  # voter_id -> target_id
    vote_result: dict | None = None            # 投票结果
    sheriff_vote_result: dict | None = None    # 警长竞选投票结果
    # 事件日志
    events: list[dict] = field(default_factory=list)
    night_log: list[dict] = field(default_factory=list)  # 夜晚行动记录
    is_over: bool = False
    winner_team: str | None = None             # "werewolf" / "villager"

    def to_public_dict(self) -> dict:
        """序列化为前端可用的字典"""
        return {
            "tournament_id": self.tournament_id,
            "game_type": self.game_type,
            "round_number": self.round_number,
            "phase": self.phase.value,
            "players": [p.to_public_dict() for p in self.players],
            "sheriff_id": self.sheriff_id,
            "sheriff_candidates": self.sheriff_candidates,
            "speaking_order": self.speaking_order,
            "current_speaker": self.current_speaker,
            "night_kill_target": self.night_kill_target,
            "votes": {k: v for k, v in self.votes.items()},
            "vote_result": self.vote_result,
            "sheriff_vote_result": self.sheriff_vote_result,
            "events": self.events[-30:],
            "night_log": self.night_log[-20:],
            "is_over": self.is_over,
            "winner_team": self.winner_team,
        }

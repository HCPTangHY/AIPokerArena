"""AI 4X Arena — 4X 文明游戏数据模型

基于 point-to-point 地图拓扑（Here I Stand 风格），
Stellaris 的帝国特质系统，Civ 的科技树和胜利条件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ============================================================
# 枚举
# ============================================================

class CivTerrain(str, Enum):
    PLAINS = "plains"
    FOREST = "forest"
    MOUNTAIN = "mountain"
    DESERT = "desert"
    TUNDRA = "tundra"
    WATER = "water"
    HILL = "hill"


class CivResource(str, Enum):
    FOOD = "food"
    PRODUCTION = "production"
    SCIENCE = "science"
    GOLD = "gold"
    CULTURE = "culture"


class CivStrategicResource(str, Enum):
    IRON = "iron"
    HORSES = "horses"
    CRYSTAL = "crystal"
    URANIUM = "uranium"


class CivTrait(str, Enum):
    """帝国特质 — 正面特质"""
    MILITARIST = "militarist"          # 军事 +30%
    COMMERCIAL = "commercial"          # 金币 +30%
    SCIENTIFIC = "scientific"          # 科研 +30%
    INDUSTRIOUS = "industrious"        # 产能 +30%
    AGRARIAN = "agrarian"              # 粮食 +30%
    DIPLOMATIC = "diplomatic"          # 外交权重 +1
    EXPANSIONIST = "expansionist"      # 移民成本 -20%
    SPIRITUAL = "spiritual"            # 文化 +30%


class CivNegativeTrait(str, Enum):
    """帝国特质 — 负面特质（选一个）"""
    DECADENT = "decadent"              # 金币 -20%
    INSULAR = "insular"                # 外交权重 -1
    FRAGILE = "fragile"                # 防御 -20%
    SLOW_LEARNERS = "slow_learners"    # 科研 -20%
    BARREN = "barren"                  # 粮食 -20%


class CivGovernment(str, Enum):
    DEMOCRACY = "democracy"            # 快乐度 +1，战争惩罚 +50%
    OLIGARCHY = "oligarchy"            # 金币 +15%
    AUTOCRACY = "autocracy"            # 军事 +20%，科研 -10%
    HIVE_MIND = "hive_mind"            # 产能 +20%，外交 -50%


class CivVictoryType(str, Enum):
    DOMINATION = "domination"          # 制霸 — 占领 60% 地图
    SCIENCE = "science"                # 科技 — 完成终极科技
    DIPLOMATIC = "diplomatic"          # 外交 — 世界议会 2/3 票
    SCORE = "score"                    # 分数 — 回合截止最高分


class CivBuildings(str, Enum):
    GRANARY = "granary"
    BARRACKS = "barracks"
    LIBRARY = "library"
    MARKET = "market"
    TEMPLE = "temple"
    FACTORY = "factory"
    FORTRESS = "fortress"
    UNIVERSITY = "university"
    BANK = "bank"
    WONDER = "wonder"


class CivTechCategory(str, Enum):
    MILITARY = "military"
    ECONOMY = "economy"
    CULTURE = "culture"


class CivPhase(str, Enum):
    EMPIRE_CREATION = "empire_creation"    # 开局创建文明
    ACTION = "action"                      # 策略阶段
    DIPLOMACY = "diplomacy"                # 外交阶段
    RESOLUTION = "resolution"              # 结算阶段
    CRISIS = "crisis"                      # 终局危机
    GAME_OVER = "game_over"


# ============================================================
# 数据类
# ============================================================

@dataclass
class CivMapNode:
    """地图节点"""
    id: str
    name: str
    terrain: CivTerrain = CivTerrain.PLAINS
    # 基础产出
    base_food: int = 2
    base_production: int = 2
    base_science: int = 0
    base_gold: int = 0
    base_culture: int = 0
    # 战略资源
    strategic_resource: str | None = None
    # 拓扑
    connections: list[str] = field(default_factory=list)
    # 占领信息
    owner_id: str | None = None
    garrison: int = 0
    buildings: list[str] = field(default_factory=list)
    wonder: str | None = None
    # 特殊
    is_capital: bool = False
    defense_bonus: float = 1.0
    note: str = ""   # 如 "chokepoint — only route to Gemini"

    def effective_food(self) -> int:
        return self.base_food + (1 if CivBuildings.GRANARY.value in self.buildings else 0)

    def effective_production(self) -> int:
        return self.base_production + (1 if CivBuildings.FACTORY.value in self.buildings else 0)

    def effective_science(self) -> int:
        s = self.base_science
        if CivBuildings.LIBRARY.value in self.buildings:
            s += 1
        if CivBuildings.UNIVERSITY.value in self.buildings:
            s += 2
        return s

    def effective_gold(self) -> int:
        g = self.base_gold
        if CivBuildings.MARKET.value in self.buildings:
            g += 2
        if CivBuildings.BANK.value in self.buildings:
            g += 2
        return g

    def effective_culture(self) -> int:
        c = self.base_culture
        if CivBuildings.TEMPLE.value in self.buildings:
            c += 1
        return c


@dataclass
class CivTech:
    """科技定义"""
    id: str
    name: str
    category: CivTechCategory
    cost: int  # 科研点数
    prerequisites: list[str] = field(default_factory=list)
    effect: str = ""  # 自然语言描述
    unlocks_buildings: list[str] = field(default_factory=list)
    military_bonus: float = 0.0


@dataclass
class CivPlayerState:
    """玩家状态"""
    player_id: str
    display_name: str
    # 文明信息
    empire_name: str = ""
    leader_name: str = ""
    traits: list[str] = field(default_factory=list)
    negative_trait: str = ""
    government: str = CivGovernment.DEMOCRACY.value
    victory_goal: str = ""
    backstory: str = ""  # AI 自己写的背景故事
    # 全局资源
    food: float = 0.0
    production: float = 0.0
    science: float = 0.0
    gold: float = 0.0
    culture: float = 0.0
    # 领土
    controlled_nodes: list[str] = field(default_factory=list)
    capital_node_id: str = ""
    # 军事
    total_army: int = 0
    army_deployment: dict[str, int] = field(default_factory=dict)  # node_id -> troop count
    # 科技
    tech_researched: list[str] = field(default_factory=list)
    tech_current: str | None = None
    tech_progress: float = 0.0
    # 外交
    diplomatic_weight: int = 1
    treaties: dict[str, list[str]] = field(default_factory=dict)  # player_id -> [treaty types]
    # 状态
    is_alive: bool = True
    is_eliminated: bool = False
    seat_index: int = 0
    avatar_url: str = ""

    def resource_income(self, nodes: dict[str, CivMapNode]) -> dict[str, float]:
        """计算每回合资源净收入"""
        income = {"food": 0.0, "production": 0.0, "science": 0.0, "gold": 0.0, "culture": 0.0}
        for nid in self.controlled_nodes:
            node = nodes.get(nid)
            if not node:
                continue
            income["food"] += node.effective_food()
            income["production"] += node.effective_production()
            income["science"] += node.effective_science()
            income["gold"] += node.effective_gold()
            income["culture"] += node.effective_culture()
        # 应用特质加成
        for t in self.traits:
            if t == CivTrait.AGRARIAN.value:
                income["food"] *= 1.3
            elif t == CivTrait.INDUSTRIOUS.value:
                income["production"] *= 1.3
            elif t == CivTrait.SCIENTIFIC.value:
                income["science"] *= 1.3
            elif t == CivTrait.COMMERCIAL.value:
                income["gold"] *= 1.3
            elif t == CivTrait.SPIRITUAL.value:
                income["culture"] *= 1.3
        if self.negative_trait == CivNegativeTrait.BARREN.value:
            income["food"] *= 0.8
        if self.negative_trait == CivNegativeTrait.DECADENT.value:
            income["gold"] *= 0.8
        if self.negative_trait == CivNegativeTrait.SLOW_LEARNERS.value:
            income["science"] *= 0.8
        # 政体修正
        if self.government == CivGovernment.OLIGARCHY.value:
            income["gold"] *= 1.15
        elif self.government == CivGovernment.AUTOCRACY.value:
            income["production"] *= 1.10
        elif self.government == CivGovernment.HIVE_MIND.value:
            income["production"] *= 1.20
        # 军队维护费
        income["gold"] -= self.total_army * 0.5
        return income


@dataclass
class CivGameState:
    """4X 游戏状态（发给前端广播用）"""
    tournament_id: str
    game_type: str = "civ"
    turn: int = 0
    max_turns: int = 60
    players: list[dict] = field(default_factory=list)  # 公开摘要
    map_summary: dict[str, dict] = field(default_factory=dict)  # 地图公开信息
    phase: str = CivPhase.EMPIRE_CREATION.value
    events: list[dict] = field(default_factory=list)
    crisis_active: bool = False
    crisis_type: str = ""
    world_council_votes: dict[str, int] = field(default_factory=dict)
    is_over: bool = False
    winner: dict | None = None

    def to_public_dict(self) -> dict:
        """序列化为前端可用的字典"""
        return {
            "tournament_id": self.tournament_id,
            "game_type": self.game_type,
            "turn": self.turn,
            "max_turns": self.max_turns,
            "players": self.players,
            "map_summary": self.map_summary,
            "phase": self.phase,
            "events": self.events[-30:],
            "crisis_active": self.crisis_active,
            "crisis_type": self.crisis_type,
            "world_council_votes": self.world_council_votes,
            "is_over": self.is_over,
            "winner": self.winner,
        }


# ============================================================
# 科技树定义
# ============================================================

CIV_TECH_TREE: list[CivTech] = [
    # ---- Tier 0 (开局已有) ----
    CivTech("agriculture", "农业", CivTechCategory.ECONOMY, 0),
    CivTech("mining", "采矿", CivTechCategory.ECONOMY, 0),
    CivTech("writing", "文字", CivTechCategory.CULTURE, 0),
    # ---- Tier 1 ----
    CivTech("pottery", "制陶", CivTechCategory.ECONOMY, 20, ["agriculture"],
            unlocks_buildings=["granary"]),
    CivTech("animal_husbandry", "畜牧", CivTechCategory.ECONOMY, 25, ["agriculture"]),
    CivTech("bronze_working", "青铜器", CivTechCategory.MILITARY, 30, ["mining"],
            unlocks_buildings=["barracks"], military_bonus=0.15),
    CivTech("mysticism", "神秘论", CivTechCategory.CULTURE, 20, ["writing"],
            unlocks_buildings=["temple"]),
    # ---- Tier 2 ----
    CivTech("iron_working", "铁器", CivTechCategory.MILITARY, 50, ["bronze_working"],
            unlocks_buildings=["fortress"], military_bonus=0.25),
    CivTech("currency", "货币", CivTechCategory.ECONOMY, 45, ["pottery"],
            unlocks_buildings=["market"]),
    CivTech("philosophy", "哲学", CivTechCategory.CULTURE, 45, ["mysticism"],
            unlocks_buildings=["library"]),
    CivTech("horseback_riding", "骑术", CivTechCategory.MILITARY, 40, ["animal_husbandry"],
            military_bonus=0.15),
    # ---- Tier 3 ----
    CivTech("education", "教育", CivTechCategory.CULTURE, 80, ["philosophy"],
            unlocks_buildings=["university"]),
    CivTech("machinery", "机械", CivTechCategory.ECONOMY, 90, ["iron_working", "currency"],
            unlocks_buildings=["factory"]),
    CivTech("gunpowder", "火药", CivTechCategory.MILITARY, 100, ["iron_working"],
            military_bonus=0.30),
    CivTech("banking", "银行", CivTechCategory.ECONOMY, 85, ["currency", "education"],
            unlocks_buildings=["bank"]),
    # ---- Tier 4 ----
    CivTech("industrialization", "工业化", CivTechCategory.ECONOMY, 140, ["machinery"],
            effect="产能+50%，可在任意地形建工厂"),
    CivTech("rifling", "膛线", CivTechCategory.MILITARY, 150, ["gunpowder"],
            military_bonus=0.40),
    CivTech("scientific_method", "科学方法", CivTechCategory.CULTURE, 130, ["education"],
            effect="科研+50%"),
    # ---- Tier 5 (终极) ----
    CivTech("advanced_ai", "高级AI", CivTechCategory.CULTURE, 200, ["scientific_method", "industrialization"],
            effect="【终极科技—科技胜利解锁】"),
    CivTech("nuclear_fusion", "核聚变", CivTechCategory.MILITARY, 220, ["rifling", "industrialization"],
            effect="军事+80%，解锁终局武器", military_bonus=0.80),
    CivTech("globalization", "全球化", CivTechCategory.ECONOMY, 200, ["banking", "industrialization"],
            effect="金币+100%，外交权重+2"),
]


@dataclass
class CivConfig:
    """游戏配置"""
    game_type: str = "civ"
    name: str = "AI 4X Civilization Showdown"
    max_players: int = 6
    max_turns: int = 60
    map_nodes: int = 25
    map_seed: int | None = None
    crisis_trigger_turn: int = 45
    action_timeout_seconds: int = 120
    # 胜利条件阈值
    domination_pct: float = 0.60
    diplomatic_votes_pct: float = 0.667

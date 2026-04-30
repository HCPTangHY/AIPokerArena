"""AI 4X Arena — 文明游戏引擎

继承 game_base.GameEngine，实现完整的 4X 回合制逻辑。
地图基于 point-to-point 拓扑图，LLM 无需空间推理。
"""

from __future__ import annotations

import random
from typing import Any

from app.core.game_base import GameEngine, BaseGameState, BasePlayerState
from app.core.game_registry import register_game
from app.models.civ import (
    CivConfig, CivGameState, CivPlayerState, CivMapNode,
    CivPhase, CivTerrain, CivResource, CivStrategicResource,
    CivTrait, CivNegativeTrait, CivGovernment, CivVictoryType,
    CivBuildings, CIV_TECH_TREE,
)


# ============================================================
# 地图生成
# ============================================================

DEFAULT_MAP_TOPOLOGY: dict[str, list[str]] = {
    # 西北大陆
    "frost_peak": ["iron_ridge", "pine_forest"],
    "iron_ridge": ["frost_peak", "pine_forest", "central_plains"],
    "pine_forest": ["frost_peak", "iron_ridge", "northern_crossing"],
    "northern_crossing": ["pine_forest", "central_plains", "western_coast"],
    "western_coast": ["northern_crossing", "gold_delta"],
    "gold_delta": ["western_coast", "central_plains", "southern_sea"],
    # 中央大陆
    "central_plains": ["iron_ridge", "northern_crossing", "gold_delta", "canyon_pass", "great_river", "ancient_ruins"],
    "canyon_pass": ["central_plains", "eastern_steppe"],
    "great_river": ["central_plains", "fertile_valley", "eastern_steppe"],
    "ancient_ruins": ["central_plains", "fertile_valley", "obsidian_peak"],
    # 东部大陆
    "eastern_steppe": ["canyon_pass", "great_river", "sunrise_plains", "gem_depths"],
    "fertile_valley": ["great_river", "ancient_ruins", "sunrise_plains", "gem_depths"],
    "sunrise_plains": ["eastern_steppe", "fertile_valley", "eastern_coast"],
    "gem_depths": ["eastern_steppe", "fertile_valley", "obsidian_peak"],
    "eastern_coast": ["sunrise_plains", "southern_sea"],
    # 南部
    "southern_sea": ["gold_delta", "eastern_coast", "storm_isles"],
    "storm_isles": ["southern_sea"],
    "obsidian_peak": ["ancient_ruins", "gem_depths", "volcanic_rift"],
    "volcanic_rift": ["obsidian_peak"],
}

DEFAULT_MAP_NODES: dict[str, dict] = {
    "frost_peak": {"name": "冰封高原", "terrain": CivTerrain.TUNDRA, "base_food": 1, "base_production": 3, "base_gold": 1, "note": "北方门户"},
    "iron_ridge": {"name": "铁矿岭", "terrain": CivTerrain.MOUNTAIN, "base_production": 5, "base_food": 1, "strategic_resource": CivStrategicResource.IRON.value, "defense_bonus": 1.5, "note": "唯一铁矿"},
    "pine_forest": {"name": "松树林", "terrain": CivTerrain.FOREST, "base_food": 3, "base_production": 3, "base_culture": 1},
    "northern_crossing": {"name": "北十字关", "terrain": CivTerrain.HILL, "base_production": 3, "defense_bonus": 1.3, "note": "南北要道"},
    "western_coast": {"name": "西海岸", "terrain": CivTerrain.PLAINS, "base_food": 3, "base_gold": 2, "base_culture": 1},
    "gold_delta": {"name": "黄金三角洲", "terrain": CivTerrain.PLAINS, "base_food": 5, "base_gold": 4, "base_production": 1},
    "central_plains": {"name": "中央平原", "terrain": CivTerrain.PLAINS, "base_food": 4, "base_production": 3, "note": "枢纽中心"},
    "canyon_pass": {"name": "峡谷关隘", "terrain": CivTerrain.MOUNTAIN, "base_production": 2, "defense_bonus": 2.0, "note": "东西唯一通道"},
    "great_river": {"name": "大河谷", "terrain": CivTerrain.PLAINS, "base_food": 5, "base_gold": 2, "base_culture": 1},
    "ancient_ruins": {"name": "遗迹之地", "terrain": CivTerrain.DESERT, "base_science": 2, "base_culture": 3, "note": "奇观所在地"},
    "eastern_steppe": {"name": "东方草原", "terrain": CivTerrain.PLAINS, "base_food": 3, "base_production": 2, "base_gold": 1, "strategic_resource": CivStrategicResource.HORSES.value},
    "fertile_valley": {"name": "丰饶谷地", "terrain": CivTerrain.FOREST, "base_food": 6, "base_production": 2},
    "sunrise_plains": {"name": "旭日平原", "terrain": CivTerrain.PLAINS, "base_food": 4, "base_production": 3, "base_science": 1},
    "gem_depths": {"name": "宝石深渊", "terrain": CivTerrain.MOUNTAIN, "base_production": 3, "base_gold": 4, "strategic_resource": CivStrategicResource.CRYSTAL.value, "note": "唯一水晶"},
    "eastern_coast": {"name": "东海湾", "terrain": CivTerrain.PLAINS, "base_food": 3, "base_gold": 3, "base_culture": 1},
    "southern_sea": {"name": "南方海岸", "terrain": CivTerrain.PLAINS, "base_food": 3, "base_gold": 2, "note": "连接岛屿的跳板"},
    "storm_isles": {"name": "风暴群岛", "terrain": CivTerrain.WATER, "base_science": 3, "base_culture": 2, "strategic_resource": CivStrategicResource.URANIUM.value, "note": "唯一铀矿，终局关键"},
    "obsidian_peak": {"name": "黑曜石峰", "terrain": CivTerrain.MOUNTAIN, "base_production": 4, "base_science": 1, "defense_bonus": 1.8},
    "volcanic_rift": {"name": "火山裂隙", "terrain": CivTerrain.DESERT, "base_production": 3, "base_science": 2, "base_food": 0, "note": "危机事件起点"},
}


def generate_map(seed: int | None = None) -> dict[str, CivMapNode]:
    """生成地图节点"""
    rng = random.Random(seed)
    nodes: dict[str, CivMapNode] = {}
    for node_id, props in DEFAULT_MAP_NODES.items():
        connections = DEFAULT_MAP_TOPOLOGY.get(node_id, [])
        nodes[node_id] = CivMapNode(
            id=node_id,
            name=props.get("name", node_id),
            terrain=props.get("terrain", CivTerrain.PLAINS),
            base_food=props.get("base_food", 2),
            base_production=props.get("base_production", 2),
            base_science=props.get("base_science", 0),
            base_gold=props.get("base_gold", 0),
            base_culture=props.get("base_culture", 0),
            strategic_resource=props.get("strategic_resource"),
            connections=connections,
            defense_bonus=props.get("defense_bonus", 1.0),
            note=props.get("note", ""),
        )
    # 稍微随机化产出（±1 但不少于 0）
    for n in nodes.values():
        n.base_food = max(0, n.base_food + rng.randint(-1, 1))
        n.base_production = max(0, n.base_production + rng.randint(-1, 1))
        n.base_gold = max(0, n.base_gold + rng.randint(-1, 1))
        n.base_science = max(0, n.base_science + rng.randint(-1, 1))
        n.base_culture = max(0, n.base_culture + rng.randint(-1, 1))
    return nodes


# ============================================================
# 行动解析
# ============================================================

import json
import re


def parse_civ_action(raw_text: str) -> list[dict]:
    """从 LLM 回复中提取 JSON 行动列表"""
    # 尝试直接 json.loads
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict) and "actions" in data:
            return data.get("actions", [])
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    # 尝试从代码块中提取
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict) and "actions" in data:
                return data.get("actions", [])
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    # 尝试找 JSON 对象
    match = re.search(r'\{[^{]*"actions"[^}]*\}', raw_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return data.get("actions", [])
        except json.JSONDecodeError:
            pass
    return []


# ============================================================
# 游戏引擎
# ============================================================

class CivEngine(GameEngine):
    """4X 文明游戏引擎"""

    game_type: str = "civ"

    def __init__(self, config: CivConfig, players: list[dict]):
        super().__init__(config, players)
        self.config: CivConfig = config
        self.turn: int = 0
        self.max_turns: int = config.max_turns
        self.players: dict[str, CivPlayerState] = {}
        self.nodes: dict[str, CivMapNode] = {}
        self.events: list[dict] = []
        self.diplomatic_inboxes: dict[str, list[dict]] = {}
        self.crisis_active: bool = False
        self.crisis_type: str = ""
        self.treaties: dict[str, list[tuple[str, str, str]]] = {}  # player -> [(target, type, proposer)]
        self.war_declarations: set[tuple[str, str]] = set()  # (attacker, defender)
        self.world_council_votes: dict[str, int] = {}
        self.winner: dict | None = None

    def _add_event(self, category: str, text: str, turn: int | None = None):
        self.events.append({
            "category": category,
            "text": text,
            "turn": turn if turn is not None else self.turn,
        })

    # ============================================================
    # GameEngine 接口
    # ============================================================

    def start_game(self) -> BaseGameState:
        self.nodes = generate_map(self.config.map_seed)
        self.turn = 0
        self.is_running = True
        return self.get_state()

    def apply_action(self, action: Any) -> BaseGameState:
        return self.get_state()

    def get_state(self) -> BaseGameState:
        state = CivGameState(
            tournament_id=self.tournament_id,
            game_type="civ",
            turn=self.turn,
            max_turns=self.max_turns,
            players=[p.__dict__ for p in self.players.values()],
            map_summary=self._map_summary(),
            phase=CivPhase.ACTION.value,
            events=self.events[:],
            crisis_active=self.crisis_active,
            crisis_type=self.crisis_type,
            world_council_votes=self.world_council_votes,
            is_over=self.is_game_over(),
            winner=self.winner,
        )
        # 包装成 BaseGameState 兼容格式
        base = BaseGameState(
            tournament_id=state.tournament_id,
            game_type=state.game_type,
            round_number=state.turn,
            players=[
                BasePlayerState(player_id=p.player_id, display_name=p.display_name,
                                is_alive=p.is_alive, seat_index=p.seat_index,
                                avatar_url=p.avatar_url)
                for p in self.players.values()
            ],
            phase=state.phase,
            events=state.events[-30:],
            is_over=state.is_over,
        )
        return base

    def is_game_over(self) -> bool:
        if self.winner is not None:
            return True
        if self.turn >= self.max_turns:
            self._determine_score_winner()
            return True
        # 检查制霸胜利
        for p in self.players.values():
            if len(p.controlled_nodes) >= len(self.nodes) * self.config.domination_pct:
                self.winner = {"player_id": p.player_id, "display_name": p.display_name,
                               "victory_type": "domination"}
                self._add_event("world", f"**{p.empire_name}** 通过制霸获得胜利！")
                return True
        return False

    def get_winner(self) -> dict | None:
        return self.winner

    # ============================================================
    # 回合执行
    # ============================================================

    def get_player_state(self, player_id: str) -> CivPlayerState | None:
        return self.players.get(player_id)

    def get_diplomatic_inbox(self, player_id: str) -> list[dict]:
        return self.diplomatic_inboxes.get(player_id, [])

    def get_available_techs(self, player: CivPlayerState) -> list[dict]:
        """获取玩家当前可研发的科技"""
        available = []
        for t in CIV_TECH_TREE:
            if t.id in player.tech_researched or t.id == player.tech_current:
                continue
            if all(p in player.tech_researched for p in t.prerequisites):
                available.append({
                    "id": t.id, "name": t.name, "cost": t.cost,
                    "prerequisites": t.prerequisites,
                    "unlocks_buildings": t.unlocks_buildings,
                    "military_bonus": t.military_bonus,
                    "effect": t.effect,
                })
        return available

    def _map_summary(self) -> dict[str, dict]:
        """地图公开信息摘要"""
        summary = {}
        for nid, node in self.nodes.items():
            owner_name = "无主"
            for p in self.players.values():
                if node.owner_id == p.player_id:
                    owner_name = p.empire_name
                    break
            summary[nid] = {
                "name": node.name,
                "terrain": node.terrain.value,
                "owner": owner_name,
                "connections": node.connections,
                "is_capital": node.is_capital,
                "wonder": node.wonder,
            }
        return summary

    def execute_turn(self, player_actions: dict[str, list[dict]]) -> list[dict]:
        """执行一个完整回合。player_actions: {player_id: [action_dicts]}
        返回本回合事件列表
        """
        self.turn += 1
        turn_events: list[dict] = []

        # 终局危机检查
        if self.turn >= self.config.crisis_trigger_turn and not self.crisis_active:
            self._trigger_crisis()
            turn_events.append({"category": "world", "text": f"⚠️ 终局危机激活：{self.crisis_type}", "turn": self.turn})

        # 先处理外交消息（消息传递）
        for pid, actions in player_actions.items():
            player = self.players.get(pid)
            if not player or not player.is_alive:
                continue
            for action in actions:
                if action.get("type") == "send_message":
                    target = action.get("to", "")
                    msg = action.get("message", "")
                    if target in self.diplomatic_inboxes:
                        self.diplomatic_inboxes[target].append({
                            "from": player.empire_name,
                            "from_id": pid,
                            "message": msg,
                            "turn": self.turn,
                        })
                    turn_events.append({"category": "diplomacy", "text": f"📨 {player.empire_name} → {target}: {msg[:80]}...", "turn": self.turn})
                elif action.get("type") == "world_speech":
                    msg = action.get("message", "")
                    turn_events.append({"category": "diplomacy", "text": f"🌍 {player.empire_name} 在世界议会发表演说: {msg[:100]}...", "turn": self.turn})

        # 处理经济/扩张/军事行动
        for pid, actions in player_actions.items():
            player = self.players.get(pid)
            if not player or not player.is_alive:
                continue
            income = player.resource_income(self.nodes)
            player.food += income["food"]
            player.production += income["production"]
            player.science += income["science"]
            player.gold += income["gold"]
            player.culture += income["culture"]

            # 科研进度
            if player.tech_current:
                player.tech_progress += max(0, income["science"])
                tech_def = next((t for t in CIV_TECH_TREE if t.id == player.tech_current), None)
                if tech_def and player.tech_progress >= tech_def.cost:
                    player.tech_researched.append(player.tech_current)
                    player.tech_progress = 0
                    player.tech_current = None
                    turn_events.append({"category": "tech", "text": f"🔬 {player.empire_name} 完成了 **{tech_def.name}** 的研究！", "turn": self.turn})
                    # 科技胜利检查
                    if player.tech_current in ("advanced_ai",) and "advanced_ai" in player.tech_researched:
                        self.winner = {"player_id": pid, "display_name": player.display_name,
                                       "victory_type": "science"}
                        turn_events.append({"category": "world", "text": f"🎉 **{player.empire_name}** 通过科技获得胜利！"})

            for action in actions:
                atype = action.get("type", "")
                if atype == "research":
                    tech_id = action.get("tech", "")
                    if tech_id and tech_id not in player.tech_researched and tech_id != player.tech_current:
                        player.tech_current = tech_id
                        player.tech_progress = 0
                        turn_events.append({"category": "tech", "text": f"🔬 {player.empire_name} 开始研发 {tech_id}"})
                elif atype == "recruit":
                    node_id = action.get("node", "")
                    amount = min(action.get("amount", 1), 5)
                    cost = amount * 10
                    if node_id in player.controlled_nodes and player.production >= cost:
                        player.production -= cost
                        player.total_army += amount
                        player.army_deployment[node_id] = player.army_deployment.get(node_id, 0) + amount
                        turn_events.append({"category": "military", "text": f"⚔️ {player.empire_name} 在 {self.nodes[node_id].name} 招募 {amount} 兵力"})
                elif atype == "settle":
                    node_id = action.get("node", "")
                    if node_id in self.nodes and self.nodes[node_id].owner_id is None and player.production >= 30:
                        player.production -= 30
                        self.nodes[node_id].owner_id = pid
                        player.controlled_nodes.append(node_id)
                        player.army_deployment[node_id] = 1
                        if not player.capital_node_id:
                            player.capital_node_id = node_id
                            self.nodes[node_id].is_capital = True
                        turn_events.append({"category": "expansion", "text": f"🏙️ {player.empire_name} 在 **{self.nodes[node_id].name}** 建立了殖民地"})
                elif atype == "build":
                    node_id = action.get("node", "")
                    building = action.get("building", "")
                    cost = 20
                    if node_id in player.controlled_nodes and player.production >= cost:
                        if building not in self.nodes[node_id].buildings:
                            player.production -= cost
                            self.nodes[node_id].buildings.append(building)
                            turn_events.append({"category": "economy", "text": f"🏗️ {player.empire_name} 在 {self.nodes[node_id].name} 建造了 {building}"})
                elif atype == "attack":
                    from_node = action.get("from", "")
                    to_node = action.get("to", "")
                    if from_node in player.controlled_nodes and to_node in self.nodes:
                        if self.nodes[to_node].owner_id == pid:
                            continue  # 不能打自己
                        attacker_power = player.army_deployment.get(from_node, 0) * self._calculate_military_bonus(player)
                        defender = next((p for p in self.players.values() if p.player_id == self.nodes[to_node].owner_id), None)
                        defender_power = 0
                        if defender:
                            defender_power = defender.army_deployment.get(to_node, 0) * self._calculate_military_bonus(defender)
                        defender_power *= self.nodes[to_node].defense_bonus
                        if attacker_power > defender_power * 1.2:  # 需要 20% 优势
                            # 进攻成功
                            old_owner = self.nodes[to_node].owner_id
                            old_army = player.army_deployment.get(from_node, 0)
                            losses = max(1, int(old_army * 0.3))
                            player.army_deployment[from_node] = max(0, old_army - losses)
                            player.total_army = max(0, player.total_army - losses)
                            self.nodes[to_node].owner_id = pid
                            player.controlled_nodes.append(to_node)
                            player.army_deployment[to_node] = max(1, old_army - losses)
                            if old_owner and old_owner != pid:
                                old = self.players.get(old_owner)
                                if old and to_node in old.controlled_nodes:
                                    old.controlled_nodes.remove(to_node)
                            turn_events.append({"category": "war", "text": f"⚔️ {player.empire_name} 攻占了 {self.nodes[to_node].name}!"})
                        else:
                            losses = max(1, int(player.army_deployment.get(from_node, 0) * 0.5))
                            player.army_deployment[from_node] = max(0, player.army_deployment.get(from_node, 0) - losses)
                            player.total_army = max(0, player.total_army - losses)
                            turn_events.append({"category": "war", "text": f"🛡️ {player.empire_name} 对 {self.nodes[to_node].name} 的进攻被击退了"})

        self.events.extend(turn_events)

        # 清空外交收件箱（消息已投递）
        for pid in self.players:
            if pid in self.diplomatic_inboxes:
                self.diplomatic_inboxes[pid] = [
                    m for m in self.diplomatic_inboxes[pid] if m.get("turn", 0) >= self.turn - 1
                ]

        return turn_events

    def _calculate_military_bonus(self, player: CivPlayerState) -> float:
        """计算军事加成"""
        bonus = 1.0
        if CivTrait.MILITARIST.value in player.traits:
            bonus += 0.30
        if player.government == CivGovernment.AUTOCRACY.value:
            bonus += 0.20
        for tid in player.tech_researched:
            for t in CIV_TECH_TREE:
                if t.id == tid:
                    bonus += t.military_bonus
        if player.negative_trait == CivNegativeTrait.FRAGILE.value:
            bonus *= 0.80
        return max(bonus, 0.1)

    def _trigger_crisis(self):
        self.crisis_active = True
        self.crisis_type = "外星入侵 — 虚空裂隙在火山裂隙打开，每回合从 fissure_spawn 节点向周围扩张"
        self._add_event("world", "🌋 终局危机：虚空裂隙在火山裂隙打开！不合作全灭。")

    def _determine_score_winner(self):
        best_score = -1
        best_player = None
        for p in self.players.values():
            score = (len(p.controlled_nodes) * 10 + p.total_army * 2 +
                     len(p.tech_researched) * 5 + p.culture)
            if score > best_score:
                best_score = score
                best_player = p
        if best_player:
            self.winner = {"player_id": best_player.player_id, "display_name": best_player.display_name,
                           "victory_type": "score", "score": best_score}
            self._add_event("world", f"🏆 **{best_player.empire_name}** 以 {best_score:.0f} 分赢得分数胜利！")

    def register_empire(self, player_id: str, config: dict) -> CivPlayerState:
        """根据 AI 创建帝国的配置注册玩家"""
        player = CivPlayerState(
            player_id=player_id,
            display_name=config.get("display_name", player_id),
            empire_name=config.get("empire_name", f"{player_id}帝国"),
            leader_name=config.get("leader_name", f"{player_id}大帝"),
            traits=config.get("traits", []),
            negative_trait=config.get("negative_trait", ""),
            government=config.get("government", CivGovernment.DEMOCRACY.value),
            victory_goal=config.get("victory_goal", "score"),
            backstory=config.get("backstory", ""),
            food=50,
            production=50,
            science=0,
            gold=50,
            culture=0,
            seat_index=config.get("seat_index", 0),
            avatar_url=config.get("avatar_url", ""),
        )
        self.players[player_id] = player
        self.diplomatic_inboxes[player_id] = []
        return player

    def assign_starting_node(self, player_id: str, node_id: str):
        """给玩家分配起始领土"""
        player = self.players.get(player_id)
        if not player or node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        node.owner_id = player_id
        node.is_capital = True
        player.controlled_nodes = [node_id]
        player.capital_node_id = node_id
        player.army_deployment[node_id] = 3
        player.total_army = 3

    def list_unclaimed_nodes(self) -> list[str]:
        """列出无主节点"""
        return [nid for nid, node in self.nodes.items() if node.owner_id is None]


# 注册到游戏注册器
register_game("civ", CivEngine, CivConfig)

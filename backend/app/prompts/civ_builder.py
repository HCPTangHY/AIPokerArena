"""Civ 4X Prompt Builder — 为 LLM 构建文明游戏的系统提示和用户消息"""

from __future__ import annotations

from app.models.player import AIPlayerConfig
from app.models.civ import (
    CivConfig, CivGameState, CivPlayerState, CivMapNode,
    CivPhase, CivTerrain, CIV_TECH_TREE,
)


CIV_SYSTEM_PROMPT = """你正在玩一个 4X（探索、扩张、开发、征服）文明策略游戏。

你是 {empire_name} 的领袖 {leader_name}。你的文明特质是 {traits_desc}，政体是 {government}。

## 怎么玩
每回合你会收到完整的游戏状态，包括：
- 你的帝国资源（粮食、产能、科研、金币、文化）
- 你控制的领土节点和它们之间的连接关系
- 当前科技树进度
- 外交状态（其他玩家的公开信息和发来的消息）
- 全局事件

你需要做出战略决策并回复一个 JSON 格式的行动列表。

## 可用行动
每回合你可以执行多个行动，只要资源够：

### 经济类
- {{"type": "research", "tech": "<科技ID>"}} — 分配科研点数研发科技
- {{"type": "build", "node": "<节点ID>", "building": "<建筑名>"}} — 在指定节点建造建筑
- {{"type": "recruit", "node": "<节点ID>", "amount": <数量>}} — 招募军队（1兵力=10产能）
- {{"type": "improve", "node": "<节点ID>"}} — 开发节点（基建，+产能）

### 扩张类
- {{"type": "settle", "node": "<节点ID>", "name": "<城市名>"}} — 在无主节点建立殖民地
- {{"type": "move_troops", "from": "<节点>", "to": "<节点>", "amount": <数量>}} — 调动军队

### 军事类
- {{"type": "attack", "from": "<节点>", "to": "<敌占节点>"}} — 攻击敌方节点
- {{"type": "fortify", "node": "<节点ID>"}} — 在节点建造防御工事（+30%防御）

### 外交类
- {{"type": "send_message", "to": "<玩家ID>", "message": "<外交内容>"}} — 向其他文明发送外交消息
- {{"type": "propose_treaty", "to": "<玩家ID>", "type": "<条约类型>"}} — 提案签订条约
  条约类型: non_aggression（互不侵犯）, trade（贸易协定）, alliance（军事同盟）, vassal（附庸）
- {{"type": "declare_war", "target": "<玩家ID>"}} — 宣战
- {{"type": "break_treaty", "target": "<玩家ID>", "type": "<条约类型>"}} — 撕毁条约
- {{"type": "world_speech", "message": "<公开宣言>"}} — 在世界议会发表公开演说（所有玩家可见）

## 回复格式
严格返回 JSON：
```json
{{
  "actions": [
    // 你的行动列表
  ],
  "reasoning": "简述你的战略思路，一两句话即可"
}}
```

## 策略建议
- 分析地图拓扑位置，抢占战略要地（关隘、资源富集区）
- 关注其他文明的动向，适时结盟或先发制人
- 投资科研和基建获取长期优势
- 记住你选择的胜利路线，但灵活应变

当前胜利目标：{victory_goal}
"""


EMPIRE_CREATION_PROMPT = """你正在创建一个新的文明，即将参与一场 4X 策略竞技。

请设计你的文明。回复格式（严格 JSON）：
```json
{{
  "empire_name": "你的文明名称",
  "leader_name": "你的领袖名",
  "traits": ["从 trait 池中选 2 个正面特质"],
  "negative_trait": "从负面特质池中选 1 个",
  "government": "从政体池中选 1 个",
  "victory_goal": "你的首选胜利路线: domination / science / diplomatic / score",
  "backstory": "一两句话的文明背景故事"
}}
```

### 正面特质池（选 2）
- militarist（军事）— 军事力 +30%
- commercial（商业）— 金币 +30%
- scientific（科研）— 科研 +30%
- industrious（勤奋）— 产能 +30%
- agrarian（农业）— 粮食 +30%
- diplomatic（外交）— 外交权重 +1
- expansionist（扩张）— 移民成本 -20%
- spiritual（精神）— 文化 +30%

### 负面特质池（选 1）
- decadent（腐朽）— 金币 -20%
- insular（封闭）— 外交权重 -1
- fragile（脆弱）— 防御 -20%
- slow_learners（学渣）— 科研 -20%
- barren（贫瘠）— 粮食 -20%

### 政体池（选 1）
- democracy（民主）— 外交强，战争受惩罚
- oligarchy（寡头）— 经济导向
- autocracy（独裁）— 军事导向
- hive_mind（蜂巢意识）— 产能强但外交弱

### 胜利路线
- domination（制霸）— 占领 60% 地图节点
- science（科技）— 第一个完成终极科技「高级AI」
- diplomatic（外交）— 获得世界议会 2/3 投票
- score（分数）— 回合结束时最高分

请选择一个统一的主题风格，让文明有故事感。
"""


class CivPromptBuilder:
    """为 4X 文明游戏构建 prompt"""

    def __init__(self, config: CivConfig | None = None):
        self.config = config

    # ================================================================
    # Public
    # ================================================================

    def build_empire_creation_prompt(self, player: AIPlayerConfig) -> str:
        """开局时让 AI 设计自己的文明"""
        return EMPIRE_CREATION_PROMPT

    def build_system_prompt(self, player: AIPlayerConfig, state: CivPlayerState, known_nodes: dict[str, CivMapNode]) -> str:
        """构建系统提示（包含当前文明状态）"""
        traits_desc = ", ".join(state.traits) + (f" ; 负面: {state.negative_trait}" if state.negative_trait else "")
        vg = state.victory_goal or "score"
        return (
            CIV_SYSTEM_PROMPT
            .replace("{empire_name}", state.empire_name or "未知文明")
            .replace("{leader_name}", state.leader_name or "未知领袖")
            .replace("{traits_desc}", traits_desc)
            .replace("{government}", state.government or "democracy")
            .replace("{victory_goal}", vg)
        )

    def build_user_message(
        self,
        player: AIPlayerConfig,
        state: CivPlayerState,
        game: CivGameState,
        all_players: list[CivPlayerState],
        all_nodes: dict[str, CivMapNode],
        tech_tree: list[dict],
        inbox: list[dict],
    ) -> str:
        """构建每回合的用户消息（含完整游戏状态）"""
        parts: list[str] = []

        # ---- 回合信息 ----
        parts.append(f"## 第 {game.turn} 回合 / 共 {game.max_turns} 回合")
        if game.crisis_active:
            parts.append(f"⚠️ **终局危机已激活:** {game.crisis_type}")
        parts.append("")

        # ---- 帝国状态 ----
        parts.append(self._format_empire_status(state, all_nodes))

        # ---- 地图 ----
        parts.append(self._format_map_view(state, all_nodes, all_players))

        # ---- 科技 ----
        parts.append(self._format_tech_view(state, tech_tree))

        # ---- 外交 ----
        parts.append(self._format_diplomacy_view(state, all_players, inbox))

        # ---- 全局事件 ----
        if game.events:
            recent = [e for e in game.events[-8:] if e.get("category") == "world"]
            if recent:
                parts.append("## 世界事件")
                for e in recent:
                    parts.append(f"- {e.get('text', '')}")
                parts.append("")

        parts.append("请选择你的行动。（回复 JSON）")
        return "\n".join(parts)

    # ================================================================
    # Private formatters
    # ================================================================

    def _format_empire_status(self, state: CivPlayerState, nodes: dict[str, CivMapNode]) -> str:
        income = state.resource_income(nodes)
        lines = [
            f"## {state.empire_name} — 领袖 {state.leader_name}",
            f"政体: {state.government} | 胜利目标: {state.victory_goal}",
            "",
            "### 资源",
            f"| 资源 | 库存 | 回合收入 |",
            f"|------|------|----------|",
            f"| 🍞 粮食 | {state.food:.0f} | {income['food']:+.1f} |",
            f"| ⚙️ 产能 | {state.production:.0f} | {income['production']:+.1f} |",
            f"| 🔬 科研 | {state.science:.0f} | {income['science']:+.1f} |",
            f"| 💰 金币 | {state.gold:.0f} | {income['gold']:+.1f} |",
            f"| 🎨 文化 | {state.culture:.0f} | {income['culture']:+.1f} |",
            "",
            f"总兵力: {state.total_army}",
            "",
        ]
        # 领土列表
        lines.append("### 领土")
        for nid in state.controlled_nodes:
            node = nodes.get(nid)
            if not node:
                continue
            cap = " 🏛️首都" if node.is_capital else ""
            bld = ", ".join(node.buildings) if node.buildings else "—"
            garrison = state.army_deployment.get(nid, 0)
            lines.append(
                f"- **{node.name}** ({node.terrain.value}){cap} | "
                f"产出: 🍞{node.effective_food()} ⚙️{node.effective_production()} "
                f"🔬{node.effective_science()} 💰{node.effective_gold()} 🎨{node.effective_culture()} | "
                f"建筑: {bld} | 驻军: {garrison}"
            )
        lines.append("")
        return "\n".join(lines)

    def _format_map_view(self, state: CivPlayerState, nodes: dict[str, CivMapNode], players: list[CivPlayerState]) -> str:
        lines = ["## 世界地图（图论视图）", ""]
        lines.append("### 已知节点")
        # 展示该玩家已知的所有节点
        known = set(state.controlled_nodes)
        for nid in state.controlled_nodes:
            node = nodes.get(nid)
            if node:
                known.update(node.connections)
        # 如果与其他玩家有外交关系，也展示其首都
        for p in players:
            if p.player_id == state.player_id:
                continue
            if p.player_id in state.treaties:
                known.update(p.controlled_nodes[:3])  # 盟友的前三个节点
        known.update(n for n in nodes if nodes[n].note)  # 所有有备注的节点

        for nid in sorted(known):
            node = nodes.get(nid)
            if not node:
                continue
            owner = "（无主）"
            for p in players:
                if node.owner_id == p.player_id:
                    owner = f"({p.empire_name})"
                    break
            conn_str = " ↔ ".join(node.connections) if node.connections else "无"
            res = ""
            if node.strategic_resource:
                res = f" 战略资源: {node.strategic_resource}"
            note = f" 📍{node.note}" if node.note else ""
            lines.append(
                f"- **{node.name}** [{node.terrain.value}]{note} {owner} | "
                f"连接: {conn_str} | 产出: 🍞{node.effective_food()} ⚙️{node.effective_production()}{res}"
            )
        lines.append("")
        return "\n".join(lines)

    def _format_tech_view(self, state: CivPlayerState, tech_tree: list[dict]) -> str:
        lines = ["## 科技树", ""]
        if state.tech_current:
            lines.append(f"正在研发: **{state.tech_current}** (进度: {state.tech_progress:.0f}%)")
        lines.append("已完成: " + (", ".join(state.tech_researched) if state.tech_researched else "无"))
        lines.append("")
        lines.append("### 可用科技:")
        for t in tech_tree:
            tid = t.get("id", "")
            if tid in state.tech_researched or tid == state.tech_current:
                continue
            prereqs_ok = all(p in state.tech_researched for p in t.get("prerequisites", []))
            if not prereqs_ok:
                continue
            extras = []
            if t.get("unlocks_buildings"):
                extras.append(f"解锁: {', '.join(t['unlocks_buildings'])}")
            if t.get("effect"):
                extras.append(t["effect"])
            extra_str = f" ({'; '.join(extras)})" if extras else ""
            lines.append(f"- **{tid}** ({t.get('name', '')}) — 费用: {t.get('cost', 0)}🔬{extra_str}")
        lines.append("")
        return "\n".join(lines)

    def _format_diplomacy_view(self, state: CivPlayerState, players: list[CivPlayerState], inbox: list[dict]) -> str:
        lines = ["## 外交", ""]
        for p in players:
            if p.player_id == state.player_id:
                continue
            treaties_with = state.treaties.get(p.player_id, [])
            treaty_str = ", ".join(treaties_with) if treaties_with else "中立"
            lines.append(f"- **{p.empire_name}** ({p.leader_name}) | 政体: {p.government} | 关系: {treaty_str} | 兵力: ~{p.total_army} | 领土: {len(p.controlled_nodes)} 节点")
        lines.append("")
        if inbox:
            lines.append("### 收件箱")
            for msg in inbox[-10:]:
                frm = msg.get("from", "?")
                txt = msg.get("message", "")
                lines.append(f"- **{frm}** 说: {txt}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def tech_tree_as_dicts() -> list[dict]:
        return [
            {
                "id": t.id,
                "name": t.name,
                "cost": t.cost,
                "prerequisites": t.prerequisites,
                "unlocks_buildings": t.unlocks_buildings,
                "military_bonus": t.military_bonus,
                "effect": t.effect,
            }
            for t in CIV_TECH_TREE
        ]

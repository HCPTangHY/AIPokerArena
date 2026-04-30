"""狼人杀提示词构建器——为每个游戏阶段构建角色感知的提示词"""

from app.models.player import AIPlayerConfig
from app.core.werewolf_engine import WerewolfEngine
from app.models.werewolf import (
    ROLE_LIBRARY, RoleID, WerewolfPlayerState,
)
from app.prompts.werewolf_prompts import (
    ROLE_PROMPTS, SHERIFF_CAMPAIGN_DECISION_PROMPT, SHERIFF_SPEECH_PROMPT,
    SHERIFF_VOTE_PROMPT, SHERIFF_ORDER_PROMPT, WEREWOLF_DISCUSSION_PROMPT, WEREWOLF_KILL_DECISION_PROMPT,
    NIGHT_ACTION_PROMPT, DISCUSSION_PROMPT, VOTE_PROMPT, SHERIFF_SUCCESSOR_PROMPT,
)


class WerewolfPromptBuilder:
    """为狼人杀构建角色感知的游戏提示词。"""

    def __init__(self, engine: WerewolfEngine):
        self.engine = engine

    def build_system_prompt(self, player_config: AIPlayerConfig) -> str:
        """构建系统提示（包含角色身份）。"""
        player = self.engine._get_player(player_config.id)
        if not player or not player.role_id:
            return "你正在参加一场狼人杀游戏。"

        role_def = ROLE_LIBRARY.get(player.role_id)
        if not role_def:
            return "你正在参加一场狼人杀游戏。"

        template = ROLE_PROMPTS.get(role_def.role_id.value, "你正在参加一场狼人杀游戏。")

        # 填充上下文
        aliases = self._get_werewolf_allies(player)
        check_history = "见用户消息中的玩家视角历史信息"
        guard_history = "见用户消息中的玩家视角历史信息"
        can_save = "（还可用）" if not player.witch_save_used else "（已使用）"
        can_poison = "（还可用）" if not player.witch_poison_used else "（已使用）"

        prompt = template.format(
            werewolf_allies=aliases,
            check_history=check_history,
            guard_history=guard_history,
            can_save_info=can_save,
            can_poison_info=can_poison,
        )

        # 添加通用游戏信息
        alive_count = sum(1 for p in self.engine.players if p.is_alive)
        prompt += f"\n\n当前游戏：{alive_count}人存活，第{self.engine.round_number}轮"
        prompt += f"\n{self._format_board_info()}"
        prompt += f"\n警长：{self._get_sheriff_name() or '无'}"

        return prompt

    def build_campaign_decision_prompt(self, player_config: AIPlayerConfig) -> str:
        """构建是否参选警长的提示词。"""
        player = self.engine._get_player(player_config.id)
        if not player:
            return "是否参加警长竞选？"
        role_name = ROLE_LIBRARY[player.role_id].name if player.role_id else "未知"
        prompt = SHERIFF_CAMPAIGN_DECISION_PROMPT.format(
            player_name=self._player_ref(player),
            role_name=role_name,
        )
        return self._append_user_history(player, prompt)

    def build_sheriff_speech_prompt(self, player_config: AIPlayerConfig) -> str:
        """构建警长竞选发言提示词。"""
        player = self.engine._get_player(player_config.id)
        prompt = SHERIFF_SPEECH_PROMPT.format(player_name=self._player_ref(player) if player else "?")
        return self._append_user_history(player, prompt)

    def build_sheriff_vote_prompt(self, player_config: AIPlayerConfig) -> str:
        """构建投票选警长的提示词。"""
        player = self.engine._get_player(player_config.id)
        candidates = self.engine.get_sheriff_candidates()
        candidates_list = "\n".join(
            f"  - {self._player_ref(self.engine._get_player(cid))}" for cid in candidates
        )
        role_name = ROLE_LIBRARY[player.role_id].name if player and player.role_id else "未知"
        prompt = SHERIFF_VOTE_PROMPT.format(
            player_name=self._player_ref(player) if player else "?",
            role_name=role_name,
            candidates_list=candidates_list,
        )
        return self._append_user_history(player, prompt)

    def build_sheriff_order_prompt(self, player_config: AIPlayerConfig) -> str:
        """构建警长决定白天发言顺序的提示词。"""
        player = self.engine._get_player(player_config.id)
        alive_players = self._format_alive_players(highlight_self=player.player_id if player else "")
        prompt = SHERIFF_ORDER_PROMPT.format(
            player_name=self._player_ref(player) if player else "?",
            alive_players=alive_players,
        )
        return self._append_user_history(player, prompt)

    def build_werewolf_discussion_prompt(self, player_config: AIPlayerConfig, discussion_round: int = 1) -> str:
        """构建狼人夜间交流提示词。"""
        player = self.engine._get_player(player_config.id)
        if not player:
            return "请和同伙商议今晚的刀口。"
        allies = [self._player_ref(p) for p in self.engine.get_alive_werewolves()
                   if p.player_id != player.player_id]
        alive_players = self._format_alive_players(highlight_self=player.player_id)

        # 之前的讨论
        prev = self.engine.get_werewolf_discussion_summary()
        prev_text = f"之前的讨论：\n{prev}" if prev and "还未讨论" not in prev else ""

        # 当前投票状态
        votes = self.engine.get_werewolf_votes()
        vote_lines = []
        for wolf_id, target_id in votes.items():
            wolf = self.engine._get_player(wolf_id)
            target = self.engine._get_player(target_id)
            if wolf and target:
                marker = " ← 一致！" if self.engine.is_werewolf_consensus_reached() else ""
                vote_lines.append(f"  {self._player_ref(wolf)} → 刀 {self._player_ref(target)}{marker}")
        vote_text = "当前投票：\n" + "\n".join(vote_lines) if vote_lines else "（尚未有人投票）"

        prompt = WEREWOLF_DISCUSSION_PROMPT.format(
            player_name=self._player_ref(player),
            discussion_round=str(discussion_round),
            werewolf_allies=", ".join(allies) if allies else "（只有你一个狼人）",
            alive_players=alive_players,
            previous_discussion=prev_text,
            current_votes=vote_text,
        )
        return self._append_user_history(player, prompt)

    def build_werewolf_kill_decision_prompt(self, player_config: AIPlayerConfig, action_info: dict) -> str:
        """构建狼人刀人最终决定提示词。"""
        player = self.engine._get_player(player_config.id)
        targets = action_info.get("targets", [])
        targets_list = "\n".join(
            f"  - {self._target_ref(t)}" for t in targets
        ) if targets else "  （无有效目标）"
        discussion = action_info.get("discussion_summary", "（未讨论）")
        prompt = WEREWOLF_KILL_DECISION_PROMPT.format(
            player_name=self._player_ref(player) if player else "?",
            discussion_summary=discussion,
            targets_list=targets_list,
        )
        return self._append_user_history(player, prompt)

    def build_night_action_prompt(self, player_config: AIPlayerConfig, action_info: dict) -> str:
        """构建夜晚行动提示词。"""
        player = self.engine._get_player(player_config.id)
        if not player or not player.role_id:
            return "请做出选择。"

        role_def = ROLE_LIBRARY[player.role_id]
        targets = action_info.get("targets", [])

        alive_list = self._format_alive_players(highlight_self=player.player_id)
        targets_list = "\n".join(
            f"  - {self._target_ref(t)}" for t in targets
        ) if targets else "  （无有效目标）"

        instruction_map = {
            "kill": f"选择要刀杀的目标。可選目标：\n{targets_list}",
            "check": f"选择要查验的玩家。可選目标：\n{targets_list}",
            "save": "是否使用解药救活被杀的玩家？（目标将自动是被狼人选中的玩家）回复 'ACTION: save' 或 'ACTION: skip'",
            "poison": f"是否使用毒药？可選目标：\n{targets_list}\n回复 'ACTION: <玩家编号>' 或 'ACTION: skip'",
            "guard": f"选择要守护的玩家。可選目标：\n{targets_list}",
        }
        if action_info.get("action_type") == "witch":
            killed = action_info.get("killed_target")
            killed_text = (
                f"今晚狼人刀口是：{self._target_ref(killed)}。\n"
                if killed else
                "今晚没有有效狼人刀口。\n"
            )
            save_text = "你可以回复 `ACTION: save` 使用解药，系统会自动救刀口玩家。\n" if action_info.get("can_save") else "解药不可用或没有可救目标。\n"
            poison_text = (
                f"你也可以回复 `ACTION: poison <玩家编号>` 使用毒药。可毒目标：\n{targets_list}\n"
                if action_info.get("can_poison") else
                "毒药已使用，今晚不能毒人。\n"
            )
            instruction = (
                f"{killed_text}{save_text}{poison_text}"
                "如果不使用药，请回复 `ACTION: skip`。不要说“待会再问目标”，当前提示已经给出全部可用目标。"
            )
        else:
            instruction = instruction_map.get(action_info.get("action_type", ""), "请选择行动目标。")

        prompt = NIGHT_ACTION_PROMPT.format(
            player_name=self._player_ref(player),
            role_name=role_def.name,
            round_number=self.engine.round_number,
            alive_players_list=alive_list,
            action_instruction=instruction,
        )
        return self._append_user_history(player, prompt)

    def build_sheriff_successor_prompt(self, player_config: AIPlayerConfig) -> str:
        """构建警长死亡移交警徽提示词。"""
        player = self.engine._get_player(player_config.id)
        alive_players = self._format_alive_players(highlight_self=player.player_id if player else "")
        prompt = SHERIFF_SUCCESSOR_PROMPT.format(
            player_name=self._player_ref(player) if player else "?",
            alive_players=alive_players,
        )
        return self._append_user_history(player, prompt)

    def build_discussion_prompt(self, player_config: AIPlayerConfig) -> str:
        """构建白天讨论发言提示词。"""
        player = self.engine._get_player(player_config.id)
        if not player:
            return "请发表你的看法。"

        role_name = ROLE_LIBRARY[player.role_id].name if player.role_id else "未知"
        alive_players = self._format_alive_players(highlight_self=player.player_id)

        # 昨晚结果只使用公开晨间结算，避免泄露解药、守卫等夜间细节。
        night_result = self._get_latest_public_night_result()

        return DISCUSSION_PROMPT.format(
            player_name=self._player_ref(player),
            role_name=role_name,
            sheriff_note="，你是警长，拥有1.5票" if player.is_sheriff else "",
            round_number=self.engine.round_number,
            alive_players=alive_players,
            night_result=night_result,
            perspective_history=self._build_perspective_history(player),
        )

    def build_vote_prompt(self, player_config: AIPlayerConfig) -> str:
        """构建放逐投票提示词。"""
        player = self.engine._get_player(player_config.id)
        if not player:
            return "请选择要放逐的玩家。"

        role_name = ROLE_LIBRARY[player.role_id].name if player.role_id else "未知"
        alive_players = self._format_alive_players(highlight_self=player.player_id)
        pk_candidates = self.engine.get_vote_pk_candidates()
        vote_scope = ""
        if pk_candidates:
            vote_scope = "本轮PK候选：\n" + "\n".join(
                f"  - {self._player_ref(candidate)}" for candidate in pk_candidates
            )

        return VOTE_PROMPT.format(
            player_name=self._player_ref(player),
            role_name=role_name,
            sheriff_note="，你是警长，拥有1.5票" if player.is_sheriff else "",
            round_number=self.engine.round_number,
            alive_players=alive_players,
            perspective_history=self._build_perspective_history(player),
            vote_scope=vote_scope,
        )

    # ============================================================
    # 辅助方法
    # ============================================================

    def _append_user_history(self, player: WerewolfPlayerState | None, prompt: str) -> str:
        if not player:
            return prompt
        return f"{self._build_perspective_history(player)}\n\n{prompt}"

    def _get_werewolf_allies(self, player: WerewolfPlayerState) -> str:
        """获取狼人同伙列表。"""
        if player.role_id != RoleID.WEREWOLF:
            return ""
        allies = [
            self._player_ref(p)
            for p in self.engine.players
            if p.role_id == RoleID.WEREWOLF and p.player_id != player.player_id
        ]
        return ", ".join(allies) if allies else "（无其他狼人）"

    def _format_board_info(self) -> str:
        role_lines = []
        for role_id_str, count in self.engine.role_counts.items():
            if count <= 0:
                continue
            try:
                role_def = ROLE_LIBRARY.get(RoleID(role_id_str))
            except ValueError:
                role_def = None
            role_name = role_def.name if role_def else role_id_str
            role_lines.append(f"{role_name}×{count}")
        preset = self.engine.config.board_preset or "自定义板子"
        sheriff_rule = "开启，警长放逐票为1.5票，可决定白天发言顺序" if self.engine.config.sheriff_election else "关闭"
        return (
            f"板子：{preset}\n"
            f"角色配置：{'、'.join(role_lines) if role_lines else '未配置'}\n"
            f"警长规则：{sheriff_rule}"
        )

    def _get_latest_public_night_result(self) -> str:
        for item in reversed(getattr(self.engine, "_history_log", [])):
            if item.get("kind") != "night_result":
                continue
            text = self._scrub_names(str(item.get("text", ""))).strip()
            if not text:
                continue
            if "平安夜" in text:
                return "平安夜"
            prefix = "天亮了，昨晚 "
            if text.startswith(prefix):
                return text[len(prefix):]
            return text
        return "平安夜"

    def _build_perspective_history(self, player: WerewolfPlayerState) -> str:
        """Build full history from this player's legal point of view."""
        sections = [
            "【你的视角历史记录】",
            f"你是：{self._player_ref(player)}",
            "",
            "玩家状态：",
            self._format_all_players(),
            "",
            self._format_structured_history(player),
        ]
        return "\n".join(sections)

    def _format_all_players(self) -> str:
        lines = []
        for p in self.engine.players:
            status = "存活" if p.is_alive else "出局"
            flags = []
            if p.is_sheriff:
                flags.append("警长")
            if not p.is_alive and p.death_cause:
                flags.append(p.death_cause)
            suffix = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"  - {self._player_ref(p)}：{status}{suffix}")
        return "\n".join(lines) if lines else "（暂无）"

    def _format_structured_history(self, player: WerewolfPlayerState) -> str:
        history = [item for item in getattr(self.engine, "_history_log", []) if self._can_see_history_item(player, item)]
        if not history:
            return "历史记录：（暂无）"

        days = sorted({int(item.get("day") or 0) for item in history})
        lines = []
        for day in days:
            night_items = [item for item in history if int(item.get("day") or 0) == day and item.get("phase") == "night"]
            day_items = [item for item in history if int(item.get("day") or 0) == day and item.get("phase") == "day"]

            if night_items:
                lines.append(f"【第{day}天-夜晚】")
                self._append_werewolf_blocks(lines, night_items)
                self._append_role_action_block(lines, "预言家查验", night_items, {"seer_check"})
                self._append_role_action_block(lines, "女巫行动", night_items, {"witch_save", "witch_poison", "witch_skip"})
                self._append_role_action_block(lines, "守卫行动", night_items, {"guard"})

            if day_items:
                lines.append(f"【第{day}天-白天】")
                self._append_morning_result(lines, day_items)
                self._append_generic_text_block(lines, "系统公告", day_items, {"sheriff_order", "sheriff_succession"})
                self._append_player_text_block(lines, "警长竞选", day_items, {"sheriff_speech"})
                self._append_player_text_block(lines, "轮流发言", day_items, {"day_speech"})
                self._append_vote_block(lines, day_items)
                self._append_player_text_block(lines, "遗言", day_items, {"last_words"})

        return "\n".join(lines) if lines else "历史记录：（暂无）"

    def _append_werewolf_blocks(self, lines: list[str], items: list[dict]):
        rounds = sorted({
            int(item.get("round") or 1)
            for item in items
            if item.get("kind") in ("werewolf_chat", "werewolf_vote")
        })
        for round_number in rounds:
            round_items = [
                item for item in items
                if item.get("kind") in ("werewolf_chat", "werewolf_vote")
                and int(item.get("round") or 1) == round_number
            ]
            if not round_items:
                continue
            lines.append(f"【狼人交流 第{round_number}轮】")
            for item in round_items:
                actor = self._player_ref(self.engine._get_player(str(item.get("player_id", ""))))
                if item.get("kind") == "werewolf_chat":
                    lines.append(f"{actor}: {self._scrub_names(str(item.get('text', '')))}")
                elif item.get("kind") == "werewolf_vote":
                    target = self._player_ref(self.engine._get_player(str(item.get("target_id", ""))))
                    lines.append(f"{actor}: 投票刀 {target}")

    def _append_role_action_block(self, lines: list[str], title: str, items: list[dict], kinds: set[str]):
        block = [item for item in items if item.get("kind") in kinds]
        if not block:
            return
        lines.append(f"【{title}】")
        for item in block:
            lines.append(self._format_history_item(item))

    def _append_morning_result(self, lines: list[str], items: list[dict]):
        results = [item for item in items if item.get("kind") == "night_result"]
        if not results:
            return
        lines.append("【天亮信息】")
        for item in results:
            lines.append(self._scrub_names(str(item.get("text", ""))))

    def _append_generic_text_block(self, lines: list[str], title: str, items: list[dict], kinds: set[str]):
        block = [item for item in items if item.get("kind") in kinds]
        if not block:
            return
        lines.append(f"【{title}】")
        for item in block:
            lines.append(self._scrub_names(str(item.get("text", ""))))

    def _append_player_text_block(self, lines: list[str], title: str, items: list[dict], kinds: set[str]):
        block = [item for item in items if item.get("kind") in kinds]
        if not block:
            return
        lines.append(f"【{title}】")
        for item in block:
            actor = self._player_ref(self.engine._get_player(str(item.get("player_id", ""))))
            lines.append(f"{actor}: {self._scrub_names(str(item.get('text', '')))}")

    def _append_vote_block(self, lines: list[str], items: list[dict]):
        votes = [item for item in items if item.get("kind") == "vote"]
        results = [item for item in items if item.get("kind") == "vote_result"]
        if not votes and not results:
            return
        lines.append("【投票结果】")
        for item in votes:
            actor = self._player_ref(self.engine._get_player(str(item.get("player_id", ""))))
            target_id = str(item.get("target_id", ""))
            target = self._player_ref(self.engine._get_player(target_id)) if target_id else "弃权"
            lines.append(f"{actor}: {target}")
        for item in results:
            lines.append(self._scrub_names(str(item.get('text', ''))))

    def _format_history_item(self, item: dict) -> str:
        actor = self._player_ref(self.engine._get_player(str(item.get("player_id", ""))))
        target_id = str(item.get("target_id", ""))
        target = self._player_ref(self.engine._get_player(target_id)) if target_id else ""
        kind = item.get("kind")
        if kind == "seer_check":
            return f"{actor}: 查验 {target} = {item.get('text', '?')}"
        if kind == "witch_save":
            return f"{actor}: 使用解药救 {target}"
        if kind == "witch_poison":
            return f"{actor}: 使用毒药毒 {target}"
        if kind == "witch_skip":
            return f"{actor}: 未用药"
        if kind == "guard":
            return f"{actor}: 守护 {target}"
        return self._scrub_names(str(item.get("text", "")))

    def _can_see_history_item(self, player: WerewolfPlayerState, item: dict) -> bool:
        visibility = item.get("visibility", "public")
        if visibility == "public":
            return True
        if visibility == "werewolf":
            return player.role_id == RoleID.WEREWOLF
        if visibility == "seer":
            return player.role_id == RoleID.SEER and item.get("player_id") == player.player_id
        if visibility == "witch":
            return player.role_id == RoleID.WITCH and item.get("player_id") == player.player_id
        if visibility == "guard":
            return player.role_id == RoleID.GUARD and item.get("player_id") == player.player_id
        return False

    def _get_check_history(self, player: WerewolfPlayerState) -> str:
        """获取预言家查验记录。"""
        if player.role_id != RoleID.SEER:
            return "（暂无）"
        checks = [
            log for log in self.engine._night_log
            if log.get("action") == "check" and log.get("actor") == player.player_id
        ]
        if not checks:
            return "（暂无）"
        lines = []
        for c in checks:
            target = self.engine._get_player(c["target"])
            name = self._player_ref(target) if target else c["target"]
            result = c.get("result", "?")
            lines.append(f"第{self.engine.round_number}轮查验 {name}：{result}")
        return "\n".join(lines)

    def _get_guard_history(self, player: WerewolfPlayerState) -> str:
        """获取守卫守护记录。"""
        if player.role_id != RoleID.GUARD:
            return "（暂无）"
        if player.guard_last_protected:
            target = self.engine._get_player(player.guard_last_protected)
            return f"上一晚守护了 {self._player_ref(target) if target else player.guard_last_protected}"
        return "（暂无）"

    def _get_sheriff_name(self) -> str:
        sheriff = self.engine._get_player(self.engine.sheriff_id) if self.engine.sheriff_id else None
        return self._player_ref(sheriff) if sheriff else "无"

    def _format_alive_players(self, highlight_self: str = "") -> str:
        """格式化存活玩家列表。"""
        lines = []
        for p in self.engine.players:
            if not p.is_alive:
                continue
            flags = []
            if p.is_sheriff:
                flags.append("警长")
            if p.player_id == highlight_self:
                flags.append("你")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"  - {self._player_ref(p)}{flag_str}")
        return "\n".join(lines)

    def _get_recent_speeches(self) -> str:
        """获取最近的发言摘要。"""
        history = [
            item for item in getattr(self.engine, "_history_log", [])
            if item.get("kind") in ("sheriff_speech", "day_speech")
        ]
        if history:
            lines = []
            for item in history[-20:]:
                actor = self._player_ref(self.engine._get_player(str(item.get("player_id", ""))))
                text = self._scrub_names(str(item.get("text", "")))
                short = text[:100] + ("..." if len(text) > 100 else "")
                lines.append(f"{actor}: {short}")
            return "\n".join(lines)

        lines = []
        for p in self.engine.players:
            if not p.is_alive or not p.speech_history:
                continue
            recent = p.speech_history[-2:]  # 最近2条
            for s in recent:
                short = s[:100] + ("..." if len(s) > 100 else "")
                lines.append(f"{self._player_ref(p)}：{short}")
        return "\n".join(lines[-20:]) if lines else ""

    def _player_ref(self, player: WerewolfPlayerState | None) -> str:
        if not player:
            return "未知号"
        return f"{player.seat_index + 1}号玩家"

    def _target_ref(self, target: dict) -> str:
        player_id = target.get("player_id") if target else None
        player = self.engine._get_player(player_id) if player_id else None
        return self._player_ref(player)

    def _scrub_names(self, text: str) -> str:
        result = text
        for p in self.engine.players:
            result = result.replace(p.display_name, self._player_ref(p))
            result = result.replace(p.player_id, self._player_ref(p))
        return result

from app.models.player import AIPlayerConfig
from app.models.tournament import ActionType
from app.models.game import GameState, PlayerState
from app.prompts.default import DEFAULT_SYSTEM_PROMPT, SHOWDOWN_REVEAL_PROMPT


class PromptBuilder:
    """Renders prompt templates with game state and hand history."""

    def __init__(self, history: list[dict] | None = None, config: object = None):
        self.history: list[dict] = history or []
        self.config = config

    def build_system_prompt(self, player_config: AIPlayerConfig, state: GameState) -> str:
        """Use player's custom template or default, filled with tournament info."""
        template = player_config.prompt_override or DEFAULT_SYSTEM_PROMPT

        config = self.config
        ante_text = f" Ante={state.ante}" if state.ante > 0 else ""

        # Fill tournament config placeholders
        defaults = {
            "total_players": str(len(state.players)),
            "initial_chips": "?",
            "start_sb": str(state.small_blind),
            "start_bb": str(state.big_blind),
            "blind_minutes": "?",
            "level": str(state.level),
            "small_blind": str(state.small_blind),
            "big_blind": str(state.big_blind),
            "ante": str(state.ante),
            "ante_text": ante_text,
        }

        if config is not None:
            defaults["initial_chips"] = str(getattr(config, "initial_chips", "?"))
            defaults["start_sb"] = str(getattr(config, "small_blind_initial", state.small_blind))
            defaults["start_bb"] = str(getattr(config, "big_blind_initial", state.big_blind))
            defaults["blind_minutes"] = str(getattr(config, "blind_level_minutes", "?"))

        # Use safe formatting — only replace known placeholders
        for key, val in defaults.items():
            template = template.replace("{" + key + "}", val)

        return template

    def build_user_message(
        self,
        player_config: AIPlayerConfig,
        state: GameState,
        legal_actions: list[ActionType],
    ) -> str:
        player = next((p for p in state.players if p.player_id == player_config.id), None)
        if not player:
            return ""

        parts: list[str] = []

        # --- History section ---
        if self.history:
            parts.append("【历史记录】")
            for h in self.history:
                parts.append(self._format_history_hand(h, player_config.id))
            parts.append("【历史记录结束】\n")

        # --- Current hand ---
        parts.append("【当前牌局】")
        parts.append(self._format_current_hand(state, player))
        parts.append(self._format_legal_actions(legal_actions, state, player))
        parts.append("\n你的行动是：")

        return "\n".join(parts)

    def _format_history_hand(self, h: dict, player_id: str, fold_actions: bool = False) -> str:
        """Format one hand summary. If fold_actions=True, collapse action details into a compact summary."""
        lines = [f"第 {h['hand_number']} 手"]
        lines.append(f"  手牌：{' '.join(h.get('my_hole_cards', ['??', '??']))}")

        # Folded mode: compact action summary per phase
        if fold_actions:
            phases = ["pre_flop", "flop", "turn", "river"]
            for phase in phases:
                phase_actions = [a for a in h.get("actions", []) if a.get("phase") == phase]
                if not phase_actions:
                    continue
                phase_cn = {"pre_flop": "翻前", "flop": "翻牌", "turn": "转牌", "river": "河牌"}
                action_strs = []
                for a in phase_actions:
                    astr = self._action_line(a, player_id)
                    action_strs.append(astr)
                lines.append(f"  {phase_cn.get(phase, phase)}：{' → '.join(action_strs)}")
                # Show community cards for this phase
                if phase == "flop" and h.get("flop_cards"):
                    lines.append(f"  公共牌：{' '.join(h['flop_cards'])}")
                elif phase == "turn" and h.get("turn_card"):
                    lines.append(f"  公共牌：{' '.join(h['flop_cards'])} {h['turn_card']}")
                elif phase == "river" and h.get("river_card"):
                    lines.append(f"  公共牌：{' '.join(h['flop_cards'])} {h['turn_card']} {h['river_card']}")
        else:
            # Full detail mode (latest hand)
            for phase in ["pre_flop", "flop", "turn", "river"]:
                phase_actions = [a for a in h.get("actions", []) if a.get("phase") == phase]
                if not phase_actions and phase == "pre_flop":
                    continue  # skip phases with no actions if not pre-flop
                if phase == "flop" and not h.get("flop_cards"):
                    continue
                if phase == "turn" and not h.get("turn_card"):
                    continue
                if phase == "river" and not h.get("river_card"):
                    continue

                phase_cn = {"pre_flop": "pre-flop", "flop": "flop", "turn": "turn", "river": "river"}
                lines.append(f"  阶段：{phase_cn.get(phase, phase)}")
                if phase == "flop" and h.get("flop_cards"):
                    lines.append(f"  公共牌：{' '.join(h['flop_cards'])}")
                elif phase == "turn" and h.get("turn_card"):
                    lines.append(f"  公共牌：{' '.join(h['flop_cards'])} {h['turn_card']}")
                elif phase == "river" and h.get("river_card"):
                    lines.append(f"  公共牌：{' '.join(h['flop_cards'])} {h['turn_card']} {h['river_card']}")
                for a in phase_actions:
                    lines.append(f"  {self._action_line(a, player_id)}")

        # Settlement (always shown)
        lines.append("  结算：")
        for s in h.get("settlement", []):
            if s.get("revealed"):
                lines.append(f"  {s['name']}：{s['chip_change']:+d}  手牌：{' '.join(s.get('cards', ['??', '??']))}")
            else:
                lines.append(f"  {s['name']}：{s['chip_change']:+d}  手牌：未公开")

        lines.append("---")
        return "\n".join(lines)

    def _action_line(self, a: dict, player_id: str) -> str:
        name = a.get("player_name", "?")
        pos = a.get("position", "")
        action = a.get("action", "?")
        amount = a.get("amount", 0)
        you = "（你）" if a.get("player_id") == player_id else ""

        action_str = action
        if action == "raise":
            action_str = f"加注至 {amount}"
        elif action == "call":
            action_str = f"跟注 {amount}"  # amount is total bet after calling
        elif action == "fold":
            action_str = "弃牌"
        elif action == "check":
            action_str = "过牌"
        elif action == "all_in":
            action_str = f"全下 {amount}"
        elif action == "small_blind":
            action_str = f"小盲 {amount}"
        elif action == "big_blind":
            action_str = f"大盲 {amount}"

        return f"{name}（{pos}）{you}：{action_str}"

    def _format_current_hand(self, state: GameState, player: PlayerState) -> str:
        lines = []

        # Blind info
        blind_line = f"盲注级别：Lv{state.level}（SB={state.small_blind} BB={state.big_blind}"
        if state.ante > 0:
            blind_line += f" Ante={state.ante}"
        blind_line += "）"
        lines.append(blind_line)
        lines.append(f"手牌号：#{state.hand_number}")
        lines.append("")

        # Phase
        phase_cn = {
            "pre_flop": "pre-flop", "flop": "flop",
            "turn": "turn", "river": "river", "showdown": "showdown",
        }
        lines.append(f"当前阶段：{phase_cn.get(state.phase.value, state.phase.value)}")

        # Community cards
        if state.community_cards:
            lines.append(f"公共牌：{' '.join(state.community_cards)}")
        else:
            lines.append("公共牌：（无）")

        # Your hand
        if player.hole_cards:
            lines.append(f"你的手牌：{' '.join(player.hole_cards)}")
        else:
            lines.append("你的手牌：（已弃牌）")

        # Pot
        pot_total = sum(state.total_bets.values())
        lines.append(f"底池：{pot_total}")

        # Current round actions (exclude settlement/win events, include phase markers)
        action_events: list[dict] = []
        for e in state.events:
            text = e["text"]
            if "赢得" in text:
                continue
            if any(kw in text for kw in ["弃牌", "过牌", "跟注", "加注", "全下", "支付", "发翻牌", "发转牌", "发河牌"]):
                action_events.append(e)

        if action_events:
            lines.append("")
            lines.append("本轮行动：")
            prev_phase = None
            for e in action_events[-15:]:
                text = e["text"]
                # Insert phase separator
                if "发翻牌" in text:
                    lines.append("  --- flop ---")
                elif "发转牌" in text:
                    lines.append("  --- turn ---")
                elif "发河牌" in text:
                    lines.append("  --- river ---")
                else:
                    lines.append(f"  · {text}")
        lines.append("")

        # Players (skip eliminated: 0 chips + inactive + not all-in)
        lines.append("玩家状态（仅存活玩家）：")
        active_players = [p for p in state.players if p.chips > 0 or p.is_all_in]
        for p in active_players:

            pos = self._get_position_name(p.seat_index, state)
            you = "（你）" if p.player_id == player.player_id else ""

            status = ""
            if not p.is_active:
                status = " [已弃牌]"
            elif p.is_all_in:
                status = " [全下]"

            bet = state.round_bets.get(p.player_id, 0)
            bet_str = f" 本轮下注：{bet}" if bet > 0 else ""

            lines.append(f"  {p.display_name}（{pos}）{you}：剩余筹码 {p.chips}{status}{bet_str}")

        return "\n".join(lines)

    def _format_legal_actions(self, legal: list[ActionType], state: GameState, player: PlayerState) -> str:
        lines = ["\n合法行动："]
        to_call = state.current_bet - state.round_bets.get(player.player_id, 0)
        for a in legal:
            if a == ActionType.FOLD:
                lines.append("  - fold（弃牌）")
            elif a == ActionType.CHECK:
                lines.append("  - check（过牌）")
            elif a == ActionType.CALL:
                lines.append(f"  - call（跟注 {to_call}）")
            elif a == ActionType.RAISE:
                min_r = state.current_bet + state.min_raise
                max_r = player.chips + state.round_bets.get(player.player_id, 0)
                lines.append(f"  - raise <总额>（加注至，最小 {min_r}，最大 {max_r}）")
            elif a == ActionType.ALL_IN:
                lines.append(f"  - all_in（全下 {player.chips}）")
        return "\n".join(lines)

    @staticmethod
    def _get_position_name(seat_index: int, state: GameState) -> str:
        active = [p for p in state.players if p.chips > 0 or p.is_all_in]
        active_seats = sorted(p.seat_index for p in active)
        total = len(active_seats)
        if total <= 2:
            return "小盲/庄家" if seat_index == state.dealer_index else "大盲"

        positions = ["庄家", "小盲", "大盲", "枪口", "枪口+1", "枪口+2", "中位", "中位+1", "劫位", "关位"]
        try:
            dealer_pos = active_seats.index(state.dealer_index)
            seat_pos = active_seats.index(seat_index)
        except ValueError:
            return f"座{seat_index}"
        offset = (seat_pos - dealer_pos) % total
        return positions[offset] if offset < len(positions) else f"座{offset}"

    def build_reveal_prompt(self, player_config: AIPlayerConfig, state: GameState) -> str:
        """Build the reveal prompt with full hand context (same format as game prompt)."""
        player = next((p for p in state.players if p.player_id == player_config.id), None)
        if not player:
            return SHOWDOWN_REVEAL_PROMPT.format(
                hole_cards="未知", community_cards="无", pot=0, chips=0,
            )

        parts: list[str] = []

        # History
        if self.history:
            parts.append("【历史记录】")
            for h in self.history:
                parts.append(self._format_history_hand(h, player_config.id))
            parts.append("【历史记录结束】\n")

        # Current hand (same as game prompt)
        parts.append("【当前牌局】")
        parts.append(self._format_current_hand(state, player))

        # Reveal question
        hole = " ".join(player.hole_cards) if player.hole_cards else "未知"
        comm = " ".join(state.community_cards) if state.community_cards else "无"
        pot = sum(state.total_bets.values())
        parts.append(f"\n牌局结束，你因为其他玩家全部弃牌而赢得底池。")
        parts.append(f"你的手牌：{hole}")
        parts.append(f"公共牌：{comm}")
        parts.append(f"赢得底池：{pot}")
        parts.append(f"\n是否向牌桌亮出你的手牌？")
        parts.append("回复：REVEAL: yes  或  REVEAL: no")

        return "\n".join(parts)

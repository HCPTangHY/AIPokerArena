"""狼人杀游戏引擎：角色分配、上警、夜晚、白天、投票、胜负判定"""

import uuid
import random
import re
from app.core.game_base import GameEngine, BaseGameState
from app.models.werewolf import (
    WerewolfPhase, Team, RoleID, NightActionType,
    RoleDefinition, ROLE_LIBRARY, BoardPreset,
    WerewolfConfig, WerewolfPlayerState, WerewolfGameState,
)
from app.models.player import AIPlayerConfig


class WerewolfEngine(GameEngine):
    """狼人杀游戏引擎。"""

    game_type = "werewolf"

    def __init__(self, config: WerewolfConfig, players: list[AIPlayerConfig]):
        super().__init__(config, players)
        if len(players) < 4:
            raise ValueError("Werewolf requires at least 4 players")

        self.tournament_id = uuid.uuid4().hex[:12]
        self.round_number = 0
        self.phase = WerewolfPhase.ROLE_ASSIGN

        # 解析角色配置
        self.role_counts = self._resolve_role_counts()
        total_roles = sum(self.role_counts.values())
        if total_roles != len(players):
            raise ValueError(
                f"Role count ({total_roles}) must match player count ({len(players)})"
            )

        # 创建玩家状态
        self.players: list[WerewolfPlayerState] = [
            WerewolfPlayerState(
                player_id=p.id,
                display_name=p.display_name,
                seat_index=i,
                avatar_url=p.avatar_url,
            )
            for i, p in enumerate(players)
        ]

        # 夜晚状态
        self.night_kill_target: str | None = None
        self.night_check_result: dict | None = None
        self.night_save_target: str | None = None
        self.night_poison_target: str | None = None
        self.night_guard_target: str | None = None
        # 警长状态
        self.sheriff_id: str | None = None
        self.sheriff_vote_result: dict | None = None
        # 投票状态
        self.votes: dict[str, str] = {}
        self.vote_result: dict | None = None
        # 游戏结果
        self.winner_team: str | None = None
        self.is_over: bool = False
        # 内部状态
        self._night_actions_done: set[str] = set()
        self._pending_night_actions: list[dict] = []
        self._werewolf_discussed: bool = False
        self._werewolf_kill_decided: bool = False
        self._werewolf_votes: dict[str, str] = {}  # wolf_id → target_id
        self._discussion_round = 0
        self._events: list[dict] = []
        self._night_log: list[dict] = []
        self._speech_log: list[dict] = []
        self._history_log: list[dict] = []
        self._sheriff_candidates: list[str] = []
        self._sheriff_campaign_candidates: list[str] = []
        self._sheriff_votes: dict[str, str] = {}
        self._sheriff_vote_round = 1
        self._day_speaking_order: list[str] = []
        self._vote_pk_candidates: list[str] = []
        self._vote_round = 1
        self._pending_sheriff_succession: dict | None = None

    # ============================================================
    # 角色分配
    # ============================================================

    def _resolve_role_counts(self) -> dict[str, int]:
        """解析角色数量：优先使用自定义，否则使用预置板子。"""
        cfg = self.config
        if cfg.custom_roles:
            return dict(cfg.custom_roles)
        preset = BoardPreset.get_preset(cfg.board_preset)
        if preset:
            return dict(preset.roles)
        # 默认简易板子
        n = len(self._raw_players)
        return {"werewolf": max(1, n // 3), "seer": 1, "witch": 1, "hunter": 1, "villager": n - (n // 3) - 3}

    @property
    def _raw_players(self) -> list[AIPlayerConfig]:
        return self.config._raw_players if hasattr(self.config, '_raw_players') else self._stored_players

    # ============================================================
    # GameEngine ABC 实现
    # ============================================================

    def start_game(self) -> WerewolfGameState:
        """分配角色，返回初始状态。"""
        self.is_running = True
        self.round_number = 1

        # 构建角色池
        role_pool = []
        for role_id_str, count in self.role_counts.items():
            role_id = RoleID(role_id_str)
            role_pool.extend([role_id] * count)

        random.shuffle(role_pool)

        # 分配角色
        for i, player in enumerate(self.players):
            role_id = role_pool[i]
            role_def = ROLE_LIBRARY[role_id]
            player.role_id = role_id
            player.role_name = role_def.name
            player.team = role_def.team
            player.is_alive = True

        self.phase = WerewolfPhase.ROLE_ASSIGN
        self._add_event("角色已分配，天黑请闭眼")
        return self._build_state()

    def get_state(self) -> WerewolfGameState:
        return self._build_state()

    def apply_action(self, action) -> WerewolfGameState:
        raise NotImplementedError("Use specific methods: apply_night_action, record_speech, cast_vote")

    def is_game_over(self) -> bool:
        alive_werewolves = sum(
            1 for p in self.players
            if p.is_alive and p.team == Team.WEREWOLF
        )
        alive_villagers = sum(
            1 for p in self.players
            if p.is_alive and p.team in (Team.VILLAGER, Team.THIRD_PARTY)
        )
        if alive_werewolves == 0:
            self.winner_team = "villager"
            return True
        if alive_werewolves >= alive_villagers:
            self.winner_team = "werewolf"
            return True
        return False

    def get_winner(self) -> dict | None:
        if not self.is_game_over():
            return None
        team_name = "好人阵营" if self.winner_team == "villager" else "狼人阵营"
        return {"team": self.winner_team, "team_name": team_name}

    def get_winner_dict(self) -> dict | None:
        return self.get_winner()

    # ============================================================
    # 上警环节
    # ============================================================

    def get_sheriff_candidates_needed(self) -> bool:
        """是否需要AI决定是否参选。"""
        return self.config.allow_sheriff_campaign and not self._sheriff_candidates

    def set_sheriff_candidates(self, candidates: list[str]):
        """设置参选警长的玩家列表（由服务层调用，AI决定参选）。"""
        self._sheriff_candidates = [pid for pid in candidates
                                     if self._get_player(pid) and self._get_player(pid).is_alive]
        if not self._sheriff_candidates:
            # 随机选2-3人参选
            alive = [p for p in self.players if p.is_alive]
            n = min(3, max(2, len(alive) // 2))
            self._sheriff_candidates = [p.player_id for p in random.sample(alive, n)]
        self._sheriff_campaign_candidates = list(self._sheriff_candidates)
        self._sheriff_votes = {}
        self._sheriff_vote_round = 1
        self._add_event(f"警长候选人：{', '.join(self._seat_label(pid) for pid in self._sheriff_candidates)}")

    def get_sheriff_candidates(self) -> list[str]:
        return list(self._sheriff_candidates)

    def get_sheriff_speaking_order(self) -> list[str]:
        """返回候选人发言顺序。"""
        return list(self._sheriff_candidates)

    def record_sheriff_speech(self, player_id: str, speech: str, announce: bool = True):
        """记录警长竞选发言。"""
        p = self._get_player(player_id)
        if p:
            speech = self._extract_public_speech(speech)
            label = self._speech_label("sheriff")
            p.speech_history.append(f"[竞选发言] {speech}")
            self._speech_log.append({
                "phase": "sheriff",
                "day": self.round_number,
                "player_id": player_id,
                "text": f"[竞选发言] {speech}",
                "label": label,
                "visibility": "public",
            })
            self._append_history("sheriff_speech", "day", player_id=player_id, text=speech)
            if announce:
                self._add_event(f"🎤 {p.display_name}（警长候选人）：{speech}")

    def get_sheriff_voters(self) -> list[WerewolfPlayerState]:
        """返回需要投票的玩家（未参选且存活）。"""
        ineligible = set(self._sheriff_campaign_candidates or self._sheriff_candidates)
        return [p for p in self.players
                if p.is_alive and p.player_id not in ineligible]

    def cast_sheriff_vote(self, voter_id: str, target_id: str | None):
        """投警长票。"""
        eligible_voter_ids = {p.player_id for p in self.get_sheriff_voters()}
        if voter_id not in eligible_voter_ids:
            return
        if target_id and target_id in self._sheriff_candidates:
            self._sheriff_votes[voter_id] = target_id
        else:
            self._sheriff_votes[voter_id] = ""

    def resolve_sheriff_election(self) -> WerewolfGameState:
        """统计警长票数，选出警长。"""
        candidates = list(self._sheriff_candidates)
        if not candidates:
            self.sheriff_vote_result = {
                "winner_id": "",
                "winner_name": "",
                "votes": dict(self._sheriff_votes),
                "tally": {},
                "candidate_ids": [],
                "round": 1,
                "is_tie": False,
                "tie_ids": [],
                "no_sheriff": True,
            }
            self._add_event("本局无警徽")
            self._sheriff_vote_round = 1
            return self._build_state()

        tally: dict[str, int] = {}
        for target_id in self._sheriff_votes.values():
            if target_id in candidates:
                tally[target_id] = tally.get(target_id, 0) + 1

        if tally:
            max_votes = max(tally.values())
            top = [pid for pid in candidates if tally.get(pid, 0) == max_votes]
        else:
            top = list(candidates)

        is_pk_round = self._sheriff_vote_round >= 2
        round_number = self._sheriff_vote_round

        if len(top) > 1:
            self.sheriff_vote_result = {
                "winner_id": "",
                "winner_name": "",
                "votes": dict(self._sheriff_votes),
                "tally": dict(tally),
                "candidate_ids": candidates,
                "round": round_number,
                "is_tie": True,
                "tie_ids": top,
                "no_sheriff": is_pk_round,
            }
            self._add_sheriff_vote_summary_event(tally, self._sheriff_votes)
            tied_names = "、".join(self._seat_label(pid) for pid in top)
            if is_pk_round:
                self._add_event(f"警长PK再次平票：{tied_names}，本局无警徽")
                self._sheriff_candidates = []
                self._sheriff_campaign_candidates = []
                self._sheriff_votes = {}
                self._sheriff_vote_round = 1
            else:
                self._add_event(f"警长投票平票：{tied_names} 进入PK发言，警下玩家重新投票")
                self._sheriff_candidates = top
                self._sheriff_votes = {}
                self._sheriff_vote_round = 2
            return self._build_state()

        winner_id = top[0]

        self.sheriff_vote_result = {
            "winner_id": winner_id,
            "winner_name": self._get_player(winner_id).display_name if self._get_player(winner_id) else "?",
            "votes": dict(self._sheriff_votes),
            "tally": dict(tally),
            "candidate_ids": candidates,
            "round": round_number,
            "is_tie": False,
            "tie_ids": [],
            "no_sheriff": False,
        }
        self._add_sheriff_vote_summary_event(tally, self._sheriff_votes)

        winner = self._get_player(winner_id)
        if winner:
            winner.is_sheriff = True
            self.sheriff_id = winner_id
            self._add_event(f"🏆 {winner.display_name} 当选警长！（拥有1.5票）")

        self._sheriff_candidates = []
        self._sheriff_campaign_candidates = []
        self._sheriff_votes = {}
        self._sheriff_vote_round = 1
        return self._build_state()

    def _add_sheriff_vote_summary_event(self, tally: dict[str, int], votes: dict[str, str]):
        """Add a public sheriff election vote distribution event."""
        tally_lines = []
        candidates = sorted(
            [p for p in (self._get_player(pid) for pid in self._sheriff_candidates) if p],
            key=lambda p: p.seat_index,
        )
        for candidate in candidates:
            tally_lines.append(f"{candidate.display_name}：{tally.get(candidate.player_id, 0)}票")

        abstain_count = sum(1 for target_id in votes.values() if not target_id)
        if abstain_count:
            tally_lines.append(f"弃权/无效：{abstain_count}人")

        flow_lines = []
        for voter_id, target_id in votes.items():
            voter = self._get_player(voter_id)
            if not voter:
                continue
            target = self._get_player(target_id) if target_id else None
            flow_lines.append(f"{voter.display_name} → {target.display_name if target else '弃权/无效'}")

        tally_text = "；".join(tally_lines) if tally_lines else "无有效票"
        flow_text = "；".join(flow_lines) if flow_lines else "无投票明细"
        self._add_event(f"📊 警长票型：{tally_text}\n投票明细：{flow_text}")

    # ============================================================
    # 夜晚阶段 - 狼人交流（多轮讨论+投票，共识后自动开刀）
    # ============================================================

    def get_alive_werewolves(self) -> list[WerewolfPlayerState]:
        """获取存活狼人列表。"""
        return [p for p in self.players
                if p.is_alive and p.role_id == RoleID.WEREWOLF]

    def get_werewolf_discussion_order(self) -> list[WerewolfPlayerState]:
        """狼人交流发言顺序（按座次循环）。"""
        wolves = self.get_alive_werewolves()
        return sorted(wolves, key=lambda p: p.seat_index)

    def record_werewolf_discussion(
        self,
        player_id: str,
        speech: str,
        discussion_round: int | None = None,
        announce: bool = True,
    ):
        """记录一条狼人夜间交流发言，同时解析其中的投票。"""
        p = self._get_player(player_id)
        if not p or not speech.strip():
            return

        raw_speech = speech.strip()
        public_speech = self._extract_public_speech(raw_speech)
        label = self._speech_label("werewolf_night", discussion_round=discussion_round)
        p.speech_history.append(f"[夜晚交流] {public_speech}")
        self._speech_log.append({
            "phase": "werewolf_night",
            "day": self.round_number,
            "round": discussion_round,
            "player_id": player_id,
            "text": f"[夜晚交流] {public_speech}",
            "label": label,
            "visibility": "werewolf",
        })
        self._append_history(
            "werewolf_chat", "night",
            player_id=player_id,
            text=public_speech,
            visibility="werewolf",
            round=discussion_round,
        )
        if announce:
            self._add_event(f"🐺 {p.display_name}：{public_speech}", hidden=False)
        self._night_log.append({
            "action": "werewolf_chat",
            "actor": player_id,
            "target": "",
            "result": public_speech,
        })

        # 从发言中解析投票意图
        # 匹配 VOTE: xxx 或 刀xxx 或 投xxx（名字可能含空格）
        vote_match = re.search(
            r'(?:VOTE|vote|投票|刀|杀)[:：]\s*(.+?)(?:\n|$|。|，|！|！|？)',
            raw_speech,
        )
        if not vote_match:
            # 更宽松的匹配：VOTE/刀/杀 后面的内容直到行尾
            vote_match = re.search(
                r'(?:VOTE|vote|投票|刀|杀)[:：]\s*(.+)',
                raw_speech,
            )
        if vote_match:
            target_name = vote_match.group(1).strip().rstrip("。，，.!！？?")
            target_id = self._parse_target(target_name)
            target_p = self._get_player(target_id) if target_id else None
            if target_p:
                self._werewolf_votes[player_id] = target_p.player_id
                self._night_log.append({
                    "action": "werewolf_vote",
                    "actor": player_id,
                    "target": target_p.player_id,
                    "result": "",
                })
                self._append_history(
                    "werewolf_vote", "night",
                    player_id=player_id,
                    target_id=target_p.player_id,
                    visibility="werewolf",
                    round=discussion_round,
                )
                self._add_event(
                    f"🗳️ {p.display_name} 投票刀 {target_p.display_name}",
                    hidden=True,
                )

    def get_werewolf_votes(self) -> dict[str, str]:
        """获取当前狼人投票状态。{wolf_id: target_id}"""
        return dict(self._werewolf_votes)

    def is_werewolf_consensus_reached(self) -> bool:
        """检查是否所有狼人达成共识（都投了同一个目标）。"""
        wolves = self.get_alive_werewolves()
        if len(wolves) == 1:
            return True
        votes = self._werewolf_votes
        if len(votes) < len(wolves):
            return False
        targets = set(votes.values())
        return len(targets) == 1

    def get_consensus_target(self) -> str | None:
        """获取共识目标（所有狼人都投了同一个人）。"""
        if not self.is_werewolf_consensus_reached():
            return None
        return next(iter(set(self._werewolf_votes.values())))

    def get_werewolf_discussion_summary(self) -> str:
        """获取本轮狼人交流摘要。"""
        lines = []
        for p in self.get_alive_werewolves():
            recent = [s for s in p.speech_history if s.startswith("[夜晚交流]")]
            for s in recent[-3:]:
                lines.append(f"{self._seat_label(p)}：{s.removeprefix('[夜晚交流] ')[:150]}")
        if self._werewolf_votes:
            lines.append("")
            lines.append("当前投票：")
            for wolf_id, target_id in self._werewolf_votes.items():
                wolf = self._get_player(wolf_id)
                target = self._get_player(target_id)
                if wolf and target:
                    lines.append(f"  {self._seat_label(wolf)} → 刀 {self._seat_label(target)}")
        return "\n".join(lines) if lines else "（还未讨论）"

    def get_werewolf_kill_action_info(self) -> dict | None:
        """获取狼人刀人决策的行动信息。"""
        wolves = self.get_alive_werewolves()
        if not wolves:
            return None
        # 用共识目标或让代表狼人决定
        consensus = self.get_consensus_target()
        rep = wolves[0]
        role_def = ROLE_LIBRARY[RoleID.WEREWOLF]
        targets = self._get_valid_night_targets(rep)
        return {
            "player_id": rep.player_id,
            "player_name": rep.display_name,
            "role": role_def.name,
            "role_id": role_def.role_id.value,
            "action_type": "kill",
            "priority": role_def.night_priority,
            "targets": targets,
            "discussion_summary": self.get_werewolf_discussion_summary(),
            "consensus_target": consensus,
            "consensus_reached": self.is_werewolf_consensus_reached(),
        }

    # ============================================================
    # 夜晚阶段
    # ============================================================

    def start_night(self) -> WerewolfGameState:
        """进入夜晚阶段。"""
        self.phase = WerewolfPhase.NIGHT
        self._night_actions_done = set()
        self._night_log = []
        self._werewolf_discussed = False
        self._werewolf_kill_decided = False
        self._werewolf_votes: dict[str, str] = {}
        self.night_kill_target = None
        self.night_check_result = None
        self.night_save_target = None
        self.night_poison_target = None
        self.night_guard_target = None
        self._add_event(f"🌙 第 {self.round_number} 夜降临，请闭眼...")
        return self._build_state()

    def has_pending_night_actions(self) -> bool:
        """是否还有未处理的夜晚行动（包括狼人交流）。"""
        alive_wolves = self.get_alive_werewolves()
        if alive_wolves and not self._werewolf_discussed:
            return True
        if alive_wolves and self._werewolf_discussed and not self._werewolf_kill_decided:
            return True
        self._build_pending_actions()
        return len(self._pending_night_actions) > 0

    def needs_werewolf_discussion(self) -> bool:
        """是否需要狼人夜间交流（单狼人跳过）。"""
        wolves = self.get_alive_werewolves()
        return len(wolves) >= 2 and not self._werewolf_discussed

    def needs_werewolf_kill_decision(self) -> bool:
        """是否需要狼人做出刀人决定。"""
        wolves = self.get_alive_werewolves()
        return len(wolves) >= 1 and not self._werewolf_kill_decided

    def mark_werewolf_discussed(self):
        """标记狼人交流已完成。"""
        self._werewolf_discussed = True
        self._pending_night_actions = []

    def _build_pending_actions(self):
        """构建当前待处理的夜晚行动列表（按优先级排序，狼人kill在discussion后单独处理）。"""
        if self._pending_night_actions:
            return

        actions = []
        for player in self.players:
            if not player.is_alive or player.player_id in self._night_actions_done:
                continue

            role_def = ROLE_LIBRARY.get(player.role_id) if player.role_id else None
            if not role_def or role_def.night_action == NightActionType.NONE:
                self._night_actions_done.add(player.player_id)
                continue

            if role_def.role_id == RoleID.WITCH:
                if player.witch_save_used and player.witch_poison_used:
                    self._night_actions_done.add(player.player_id)
                    continue
                targets = []
                if not player.witch_poison_used:
                    targets = [
                        {"player_id": p.player_id, "display_name": p.display_name}
                        for p in self.players
                        if p.is_alive and p.player_id != player.player_id
                    ]
                if self.night_kill_target or targets:
                    killed = self._get_player(self.night_kill_target) if self.night_kill_target else None
                    actions.append({
                        "player_id": player.player_id,
                        "player_name": player.display_name,
                        "role": role_def.name,
                        "role_id": role_def.role_id.value,
                        "action_type": "witch",
                        "priority": role_def.night_priority,
                        "targets": targets,
                        "killed_target": {
                            "player_id": killed.player_id,
                            "display_name": killed.display_name,
                        } if killed else None,
                        "can_save": bool(self.night_kill_target and not player.witch_save_used),
                        "can_poison": not player.witch_poison_used,
                    })
                else:
                    self._night_actions_done.add(player.player_id)
                continue

            # 检查使用次数
            if role_def.max_uses > 0:
                if role_def.role_id == RoleID.WITCH:
                    if player.witch_save_used and player.witch_poison_used:
                        self._night_actions_done.add(player.player_id)
                        continue

            # 狼人kill由讨论后统一决策，不在常规队列中
            if role_def.role_id == RoleID.WEREWOLF:
                if role_def.night_action == NightActionType.KILL:
                    self._night_actions_done.add(player.player_id)
                    continue

            actions.append({
                "player_id": player.player_id,
                "player_name": player.display_name,
                "role": role_def.name,
                "role_id": role_def.role_id.value,
                "action_type": role_def.night_action.value,
                "priority": role_def.night_priority,
                "targets": self._get_valid_night_targets(player),
            })

        actions = [action for action in actions if action["targets"]]
        actions.sort(key=lambda a: a["priority"])
        self._pending_night_actions = actions

    def _get_valid_night_targets(self, actor: WerewolfPlayerState) -> list[dict]:
        """获取有效的夜晚行动目标。"""
        targets = []
        role_def = ROLE_LIBRARY.get(actor.role_id) if actor.role_id else None
        if not role_def:
            return targets

        for p in self.players:
            if not p.is_alive:
                continue

            if role_def.night_action == NightActionType.KILL:
                # 狼人不能刀狼人
                if p.team == Team.WEREWOLF:
                    continue
            elif role_def.night_action == NightActionType.CHECK:
                # 预言家不能查自己，不能重复查
                if p.player_id == actor.player_id:
                    continue
            elif role_def.night_action == NightActionType.GUARD:
                # 守卫不能连续守同一人
                if p.player_id == actor.guard_last_protected:
                    continue
                if p.player_id == actor.player_id:
                    continue
            elif role_def.night_action == NightActionType.SAVE:
                # 女巫解药只能救被杀的人（在第一晚可以自救）
                if actor.witch_save_used:
                    continue
            elif role_def.night_action == NightActionType.POISON:
                if actor.witch_poison_used:
                    continue

            targets.append({"player_id": p.player_id, "display_name": p.display_name})

        return targets

    def get_next_night_action(self) -> dict | None:
        """获取下一个待处理的夜晚行动。"""
        self._build_pending_actions()
        if not self._pending_night_actions:
            return None
        return self._pending_night_actions[0]

    def skip_night_action(self, player_id: str):
        """跳过某个玩家的夜晚行动。"""
        self._night_actions_done.add(player_id)
        self._pending_night_actions = []

    def apply_night_action(self, player_id: str, action, consensus_target: str | None = None) -> WerewolfGameState:
        """执行夜晚行动。action的raw_response解析目标。consensus_target用于狼人共识刀人。"""
        player = self._get_player(player_id)
        if not player:
            self.skip_night_action(player_id)
            return self._build_state()

        role_def = ROLE_LIBRARY.get(player.role_id) if player.role_id else None
        if not role_def:
            self.skip_night_action(player_id)
            return self._build_state()

        raw = (action.raw_response or "").strip()

        if role_def.role_id == RoleID.WITCH:
            raw_lower = raw.lower()
            target_id = self._parse_target(raw)
            wants_save = any(token in raw_lower for token in ("action: save", "save", "救", "解药"))
            wants_poison = any(token in raw_lower for token in ("action: poison", "poison", "毒"))
            wants_skip = any(token in raw_lower for token in ("action: skip", "skip", "pass", "不用", "跳过"))

            if wants_save and not wants_skip and self.night_kill_target and not player.witch_save_used:
                player.witch_save_used = True
                self.night_save_target = self.night_kill_target
                self._night_log.append({"action": "save", "actor": player_id, "target": self.night_kill_target})
                self._append_history("witch_save", "night", player_id=player_id, target_id=self.night_kill_target, visibility="witch")
            elif (wants_poison or target_id) and target_id and not player.witch_poison_used:
                target = self._get_player(target_id)
                if target and target.is_alive and target.player_id != player_id:
                    player.witch_poison_used = True
                    self.night_poison_target = target_id
                    self._night_log.append({"action": "poison", "actor": player_id, "target": target_id})
                    self._append_history("witch_poison", "night", player_id=player_id, target_id=target_id, visibility="witch")
            else:
                self._night_log.append({"action": "witch_skip", "actor": player_id, "target": ""})
                self._append_history("witch_skip", "night", player_id=player_id, visibility="witch")

            self._night_actions_done.add(player_id)
            self._pending_night_actions = []
            return self._build_state()

        # 如果有共识目标，直接使用
        if consensus_target and role_def.night_action == NightActionType.KILL:
            target_id = consensus_target
        else:
            target_id = self._parse_target(raw)

        if role_def.night_action == NightActionType.KILL:
            if target_id and self._is_valid_kill_target(player, target_id):
                self.night_kill_target = target_id
                self._werewolf_kill_decided = True
                self._night_log.append({"action": "kill", "actor": player_id, "target": target_id})
                self._append_history("werewolf_kill", "night", player_id=player_id, target_id=target_id, visibility="werewolf")
                self._add_event(f"🐺 狼人选择击杀 {self._get_player(target_id).display_name}", hidden=True)
            else:
                self._werewolf_kill_decided = True
                self._night_log.append({"action": "kill_skip", "actor": player_id, "target": ""})
                self._append_history("werewolf_kill_skip", "night", player_id=player_id, visibility="werewolf")
                self._add_event("🐺 狼人没有形成有效刀口", hidden=True)

        elif role_def.night_action == NightActionType.CHECK:
            if target_id and self._is_valid_check_target(player, target_id):
                target_player = self._get_player(target_id)
                target_role = ROLE_LIBRARY.get(target_player.role_id) if target_player.role_id else None
                result = "狼人" if (target_player.team == Team.WEREWOLF) else "好人"
                self.night_check_result = {
                    "target_id": target_id,
                    "target_name": target_player.display_name,
                    "result": result,
                }
                self._night_log.append({"action": "check", "actor": player_id, "target": target_id, "result": result})
                self._append_history("seer_check", "night", player_id=player_id, target_id=target_id, text=result, visibility="seer")
                self._add_event(f"🔮 预言家查验 {self._seat_label(target_player)}：{result}")

        elif role_def.night_action == NightActionType.SAVE:
            if target_id and not player.witch_save_used:
                player.witch_save_used = True
                self.night_save_target = target_id
                self._night_log.append({"action": "save", "actor": player_id, "target": target_id})
                self._append_history("witch_save", "night", player_id=player_id, target_id=target_id, visibility="witch")

        elif role_def.night_action == NightActionType.POISON:
            if target_id and not player.witch_poison_used:
                player.witch_poison_used = True
                self.night_poison_target = target_id
                self._night_log.append({"action": "poison", "actor": player_id, "target": target_id})
                self._append_history("witch_poison", "night", player_id=player_id, target_id=target_id, visibility="witch")

        elif role_def.night_action == NightActionType.GUARD:
            if target_id and target_id != player.guard_last_protected:
                player.guard_last_protected = target_id
                self.night_guard_target = target_id
                self._night_log.append({"action": "guard", "actor": player_id, "target": target_id})
                self._append_history("guard", "night", player_id=player_id, target_id=target_id, visibility="guard")

        self._night_actions_done.add(player_id)
        self._pending_night_actions = []
        return self._build_state()

    def _parse_target(self, raw: str) -> str | None:
        """从AI回复中解析目标玩家。"""
        if not raw:
            return None
        # 优先匹配座位号，避免模型名带来的场外偏差。
        for m in re.finditer(r'(?:玩家\s*)?(\d{1,2})\s*号|#\s*(\d{1,2})', raw):
            seat_number = int(m.group(1) or m.group(2))
            for p in self.players:
                if p.seat_index + 1 == seat_number:
                    return p.player_id
        # 尝试匹配 player_id
        for p in self.players:
            if p.player_id in raw:
                return p.player_id
        # 尝试匹配 display_name
        for p in self.players:
            if p.display_name in raw:
                return p.player_id
        # 尝试匹配 "TARGET: xxx"
        m = re.search(r'(?:TARGET|target|目标|ACTION|action|VOTE|vote)[:：]\s*(\S+)', raw)
        if m:
            name = m.group(1).strip()
            if name.isdigit():
                seat_number = int(name)
                for p in self.players:
                    if p.seat_index + 1 == seat_number:
                        return p.player_id
            nested = self._parse_target(name) if name != raw else None
            if nested:
                return nested
            for p in self.players:
                if p.display_name == name or p.player_id == name:
                    return p.player_id
        return None

    def _is_valid_kill_target(self, actor: WerewolfPlayerState, target_id: str) -> bool:
        target = self._get_player(target_id)
        return target and target.is_alive and target.team != Team.WEREWOLF

    def _is_valid_check_target(self, actor: WerewolfPlayerState, target_id: str) -> bool:
        target = self._get_player(target_id)
        return target and target.is_alive and target.player_id != actor.player_id

    def resolve_night(self) -> WerewolfGameState:
        """结算夜晚行动。"""
        deaths: list[str] = []
        death_reasons: dict[str, str] = {}

        # 狼人刀口
        if self.night_kill_target:
            # 检查是否被守卫守护
            if self.night_guard_target != self.night_kill_target:
                # 没有被守护，检查女巫是否救人
                if self.night_save_target == self.night_kill_target:
                    self._add_event(
                        f"💊 女巫使用解药救活了 {self._get_player(self.night_kill_target).display_name}",
                        hidden=True,
                    )
                else:
                    deaths.append(self.night_kill_target)
                    death_reasons[self.night_kill_target] = "killed"
            else:
                self._add_event(
                    f"🛡️ 守卫守住了 {self._get_player(self.night_kill_target).display_name}",
                    hidden=True,
                )

        # 女巫毒药
        if self.night_poison_target and self.night_poison_target not in deaths:
            deaths.append(self.night_poison_target)
            death_reasons[self.night_poison_target] = "killed"
            self._add_event(
                f"☠️ 女巫使用毒药毒杀了 {self._get_player(self.night_poison_target).display_name}",
                hidden=True,
            )

        # 处理死亡
        for pid in deaths:
            player = self._get_player(pid)
            if player:
                player.is_alive = False
                player.death_cause = death_reasons.get(pid, "killed")
                player.death_round = self.round_number
                # 猎人被刀可以开枪
                if player.role_id == RoleID.HUNTER:
                    player.hunter_can_shoot = True
                    self._add_event(f"💀 {player.display_name} 被杀害", hidden=True)

        # 公布死讯
        if deaths:
            names = [self._get_player(pid).display_name for pid in deaths]
            text = f"天亮了，昨晚 {', '.join(names)} 死亡"
            self._add_event(f"☀️ {text}")
            self._append_history("night_result", "day", text=text, visibility="public")
        else:
            text = "天亮了，昨晚是平安夜"
            self._add_event(f"☀️ {text}")
            self._append_history("night_result", "day", text=text, visibility="public")

        # 处理警长继承
        for pid in deaths:
            if pid == self.sheriff_id:
                self._handle_sheriff_succession()

        self._night_actions_done = set()
        self._pending_night_actions = []
        return self._build_state()

    def _handle_sheriff_succession(self):
        """警长死亡时标记待处理的警徽移交（由服务层通过AI决定接手者）。"""
        old_sheriff = self._get_player(self.sheriff_id) if self.sheriff_id else None
        if old_sheriff:
            self._pending_sheriff_succession = {
                "old_sheriff_id": self.sheriff_id,
                "old_sheriff_name": old_sheriff.display_name,
            }

    def get_pending_sheriff_succession(self) -> dict | None:
        """返回待处理的警徽移交信息。"""
        return self._pending_sheriff_succession

    def apply_sheriff_succession(self, target_id: str) -> WerewolfGameState:
        """执行警徽移交到指定目标。"""
        old_sheriff = self._get_player(self.sheriff_id) if self.sheriff_id else None
        target = self._get_player(target_id)
        if not old_sheriff or not target or not target.is_alive:
            self._pending_sheriff_succession = None
            return self._build_state()

        old_sheriff.is_sheriff = False
        target.is_sheriff = True
        self.sheriff_id = target_id
        self._pending_sheriff_succession = None
        text = f"📿 警长 {old_sheriff.display_name} 将警徽移交给 {target.display_name}"
        self._add_event(text)
        self._append_history("sheriff_succession", "day", text=text, visibility="public")
        return self._build_state()

    def apply_sheriff_destroy(self) -> WerewolfGameState:
        """撕警徽：警长死亡，警徽销毁，本局不再有警长。"""
        old_sheriff = self._get_player(self.sheriff_id) if self.sheriff_id else None
        if old_sheriff:
            old_sheriff.is_sheriff = False
        self.sheriff_id = None
        self._pending_sheriff_succession = None
        text = "📿 警徽已被撕毁，本局不再有警长"
        self._add_event(text)
        self._append_history("sheriff_succession", "day", text=text, visibility="public")
        return self._build_state()

    # ============================================================
    # 白天阶段 - 讨论
    # ============================================================

    def start_day(self) -> WerewolfGameState:
        """进入白天讨论阶段。"""
        self.phase = WerewolfPhase.DAY
        self._discussion_round = 0
        self._day_speaking_order = [
            p.player_id for p in self._build_day_speaking_order()
        ]
        # 重置投票状态
        for p in self.players:
            p.has_voted = False
            p.vote_target = None
        self.votes = {}
        self._add_event(f"💬 第 {self.round_number} 天讨论开始")
        return self._build_state()

    def get_speaking_order(self) -> list[WerewolfPlayerState]:
        """获取发言顺序：有警长时警长决定顺序，并最后发言。"""
        if self._day_speaking_order:
            ordered = [self._get_player(pid) for pid in self._day_speaking_order]
            return [p for p in ordered if p and p.is_alive]
        return self._build_day_speaking_order()

    def decide_day_speaking_order(self, raw_choice: str = "") -> WerewolfGameState:
        """由警长决定白天发言顺序；警长始终最后发言。"""
        direction = self._parse_speaking_order_direction(raw_choice)
        self._day_speaking_order = [
            p.player_id for p in self._build_day_speaking_order(direction)
        ]
        self._announce_day_speaking_order(direction)
        return self._build_state()

    def _build_day_speaking_order(self, direction: str = "next") -> list[WerewolfPlayerState]:
        """默认按警长后一位开始顺序发言，警长末置。"""
        alive = sorted([p for p in self.players if p.is_alive], key=lambda p: p.seat_index)
        if len(alive) <= 1:
            return alive

        sheriff = self._get_player(self.sheriff_id) if self.sheriff_id else None
        if not sheriff or not sheriff.is_alive:
            return alive

        others = [p for p in alive if p.player_id != sheriff.player_id]
        after_sheriff = [p for p in others if p.seat_index > sheriff.seat_index]
        before_sheriff = [p for p in others if p.seat_index < sheriff.seat_index]
        if direction == "previous":
            return list(reversed(before_sheriff)) + list(reversed(after_sheriff)) + [sheriff]
        return after_sheriff + before_sheriff + [sheriff]

    def _parse_speaking_order_direction(self, raw_choice: str) -> str:
        text = (raw_choice or "").lower()
        previous_markers = (
            "previous", "prev", "counterclockwise", "counter-clockwise",
            "reverse", "anti-clockwise", "anticlockwise",
            "上一", "前一", "递减", "倒序", "逆序", "逆时针", "警左", "左边",
            "action: previous", "action: prev",
        )
        if any(marker in text for marker in previous_markers):
            return "previous"
        return "next"

    def _announce_day_speaking_order(self, direction: str):
        sheriff = self._get_player(self.sheriff_id) if self.sheriff_id else None
        if not sheriff or not sheriff.is_alive or len(self._day_speaking_order) <= 1:
            return

        ordered = [self._get_player(pid) for pid in self._day_speaking_order]
        labels = [self._seat_label(p) for p in ordered if p]
        direction_text = "上一位开始" if direction == "previous" else "下一位开始"
        if labels:
            text = f"📣 警长 {sheriff.display_name} 决定从{direction_text}发言：{' → '.join(labels)}（警长最后发言）"
            self._add_event(text)
            self._append_history("sheriff_order", "day", text=text, visibility="public")

    def record_speech(self, player_id: str, speech: str, discussion_round: int | None = None, announce: bool = True):
        """记录玩家发言。"""
        p = self._get_player(player_id)
        if p and speech.strip():
            speech = self._extract_public_speech(speech)
            label = self._speech_label("day", discussion_round=discussion_round)
            p.speech_history.append(speech)
            self._speech_log.append({
                "phase": "day",
                "day": self.round_number,
                "round": discussion_round,
                "player_id": player_id,
                "text": speech,
                "label": label,
                "visibility": "public",
            })
            self._append_history("day_speech", "day", player_id=player_id, text=speech, round=discussion_round)
            if announce:
                self._add_event(f"🎤 {p.display_name}：{speech}")

    # ============================================================
    # 白天阶段 - 投票
    # ============================================================

    def start_vote(self) -> WerewolfGameState:
        """进入放逐投票阶段。"""
        self.phase = WerewolfPhase.VOTE
        self.votes = {}
        self.vote_result = None
        self._vote_pk_candidates = []
        self._vote_round = 1
        for p in self.players:
            p.has_voted = False
            p.vote_target = None
        self._add_event("🗳️ 放逐投票开始")
        return self._build_state()

    def start_vote_pk(self) -> WerewolfGameState:
        """进入放逐PK投票阶段。"""
        self.phase = WerewolfPhase.VOTE
        self.votes = {}
        self.vote_result = None
        for p in self.players:
            p.has_voted = False
            p.vote_target = None
        labels = "、".join(self._seat_label(pid) for pid in self._vote_pk_candidates)
        self._add_event(f"🗳️ PK投票开始：只能在 {labels} 中投票")
        return self._build_state()

    def get_vote_pk_candidates(self) -> list[WerewolfPlayerState]:
        """返回当前放逐PK候选人。"""
        return [
            p for p in (self._get_player(pid) for pid in self._vote_pk_candidates)
            if p and p.is_alive
        ]

    def get_voting_players(self) -> list[WerewolfPlayerState]:
        """获取可以投票的玩家。"""
        voters = [p for p in self.players if p.is_alive]
        # 白痴翻牌后不能投票
        voters = [p for p in voters if not p.idiot_revealed]
        if self._vote_pk_candidates:
            pk_ids = set(self._vote_pk_candidates)
            voters = [p for p in voters if p.player_id not in pk_ids]
        return voters

    def cast_vote(self, voter_id: str, action) -> WerewolfGameState:
        """投放逐票。"""
        voter = self._get_player(voter_id)
        if not voter or not voter.is_alive:
            return self._build_state()
        if self._vote_pk_candidates and voter_id in self._vote_pk_candidates:
            return self._build_state()

        raw = ""
        if action is not None:
            raw = (action.raw_response or "").strip()
        target_id = self._parse_target(raw) if raw else None

        # 验证目标
        if target_id:
            target = self._get_player(target_id)
            if not target or not target.is_alive:
                target_id = None
            elif self._vote_pk_candidates and target_id not in self._vote_pk_candidates:
                target_id = None

        if target_id is None:
            # 弃票
            target_id = ""  # 空票

        voter.has_voted = True
        voter.vote_target = target_id if target_id else None
        self.votes[voter_id] = target_id if target_id else ""
        self._add_event(f"🗳️ {voter.display_name} 投票 {'弃权' if not target_id else self._get_player(target_id).display_name}")
        self._append_history("vote", "day", player_id=voter_id, target_id=target_id or "", text="弃权" if not target_id else "")
        return self._build_state()

    def resolve_vote(self) -> WerewolfGameState:
        """统计投票结果，放逐得票最多者。"""
        if not self.votes:
            self.vote_result = {
                "eliminated_id": "",
                "eliminated_name": "",
                "votes": {},
                "tally": {},
                "round": self._vote_round,
                "is_tie": False,
                "tie_ids": [],
                "no_elimination": True,
            }
            self._add_event("无人被放逐")
            self._clear_vote_pk()
            return self._finish_day()

        # 计票（警长1.5票）
        tally: dict[str, float] = {}
        for voter_id, target_id in self.votes.items():
            if not target_id:
                continue
            weight = 1.5 if voter_id == self.sheriff_id else 1.0
            tally[target_id] = tally.get(target_id, 0) + weight

        if not tally:
            self._add_vote_summary_event({})
            self.vote_result = {
                "eliminated_id": "",
                "eliminated_name": "",
                "votes": {k: v for k, v in self.votes.items()},
                "tally": {},
                "round": self._vote_round,
                "is_tie": False,
                "tie_ids": [],
                "no_elimination": True,
            }
            if self._vote_pk_candidates:
                self._add_event("PK投票全部弃票，本轮无人被放逐")
                self._clear_vote_pk()
            else:
                self._add_event("无人被放逐（全部弃票）")
            return self._finish_day()

        self._add_vote_summary_event(tally)

        max_votes = max(tally.values())
        top = [pid for pid, v in tally.items() if v == max_votes]

        if len(top) == 1:
            eliminated_id = top[0]
        else:
            if self._vote_pk_candidates:
                self.vote_result = {
                    "eliminated_id": "",
                    "eliminated_name": "",
                    "votes": {k: v for k, v in self.votes.items()},
                    "tally": {k: v for k, v in tally.items()},
                    "round": self._vote_round,
                    "is_tie": True,
                    "tie_ids": top,
                    "no_elimination": True,
                }
                labels = "、".join(self._seat_label(pid) for pid in top)
                self._add_event(f"PK投票再次平票：{labels}，本轮无人被放逐")
                self._clear_vote_pk()
                return self._finish_day()

            self.vote_result = {
                "eliminated_id": "",
                "eliminated_name": "",
                "votes": {k: v for k, v in self.votes.items()},
                "tally": {k: v for k, v in tally.items()},
                "round": self._vote_round,
                "is_tie": True,
                "tie_ids": top,
                "no_elimination": False,
            }
            self._vote_pk_candidates = top
            self._vote_round = 2
            labels = "、".join(self._seat_label(pid) for pid in top)
            self._add_event(f"放逐投票平票：{labels} 进入PK发言，其余玩家重新投票")
            self.votes = {}
            for p in self.players:
                p.has_voted = False
                p.vote_target = None
            return self._build_state()

        eliminated = self._get_player(eliminated_id)
        if eliminated:
            self._handle_elimination(eliminated)

        result_data = {
            "eliminated_id": eliminated_id,
            "eliminated_name": eliminated.display_name if eliminated else "?",
            "votes": {k: v for k, v in self.votes.items()},
            "tally": {k: v for k, v in tally.items()},
            "round": self._vote_round,
            "is_tie": False,
            "tie_ids": [],
            "no_elimination": False,
        }
        self.vote_result = result_data
        if eliminated:
            self._append_history("vote_result", "day", target_id=eliminated_id, text=f"{eliminated.display_name} 被放逐")
        self._clear_vote_pk()
        return self._finish_day()

    def _clear_vote_pk(self):
        self._vote_pk_candidates = []
        self._vote_round = 1

    def _format_vote_count(self, value: float) -> str:
        return str(int(value)) if float(value).is_integer() else f"{value:g}"

    def _add_vote_summary_event(self, tally: dict[str, float]):
        """Add a public vote distribution event for spectators."""
        tally_lines = []
        for target_id, count in sorted(tally.items(), key=lambda item: (-item[1], self._get_player(item[0]).seat_index if self._get_player(item[0]) else 99)):
            target = self._get_player(target_id)
            if target:
                tally_lines.append(f"{target.display_name}：{self._format_vote_count(count)}票")

        abstain_count = sum(1 for target_id in self.votes.values() if not target_id)
        if abstain_count:
            tally_lines.append(f"弃权：{abstain_count}人")

        flow_lines = []
        for voter_id, target_id in self.votes.items():
            voter = self._get_player(voter_id)
            if not voter:
                continue
            target = self._get_player(target_id) if target_id else None
            weight = "（警长1.5票）" if voter_id == self.sheriff_id and target_id else ""
            flow_lines.append(
                f"{voter.display_name} → {target.display_name if target else '弃权'}{weight}"
            )

        tally_text = "；".join(tally_lines) if tally_lines else "无有效票"
        flow_text = "；".join(flow_lines) if flow_lines else "无投票明细"
        self._add_event(f"📊 投票分布：{tally_text}\n投票明细：{flow_text}")

    def _handle_elimination(self, player: WerewolfPlayerState):
        """处理玩家被放逐。"""
        player.is_alive = False
        player.death_cause = "voted_out"
        player.death_round = self.round_number
        self._add_event(f"⚖️ {player.display_name} 被放逐出局")

        # 白痴翻牌
        if player.role_id == RoleID.IDIOT and not player.idiot_revealed:
            player.idiot_revealed = True
            player.is_alive = True  # 白痴免死
            self._add_event(f"🃏 {player.display_name} 翻牌为白痴，免于放逐（失去投票权）")
            return

        # 猎人开枪
        if player.role_id == RoleID.HUNTER:
            player.hunter_can_shoot = True
            self._add_event(f"🔫 {player.display_name} 是猎人，可以开枪！")

        # 警长传递
        if player.player_id == self.sheriff_id:
            self._handle_sheriff_succession()

    def _finish_day(self) -> WerewolfGameState:
        """结束白天，检查胜负，进入下一轮。"""
        self.round_number += 1
        if self.is_game_over():
            self.phase = WerewolfPhase.GAME_OVER
            self.is_over = True
            self._add_event(f"游戏结束！{'好人阵营' if self.winner_team == 'villager' else '狼人阵营'} 获胜！")
        else:
            self._discussion_round = 0
        return self._build_state()

    # ============================================================
    # 辅助方法
    # ============================================================

    def _get_player(self, player_id: str) -> WerewolfPlayerState | None:
        for p in self.players:
            if p.player_id == player_id:
                return p
        return None

    def _seat_label(self, player_or_id) -> str:
        player = self._get_player(player_or_id) if isinstance(player_or_id, str) else player_or_id
        if player:
            return f"{player.seat_index + 1}号"
        return "未知号"

    def _append_history(
        self,
        kind: str,
        phase: str,
        *,
        player_id: str = "",
        target_id: str = "",
        text: str = "",
        visibility: str = "public",
        round: int | None = None,
    ):
        self._history_log.append({
            "kind": kind,
            "phase": phase,
            "day": self.round_number,
            "round": round,
            "player_id": player_id,
            "target_id": target_id,
            "text": text,
            "visibility": visibility,
        })

    def _speech_label(self, phase: str, discussion_round: int | None = None) -> str:
        if phase == "sheriff":
            return f"第{self.round_number}天-白天 警长竞选"
        if phase == "werewolf_night":
            suffix = f" 第{discussion_round}轮" if discussion_round else ""
            return f"第{self.round_number}天-夜晚 狼人交流{suffix}"
        if phase == "day":
            suffix = f" 第{discussion_round}轮" if discussion_round else ""
            return f"第{self.round_number}天-白天 自由发言{suffix}"
        return f"第{self.round_number}天"

    def _extract_public_speech(self, raw: str) -> str:
        """Extract viewer-facing speech from a labeled model response."""
        text = (raw or "").strip()
        if not text:
            return "（无发言）"

        label = r'(?:ACTION|SPEECH|VOTE|NOTES|TARGET|动作|发言|投票|笔记|目标)'
        speech_blocks = re.findall(
            rf'(?is)(?:^|\n)\s*SPEECH\s*[:：]\s*(.*?)(?=\n\s*{label}\s*[:：]|\Z)',
            text,
        )
        if speech_blocks:
            text = speech_blocks[-1].strip()
        else:
            nested = re.search(r'(?is)(?:^|\n)\s*ACTION\s*[:：]\s*SPEECH\s*[:：]\s*(.*?)(?=\n\s*{label}\s*[:：]|\Z)', text)
            if nested:
                text = nested.group(1).strip()
            else:
                text = re.sub(rf'(?is)(?:^|\n)\s*(?:ACTION|VOTE|NOTES|TARGET|动作|投票|笔记|目标)\s*[:：].*?(?=\n\s*{label}\s*[:：]|\Z)', '\n', text)
                text = re.sub(r'(?im)^\s*SPEECH\s*[:：]\s*', '', text).strip()

        text = re.sub(r'(?im)^\s*(?:ACTION|VOTE|NOTES|TARGET|动作|投票|笔记|目标)\s*[:：].*$', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text or "（无发言）"

    def _add_event(self, text: str, hidden: bool = False):
        self._events.append({"text": text, "hidden": hidden})

    def _build_state(self) -> WerewolfGameState:
        return WerewolfGameState(
            tournament_id=self.tournament_id,
            game_type="werewolf",
            round_number=self.round_number,
            phase=self.phase,
            players=list(self.players),
            night_kill_target=self.night_kill_target,
            night_check_result=self.night_check_result,
            night_save_target=self.night_save_target,
            night_poison_target=self.night_poison_target,
            night_guard_target=self.night_guard_target,
            sheriff_id=self.sheriff_id,
            sheriff_candidates=list(self._sheriff_candidates),
            speaking_order=[p.player_id for p in self.get_speaking_order()],
            current_speaker=None,
            votes=dict(self.votes),
            vote_result=self.vote_result,
            sheriff_vote_result=self.sheriff_vote_result,
            events=list(self._events[-50:]),
            night_log=list(self._night_log[-20:]),
            is_over=self.is_over,
            winner_team=getattr(self, 'winner_team', None),
        )


# Auto-register werewolf game type
from app.core.game_registry import register_game
from app.models.werewolf import WerewolfConfig as _WerewolfConfig
register_game("werewolf", WerewolfEngine, _WerewolfConfig)

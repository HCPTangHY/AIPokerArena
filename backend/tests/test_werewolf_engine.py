"""狼人杀引擎单元测试"""

import pytest
from app.models.werewolf import (
    WerewolfPhase, Team, RoleID, WerewolfConfig,
    WerewolfPlayerState, WerewolfGameState, BoardPreset,
)
from app.models.player import AIPlayerConfig
from app.core.werewolf_engine import WerewolfEngine


def make_players(n: int) -> list[AIPlayerConfig]:
    return [
        AIPlayerConfig(
            id=f"player_{i}",
            display_name=f"Player {i}",
            api_endpoint="https://test.api/v1",
            api_key="test-key",
            model_name="test-model",
        )
        for i in range(n)
    ]


def make_config(board_preset: str = "预女猎白-9人", **kwargs) -> WerewolfConfig:
    cfg = {"board_preset": board_preset, "max_players": 12}
    cfg.update(kwargs)
    return WerewolfConfig(**cfg)


class TestWerewolfEngine:
    """测试狼人杀引擎核心逻辑"""

    def test_init_and_role_assignment(self):
        """测试初始化和角色分配"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        state = engine.start_game()

        assert state.phase == WerewolfPhase.ROLE_ASSIGN
        assert state.round_number == 1
        assert len(state.players) == 9

        # 检查角色分配
        role_counts = {}
        for p in state.players:
            assert p.role_id is not None
            assert p.role_name != ""
            assert p.team is not None
            role_counts[p.role_id.value] = role_counts.get(p.role_id.value, 0) + 1

        # 预女猎白-9人：3狼 + 1预言家 + 1女巫 + 1猎人 + 0白痴 + 3村民
        assert role_counts.get("werewolf", 0) == 3
        assert role_counts.get("seer", 0) == 1
        assert role_counts.get("witch", 0) == 1
        assert role_counts.get("hunter", 0) == 1
        assert role_counts.get("villager", 0) == 3

    def test_board_presets(self):
        """测试不同板子预设"""
        test_cases = [
            ("预女猎白-6人", 6, {"werewolf": 2, "seer": 1, "witch": 1, "hunter": 1, "villager": 1}),
            ("预女猎白-9人", 9, {"werewolf": 3, "seer": 1, "witch": 1, "hunter": 1, "villager": 3}),
            ("预女猎白-12人", 12, {"werewolf": 4, "seer": 1, "witch": 1, "hunter": 1, "idiot": 1, "villager": 4}),
            ("预女猎守-12人", 12, {"werewolf": 4, "seer": 1, "witch": 1, "hunter": 1, "guard": 1, "villager": 4}),
        ]

        for preset_name, n, expected in test_cases:
            players = make_players(n)
            config = make_config(board_preset=preset_name)
            engine = WerewolfEngine(config, players)
            state = engine.start_game()

            role_counts = {}
            for p in state.players:
                role_counts[p.role_id.value] = role_counts.get(p.role_id.value, 0) + 1

            for role_id, count in expected.items():
                assert role_counts.get(role_id, 0) == count, \
                    f"{preset_name}: expected {count} {role_id}, got {role_counts.get(role_id, 0)}"

    def test_custom_roles(self):
        """测试自定义角色配置"""
        players = make_players(6)
        config = make_config(custom_roles={"werewolf": 2, "seer": 1, "witch": 1, "hunter": 1, "villager": 1})
        engine = WerewolfEngine(config, players)
        state = engine.start_game()

        role_counts = {}
        for p in state.players:
            role_counts[p.role_id.value] = role_counts.get(p.role_id.value, 0) + 1

        assert role_counts["werewolf"] == 2
        assert role_counts["villager"] == 1

    def test_role_mismatch_raises(self):
        """测试角色数量与玩家数不匹配时抛出异常"""
        players = make_players(5)
        config = make_config(board_preset="预女猎白-9人")  # expects 9
        with pytest.raises(ValueError):
            WerewolfEngine(config, players)

    def test_sheriff_election(self):
        """测试警长竞选环节"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        # 设置候选人
        candidates = [players[0].id, players[1].id]
        engine.set_sheriff_candidates(candidates)
        assert engine.get_sheriff_candidates() == candidates
        assert [p.player_id for p in engine.get_sheriff_voters()] == [p.id for p in players[2:]]

        # 投票
        engine.cast_sheriff_vote(players[0].id, candidates[1])
        for i in range(2, 7):
            engine.cast_sheriff_vote(players[i].id, candidates[0])
        engine.cast_sheriff_vote(players[7].id, candidates[1])
        engine.cast_sheriff_vote(players[8].id, None)

        state = engine.resolve_sheriff_election()
        assert engine.sheriff_id == candidates[0]
        sheriff = engine._get_player(candidates[0])
        assert sheriff.is_sheriff
        assert state.sheriff_vote_result is not None
        assert state.sheriff_vote_result["winner_id"] == candidates[0]
        assert state.sheriff_vote_result["tally"][candidates[0]] == 5
        assert players[0].id not in state.sheriff_vote_result["votes"]
        assert state.sheriff_vote_result["votes"][players[8].id] == ""
        vote_summary = next(event["text"] for event in state.events if "警长票型" in event["text"])
        assert "投票明细" in vote_summary
        assert "Player 0：5票" in vote_summary
        assert "Player 8 → 弃权/无效" in vote_summary

    def test_sheriff_election_tie_runs_pk_then_no_badge(self):
        """警长第一轮平票进入PK，再次平票则本局无警徽。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        candidates = [players[0].id, players[1].id, players[2].id]
        engine.set_sheriff_candidates(candidates)
        engine.cast_sheriff_vote(players[3].id, candidates[0])
        engine.cast_sheriff_vote(players[4].id, candidates[1])
        engine.cast_sheriff_vote(players[5].id, candidates[0])
        engine.cast_sheriff_vote(players[6].id, candidates[1])
        engine.cast_sheriff_vote(players[7].id, None)
        engine.cast_sheriff_vote(players[8].id, None)

        state = engine.resolve_sheriff_election()
        assert engine.sheriff_id is None
        assert state.sheriff_vote_result["is_tie"] is True
        assert state.sheriff_vote_result["no_sheriff"] is False
        assert set(engine.get_sheriff_candidates()) == {candidates[0], candidates[1]}
        assert candidates[2] not in [p.player_id for p in engine.get_sheriff_voters()]
        assert "进入PK发言" in state.events[-1]["text"]

        engine.cast_sheriff_vote(players[3].id, candidates[0])
        engine.cast_sheriff_vote(players[4].id, candidates[1])
        state = engine.resolve_sheriff_election()

        assert engine.sheriff_id is None
        assert state.sheriff_vote_result["is_tie"] is True
        assert state.sheriff_vote_result["no_sheriff"] is True
        assert engine.get_sheriff_candidates() == []
        assert "本局无警徽" in state.events[-1]["text"]

    def test_day_speaking_order_puts_sheriff_last(self):
        """白天发言应由警长决定顺序，警长最后发言。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        sheriff_id = players[1].id
        engine.sheriff_id = sheriff_id
        sheriff = engine._get_player(sheriff_id)
        sheriff.is_sheriff = True

        state = engine.start_day()
        order = engine.get_speaking_order()

        assert order[-1].player_id == sheriff_id
        assert state.speaking_order[-1] == sheriff_id
        assert order[0].seat_index == sheriff.seat_index + 1

    def test_sheriff_can_choose_reverse_day_speaking_order(self):
        """警长可选择从上一号开始倒序发言，但自己仍最后发言。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        sheriff_id = players[4].id
        engine.sheriff_id = sheriff_id
        sheriff = engine._get_player(sheriff_id)
        sheriff.is_sheriff = True
        engine.start_day()

        state = engine.decide_day_speaking_order("previous")
        order = engine.get_speaking_order()

        assert order[0].seat_index == sheriff.seat_index - 1
        assert order[-1].player_id == sheriff_id
        assert state.speaking_order[-1] == sheriff_id
        assert "警长最后发言" in state.events[-1]["text"]

        state = engine.decide_day_speaking_order("next")
        order = engine.get_speaking_order()

        assert order[0].seat_index == sheriff.seat_index + 1
        assert order[-1].player_id == sheriff_id
        assert state.speaking_order[-1] == sheriff_id

    def test_night_kill(self):
        """测试夜晚狼人刀人（通过kill decision流程）"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        # 跳过警长
        engine.set_sheriff_candidates([players[0].id])
        for i in range(1, 9):
            engine.cast_sheriff_vote(players[i].id, players[0].id)
        engine.resolve_sheriff_election()

        # 夜晚
        engine.start_night()
        assert engine.phase == WerewolfPhase.NIGHT

        # 狼人讨论
        assert engine.needs_werewolf_discussion()
        engine.mark_werewolf_discussed()

        # 狼人刀人决策
        assert engine.needs_werewolf_kill_decision()
        kill_info = engine.get_werewolf_kill_action_info()
        assert kill_info is not None
        assert len(kill_info["targets"]) > 0

        victim = next(p for p in engine.players if p.team != Team.WEREWOLF and p.is_alive)

        from app.models.game import PlayerAction
        from app.models.tournament import ActionType
        action = PlayerAction(
            player_id=kill_info["player_id"],
            action_type=ActionType.CALL,
            raw_response=victim.display_name,
        )
        engine.apply_night_action(kill_info["player_id"], action)
        assert engine.night_kill_target == victim.player_id
        assert engine._werewolf_kill_decided

    def test_win_condition_werewolves(self):
        """测试狼人胜利条件"""
        players = make_players(6)
        config = make_config(board_preset="预女猎白-6人")
        engine = WerewolfEngine(config, players)
        engine.start_game()

        # 杀掉所有好人
        for p in engine.players:
            if p.team == Team.VILLAGER:
                p.is_alive = False

        assert engine.is_game_over()
        assert engine.winner_team == "werewolf"

    def test_win_condition_villagers(self):
        """测试好人胜利条件"""
        players = make_players(6)
        config = make_config(board_preset="预女猎白-6人")
        engine = WerewolfEngine(config, players)
        engine.start_game()

        # 杀掉所有狼人
        for p in engine.players:
            if p.team == Team.WEREWOLF:
                p.is_alive = False

        assert engine.is_game_over()
        assert engine.winner_team == "villager"

    def test_vote_elimination(self):
        """测试投票放逐"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        engine.set_sheriff_candidates([players[0].id])
        engine.cast_sheriff_vote(players[1].id, players[0].id)
        engine.resolve_sheriff_election()

        engine.start_vote()

        from app.models.game import PlayerAction
        from app.models.tournament import ActionType

        # 所有人投票给玩家2
        for p in engine.get_voting_players():
            if p.player_id != players[2].id:
                action = PlayerAction(
                    player_id=p.player_id,
                    action_type=ActionType.CALL,
                    raw_response=players[2].display_name,
                )
                engine.cast_vote(p.player_id, action)

        result = engine.resolve_vote()
        # 玩家2应该被放逐
        assert not engine._get_player(players[2].id).is_alive
        assert engine._get_player(players[2].id).death_cause == "voted_out"
        vote_summary = next(event["text"] for event in result.events if "投票分布" in event["text"])
        assert "投票明细" in vote_summary
        assert "Player 2" in vote_summary
        assert "警长1.5票" in vote_summary

    def test_vote_tie_runs_pk_then_no_elimination_on_second_tie(self):
        """放逐第一轮平票进入PK，再次平票则本轮无人出局。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()
        engine.start_vote()

        from app.models.game import PlayerAction
        from app.models.tournament import ActionType

        def vote(voter_idx: int, target_idx: int | None):
            raw = f"ACTION: {target_idx + 1}号" if target_idx is not None else "ACTION: skip"
            engine.cast_vote(
                players[voter_idx].id,
                PlayerAction(player_id=players[voter_idx].id, action_type=ActionType.CALL, raw_response=raw),
            )

        vote(0, 2)
        vote(1, 3)
        vote(2, 3)
        vote(3, 2)
        vote(4, None)
        vote(5, None)

        state = engine.resolve_vote()
        assert state.round_number == 1
        assert state.vote_result["is_tie"] is True
        assert state.vote_result["no_elimination"] is False
        assert {p.player_id for p in engine.get_vote_pk_candidates()} == {players[2].id, players[3].id}
        assert players[2].id not in [p.player_id for p in engine.get_voting_players()]
        assert "进入PK发言" in state.events[-1]["text"]

        from app.prompts.werewolf_builder import WerewolfPromptBuilder
        builder = WerewolfPromptBuilder(engine)
        prompt = builder.build_vote_prompt(players[0])
        assert "本轮PK候选" in prompt
        assert "3号玩家" in prompt
        assert "4号玩家" in prompt

        engine.start_vote_pk()
        vote(0, 2)
        vote(1, 3)
        vote(4, None)
        vote(5, None)

        state = engine.resolve_vote()
        assert state.round_number == 2
        assert state.vote_result["is_tie"] is True
        assert state.vote_result["no_elimination"] is True
        assert engine._get_player(players[2].id).is_alive
        assert engine._get_player(players[3].id).is_alive
        assert "本轮无人被放逐" in state.events[-1]["text"]

    def test_vote_tie_pk_can_eliminate_second_round_winner(self):
        """放逐PK二轮出现最高票时，该玩家出局。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()
        engine.start_vote()

        from app.models.game import PlayerAction
        from app.models.tournament import ActionType

        def vote(voter_idx: int, target_idx: int | None):
            raw = f"ACTION: {target_idx + 1}号" if target_idx is not None else "ACTION: skip"
            engine.cast_vote(
                players[voter_idx].id,
                PlayerAction(player_id=players[voter_idx].id, action_type=ActionType.CALL, raw_response=raw),
            )

        vote(0, 2)
        vote(1, 3)
        vote(2, 3)
        vote(3, 2)
        state = engine.resolve_vote()
        assert state.vote_result["is_tie"] is True

        engine.start_vote_pk()
        vote(0, 2)
        vote(1, 2)
        vote(4, 2)
        vote(5, 3)
        state = engine.resolve_vote()

        assert not engine._get_player(players[2].id).is_alive
        assert engine._get_player(players[2].id).death_cause == "voted_out"
        assert state.vote_result["round"] == 2
        assert state.vote_result["is_tie"] is False

    def test_game_state_serialization(self):
        """测试游戏状态序列化"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        state = engine.start_game()

        d = state.to_public_dict()
        assert d["game_type"] == "werewolf"
        assert d["phase"] == "role_assign"
        assert len(d["players"]) == 9
        # 观战者看不到角色
        for p in d["players"]:
            assert "display_name" in p
            assert "is_alive" in p

    def test_role_library(self):
        """测试角色库完整性"""
        from app.models.werewolf import ROLE_LIBRARY
        assert len(ROLE_LIBRARY) >= 7
        assert ROLE_LIBRARY[RoleID.WEREWOLF].team == Team.WEREWOLF
        assert ROLE_LIBRARY[RoleID.SEER].team == Team.VILLAGER
        assert ROLE_LIBRARY[RoleID.WITCH].max_uses == 2
        assert ROLE_LIBRARY[RoleID.HUNTER].kills_on_elimination

    def test_game_registry(self):
        """测试游戏注册表"""
        import app.core.engine  # noqa: trigger poker registration
        from app.core.game_registry import get_engine_class, get_registered_games

        registered = get_registered_games()
        assert "poker" in registered
        assert "werewolf" in registered

        engine_cls = get_engine_class("werewolf")
        assert engine_cls == WerewolfEngine


class TestWerewolfConsensus:
    """测试狼人夜间共识投票机制"""

    def test_single_wolf_no_discussion_needed(self):
        """单狼人不需要讨论"""
        players = make_players(6)
        config = make_config(custom_roles={"werewolf": 1, "seer": 1, "witch": 1, "hunter": 1, "villager": 2})
        engine = WerewolfEngine(config, players)
        engine.start_game()

        assert not engine.needs_werewolf_discussion()
        assert engine.needs_werewolf_kill_decision()

    def test_consensus_not_reached_initially(self):
        """初始状态未达成共识"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        assert not engine.is_werewolf_consensus_reached()

    def test_consensus_reached_when_all_vote_same(self):
        """所有狼人投同一目标时达成共识"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        wolves = engine.get_alive_werewolves()
        victim = next(p for p in engine.players if p.team != Team.WEREWOLF and p.is_alive)

        # 所有狼人都投票同一个目标
        for w in wolves:
            engine._werewolf_votes[w.player_id] = victim.player_id

        assert engine.is_werewolf_consensus_reached()
        assert engine.get_consensus_target() == victim.player_id

    def test_consensus_not_reached_with_split_votes(self):
        """投票分裂时未达成共识"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        wolves = engine.get_alive_werewolves()
        victims = [p for p in engine.players if p.team != Team.WEREWOLF and p.is_alive]

        # 狼人投不同目标
        for i, w in enumerate(wolves):
            engine._werewolf_votes[w.player_id] = victims[i % len(victims)].player_id

        assert not engine.is_werewolf_consensus_reached()
        assert engine.get_consensus_target() is None

    def test_consensus_not_reached_when_not_all_voted(self):
        """部分狼人未投票时未达成共识"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        wolves = engine.get_alive_werewolves()
        victim = next(p for p in engine.players if p.team != Team.WEREWOLF and p.is_alive)

        # 只有一个狼人投票
        engine._werewolf_votes[wolves[0].player_id] = victim.player_id

        assert not engine.is_werewolf_consensus_reached()

    def test_vote_parsed_from_speech(self):
        """投票从发言中解析"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        wolf = engine.get_alive_werewolves()[0]
        victim = next(p for p in engine.players if p.team != Team.WEREWOLF and p.is_alive)

        engine.record_werewolf_discussion(
            wolf.player_id,
            f"我觉得应该刀{victim.display_name}，他太像预言家了。VOTE: {victim.display_name}",
        )

        votes = engine.get_werewolf_votes()
        assert wolf.player_id in votes
        assert votes[wolf.player_id] == victim.player_id

    def test_vote_parsed_from_seat_number(self):
        """投票支持玩家编号，避免依赖玩家名字。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        wolf = engine.get_alive_werewolves()[0]
        victim = next(p for p in engine.players if p.team != Team.WEREWOLF and p.is_alive)

        engine.record_werewolf_discussion(
            wolf.player_id,
            f"SPEECH: 我建议先处理{victim.seat_index + 1}号，发言压力最大。\n"
            f"VOTE: {victim.seat_index + 1}号\n"
            "NOTES: 首夜目标已确认",
        )

        votes = engine.get_werewolf_votes()
        assert votes[wolf.player_id] == victim.player_id

    def test_public_speech_strips_control_labels(self):
        """公开事件只展示发言，不把 ACTION/VOTE/NOTES 原文甩给观众。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        speaker = engine.players[0]
        engine.record_speech(
            speaker.player_id,
            "ACTION: SPEECH: 第一晚没信息，我会先听后置位。\n"
            "VOTE: 3号\n"
            "SPEECH: 第一晚没信息，我会先听后置位。\n"
            "NOTES: 暂不暴露身份",
        )

        text = engine.get_state().events[-1]["text"]
        assert "第一晚没信息" in text
        assert "ACTION:" not in text
        assert "VOTE:" not in text
        assert "NOTES:" not in text

    def test_kill_info_includes_consensus(self):
        """刀人行动信息包含共识状态"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        wolves = engine.get_alive_werewolves()
        victim = next(p for p in engine.players if p.team != Team.WEREWOLF and p.is_alive)

        # 达成共识
        for w in wolves:
            engine._werewolf_votes[w.player_id] = victim.player_id

        kill_info = engine.get_werewolf_kill_action_info()
        assert kill_info["consensus_reached"]
        assert kill_info["consensus_target"] == victim.player_id


class TestNightActions:
    """测试夜晚行动细节"""

    def test_seer_check(self):
        """测试预言家查验"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        seer = next(p for p in engine.players if p.role_id == RoleID.SEER)
        target = next(p for p in engine.players if p.team == Team.WEREWOLF)

        # 构建查验targets
        targets = engine._get_valid_night_targets(seer)
        target_ids = [t["player_id"] for t in targets]
        assert seer.player_id not in target_ids  # 不能查自己
        assert target.player_id in target_ids  # 能查狼人

    def test_seer_check_adds_spectator_event(self):
        """预言家查验结果对观众可见，但不进入其他玩家的提示词历史。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        seer = next(p for p in engine.players if p.role_id == RoleID.SEER)
        target = next(p for p in engine.players if p.player_id != seer.player_id)

        from app.models.tournament import ActionType
        from app.models.game import PlayerAction
        action = PlayerAction(
            player_id=seer.player_id,
            action_type=ActionType.CALL,
            raw_response=f"ACTION: {target.seat_index + 1}号",
        )
        engine.apply_night_action(seer.player_id, action)

        event = engine.get_state().events[-1]
        text = event["text"]
        assert event["hidden"] is False
        assert "预言家查验" in text
        assert f"{target.seat_index + 1}号" in text
        assert "狼人" in text or "好人" in text
        public_texts = [event["text"] for event in engine.get_state().events if not event.get("hidden")]
        assert any("预言家查验" in text for text in public_texts)

    def test_saved_kill_reports_silent_night_in_prompt(self):
        """被救或被守导致无人死亡时，公开信息和白天提示词都只说平安夜。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()
        engine.start_night()

        witch = next(p for p in engine.players if p.role_id == RoleID.WITCH)
        victim = next(p for p in engine.players if p.team != Team.WEREWOLF and p.player_id != witch.player_id)
        engine.night_kill_target = victim.player_id
        engine.night_save_target = victim.player_id

        state = engine.resolve_night()
        assert state.events[-1]["text"] == "☀️ 天亮了，昨晚是平安夜"
        public_texts = [event["text"] for event in state.events if not event.get("hidden")]
        assert all("女巫使用解药" not in text for text in public_texts)

        from app.prompts.werewolf_builder import WerewolfPromptBuilder
        builder = WerewolfPromptBuilder(engine)
        speaker = next(p for p in engine.players if p.is_alive)
        prompt = builder.build_discussion_prompt(players[int(speaker.player_id.removeprefix("player_"))])
        system_prompt = builder.build_system_prompt(players[int(speaker.player_id.removeprefix("player_"))])

        assert "昨晚情况：平安夜" in prompt
        assert "狼人袭击" not in prompt
        assert "女巫救活" not in prompt
        assert "天亮了，昨晚是平安夜" in prompt
        assert "（公开）" not in prompt
        assert "【你的视角历史记录】" not in system_prompt

    def test_night_death_reports_morning_result_before_day_speech(self):
        """夜晚死亡公开为第二天白天的天亮信息。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()
        engine.start_night()

        victim = next(p for p in engine.players if p.team != Team.WEREWOLF)
        engine.night_kill_target = victim.player_id

        state = engine.resolve_night()
        assert state.events[-1]["text"] == f"☀️ 天亮了，昨晚 {victim.display_name} 死亡"

        from app.prompts.werewolf_builder import WerewolfPromptBuilder
        builder = WerewolfPromptBuilder(engine)
        speaker = next(p for p in engine.players if p.is_alive)
        prompt = builder.build_discussion_prompt(players[int(speaker.player_id.removeprefix("player_"))])
        system_prompt = builder.build_system_prompt(players[int(speaker.player_id.removeprefix("player_"))])

        assert f"昨晚情况：{victim.seat_index + 1}号玩家 死亡" in prompt
        assert "【第1天-白天】" in prompt
        assert "【天亮信息】" in prompt
        assert prompt.index("【天亮信息】") < prompt.index("天亮了，昨晚")
        assert "【你的视角历史记录】" not in system_prompt

    def test_prompt_history_is_player_perspective(self):
        """提示词包含玩家视角全量历史，但不把私有查验泄露给其他玩家。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        seer = next(p for p in engine.players if p.role_id == RoleID.SEER)
        villager = next(p for p in engine.players if p.role_id == RoleID.VILLAGER)
        target = next(p for p in engine.players if p.player_id != seer.player_id)

        engine.record_speech(villager.player_id, "SPEECH: 我先听1号玩家发言")

        from app.models.tournament import ActionType
        from app.models.game import PlayerAction
        action = PlayerAction(
            player_id=seer.player_id,
            action_type=ActionType.CALL,
            raw_response=f"ACTION: {target.seat_index + 1}号",
        )
        engine.apply_night_action(seer.player_id, action)

        from app.prompts.werewolf_builder import WerewolfPromptBuilder
        builder = WerewolfPromptBuilder(engine)

        seer_system = builder.build_system_prompt(players[int(seer.player_id.removeprefix("player_"))])
        seer_prompt = builder.build_discussion_prompt(players[int(seer.player_id.removeprefix("player_"))])
        villager_prompt = builder.build_discussion_prompt(players[int(villager.player_id.removeprefix("player_"))])

        assert "【你的视角历史记录】" in seer_prompt
        assert "你的视角历史信息：" in seer_prompt
        assert "之前的发言记录" not in seer_prompt
        assert "板子：预女猎白-9人" in seer_system
        assert "狼人×3" in seer_system
        assert "预言家×1" in seer_system
        assert "警长规则：开启" in seer_system
        assert "【你的视角历史记录】" not in seer_system
        assert "【第1天-白天】" in seer_prompt
        assert "【轮流发言】" in seer_prompt
        assert "我先听1号玩家发言" in seer_prompt
        assert f"查验 {target.seat_index + 1}号玩家" in seer_prompt
        assert "🔮 预言家查验" not in villager_prompt
        assert f"查验 {target.seat_index + 1}号玩家" not in villager_prompt
        assert "Player " not in seer_prompt

    def test_prompt_speech_history_uses_actual_order(self):
        """提示词发言历史按真实记录顺序，而不是按玩家/模型顺序。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        first = engine.players[4]
        second = engine.players[1]
        viewer = engine.players[0]
        engine.record_speech(first.player_id, "SPEECH: 我是先发言的人")
        engine.record_speech(second.player_id, "SPEECH: 我是后发言的人")

        from app.prompts.werewolf_builder import WerewolfPromptBuilder
        builder = WerewolfPromptBuilder(engine)
        prompt = builder.build_discussion_prompt(players[int(viewer.player_id.removeprefix("player_"))])

        assert prompt.index("5号玩家: 我是先发言的人") < prompt.index("2号玩家: 我是后发言的人")

    def test_prompt_speech_history_has_phase_time_labels(self):
        """提示词发言历史带有第几天、昼夜和环节标签。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        wolf = engine.get_alive_werewolves()[0]
        villager = next(p for p in engine.players if p.role_id == RoleID.VILLAGER)
        engine.record_sheriff_speech(villager.player_id, "SPEECH: 我上警")
        engine.record_werewolf_discussion(wolf.player_id, "SPEECH: 夜聊内容\nVOTE: 3号", discussion_round=1)
        engine.record_speech(villager.player_id, "SPEECH: 白天发言", discussion_round=2)

        from app.prompts.werewolf_builder import WerewolfPromptBuilder
        builder = WerewolfPromptBuilder(engine)
        wolf_prompt = builder.build_discussion_prompt(players[int(wolf.player_id.removeprefix("player_"))])

        assert "【第1天-夜晚】" in wolf_prompt
        assert "【狼人交流 第1轮】" in wolf_prompt
        assert "【第1天-白天】" in wolf_prompt
        assert "【警长竞选】" in wolf_prompt
        assert "【轮流发言】" in wolf_prompt

    def test_non_werewolf_prompt_does_not_include_werewolf_night_chat(self):
        """非狼人视角不应在夜晚消息历史里看到狼队夜聊。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        wolf = engine.get_alive_werewolves()[0]
        villager = next(p for p in engine.players if p.role_id == RoleID.VILLAGER)
        engine.record_werewolf_discussion(wolf.player_id, "SPEECH: 今晚刀3号\nVOTE: 3号")

        from app.prompts.werewolf_builder import WerewolfPromptBuilder
        builder = WerewolfPromptBuilder(engine)
        wolf_prompt = builder.build_discussion_prompt(players[int(wolf.player_id.removeprefix("player_"))])
        villager_prompt = builder.build_discussion_prompt(players[int(villager.player_id.removeprefix("player_"))])

        assert "今晚刀3号" in wolf_prompt
        assert "今晚刀3号" not in villager_prompt

    def test_guard_cannot_protect_same_twice(self):
        """测试守卫不能连续守护同一人"""
        players = make_players(12)
        config = make_config(board_preset="预女猎守-12人")
        engine = WerewolfEngine(config, players)
        engine.start_game()

        guard = next(p for p in engine.players if p.role_id == RoleID.GUARD)
        target = next(p for p in engine.players if p.player_id != guard.player_id)

        # 第一晚守护
        guard.guard_last_protected = target.player_id
        # 第二晚不能再守护同一人
        targets = engine._get_valid_night_targets(guard)
        target_ids = [t["player_id"] for t in targets]
        assert target.player_id not in target_ids

    def test_witch_uses_limited(self):
        """测试女巫能力次数限制"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()

        witch = next(p for p in engine.players if p.role_id == RoleID.WITCH)
        assert not witch.witch_save_used
        assert not witch.witch_poison_used

        witch.witch_save_used = True
        witch.witch_poison_used = True

        # 模拟夜晚开始（狼人讨论已完成）
        engine._werewolf_discussed = True
        engine._werewolf_kill_decided = True
        engine._night_actions_done = set()
        engine._pending_night_actions = []

        from app.models.tournament import ActionType
        from app.models.game import PlayerAction

        action_info = engine.get_next_night_action()
        # 女巫用完了药就不在待处理列表中了
        assert action_info is None or action_info.get("player_id") != witch.player_id

    def test_witch_save_uses_wolf_kill_target(self):
        """女巫回复 ACTION: save 时自动救狼人刀口。"""
        players = make_players(9)
        config = make_config()
        engine = WerewolfEngine(config, players)
        engine.start_game()
        engine.start_night()

        witch = next(p for p in engine.players if p.role_id == RoleID.WITCH)
        victim = next(p for p in engine.players if p.team != Team.WEREWOLF and p.player_id != witch.player_id)
        engine.night_kill_target = victim.player_id
        engine._werewolf_discussed = True
        engine._werewolf_kill_decided = True

        action_info = engine.get_next_night_action()
        while action_info and action_info["player_id"] != witch.player_id:
            engine.skip_night_action(action_info["player_id"])
            action_info = engine.get_next_night_action()

        assert action_info is not None
        assert action_info["player_id"] == witch.player_id
        assert action_info["action_type"] == "witch"
        assert action_info["killed_target"]["player_id"] == victim.player_id

        from app.models.tournament import ActionType
        from app.models.game import PlayerAction
        action = PlayerAction(
            player_id=witch.player_id,
            action_type=ActionType.CALL,
            raw_response="ACTION: save",
        )
        engine.apply_night_action(witch.player_id, action)

        assert witch.witch_save_used
        assert engine.night_save_target == victim.player_id

"""Unit tests for the poker engine."""
import pytest
from app.core.engine import PokerEngine
from app.core.side_pots import calculate_side_pots
from app.core.evaluator import evaluate_hand, determine_winners, get_hand_name
from app.models.tournament import TournamentConfig, ActionType, BlindLevel
from app.models.player import AIPlayerConfig
from app.models.game import PlayerAction


def make_config(**kwargs) -> TournamentConfig:
    defaults = {
        "initial_chips": 5000,
        "small_blind_initial": 10,
        "big_blind_initial": 20,
        "max_players": 10,
    }
    defaults.update(kwargs)
    return TournamentConfig(**defaults)


def make_player(id: str, name: str = "") -> AIPlayerConfig:
    return AIPlayerConfig(
        id=id,
        display_name=name or id,
        api_endpoint="http://test",
        api_key="test",
        model_name="test",
    )


class TestSidePots:
    def test_simple_no_side_pot(self):
        """All players contribute the same amount — one pot."""
        bets = {"A": 100, "B": 100, "C": 100}
        active = {"A", "B", "C"}
        pots = calculate_side_pots(bets, active)
        assert len(pots) == 1
        assert pots[0].amount == 300
        assert pots[0].eligible_players == {"A", "B", "C"}

    def test_one_all_in_side_pot(self):
        """A is all-in for 300, B and C bet 500."""
        bets = {"A": 300, "B": 500, "C": 500}
        active = {"A", "B", "C"}
        pots = calculate_side_pots(bets, active)
        # Main pot: 300 from each = 900, eligible: A, B, C
        # Side pot: 200 from B, C = 400, eligible: B, C
        assert len(pots) == 2
        assert pots[0].amount == 900
        assert pots[0].eligible_players == {"A", "B", "C"}
        assert pots[1].amount == 400
        assert pots[1].eligible_players == {"B", "C"}

    def test_multiple_all_ins(self):
        """A all-in 200, B all-in 400, C all-in 600."""
        bets = {"A": 200, "B": 400, "C": 600}
        active = {"A", "B", "C"}
        pots = calculate_side_pots(bets, active)
        assert len(pots) == 3
        # First: 200 * 3 = 600, all eligible
        assert pots[0].amount == 600
        assert pots[0].eligible_players == {"A", "B", "C"}
        # Second: 200 * 2 = 400, B and C eligible
        assert pots[1].amount == 400
        assert pots[1].eligible_players == {"B", "C"}
        # Third: 200 * 1 = 200, C eligible
        assert pots[2].amount == 200
        assert pots[2].eligible_players == {"C"}

    def test_folded_player_contributions(self):
        """Folded player's money goes to pots, but they're not eligible."""
        bets = {"A": 500, "B": 300, "C": 500}
        active = {"A", "C"}  # B folded
        pots = calculate_side_pots(bets, active)
        # Level 300: A pays 300, B pays 300, C pays 300 = 900. Eligible: A, B(not active), C
        # Level 500: A pays 200, C pays 200 = 400. Eligible: A, C
        assert len(pots) == 2
        assert pots[0].amount == 900
        assert pots[1].amount == 400
        assert pots[1].eligible_players == {"A", "C"}

    def test_empty(self):
        pots = calculate_side_pots({}, set())
        assert pots == []


class TestHandEvaluator:
    def test_royal_flush_beats_straight_flush(self):
        royal = evaluate_hand(["Ah", "Kh"], ["Qh", "Jh", "Th", "2d", "3c"])
        straight_flush = evaluate_hand(["9s", "8s"], ["7s", "6s", "5s", "2d", "3c"])
        assert royal < straight_flush  # treys: lower score = better hand

    def test_full_house_beats_flush(self):
        fh = evaluate_hand(["Ah", "Ad"], ["Ac", "Kh", "Ks", "2d", "3c"])
        flush = evaluate_hand(["Ah", "Kh"], ["Qh", "Jh", "2h", "5h", "3c"])
        assert fh < flush

    def test_split_pot(self):
        # Both players have the same hand using community cards
        hole_map = {
            "A": ["Ah", "Kd"],
            "B": ["As", "Kc"],
        }
        community = ["Qh", "Jh", "Th", "2d", "3c"]
        winners = determine_winners(hole_map, community, {"A", "B"})
        assert len(winners) == 2
        assert "A" in winners and "B" in winners

    def test_get_hand_name(self):
        score = evaluate_hand(["Ah", "Kh"], ["Qh", "Jh", "Th", "2d", "3c"])
        name = get_hand_name(score)
        assert "Straight" in name or "Royal" in name or "Flush" in name


class TestPokerEngine:
    def test_start_tournament(self):
        config = make_config()
        players = [make_player("p1"), make_player("p2"), make_player("p3")]
        engine = PokerEngine(config, players)
        state = engine.start_tournament()
        assert state.hand_number == 0  # tournament started, no hand yet

        state = engine.start_new_hand()
        assert state.hand_number == 1
        assert state.phase.value == "pre_flop"
        assert all(len(p.hole_cards) == 2 for p in state.players if p.is_active)
        assert state.current_bet == 20  # BB

    def test_blind_posting(self):
        config = make_config()
        players = [make_player(f"p{i}") for i in range(3)]
        engine = PokerEngine(config, players)
        engine.start_tournament()
        state = engine.start_new_hand()

        total_bets = sum(state.round_bets.values())
        assert total_bets == 30  # SB 10 + BB 20

    def test_custom_blind_levels_ignore_ante_when_disabled(self):
        config = make_config(
            ante_enabled=False,
            blind_levels=[
                BlindLevel(level=1, small_blind=10, big_blind=20, ante=5),
            ],
        )
        players = [make_player(f"p{i}") for i in range(3)]
        engine = PokerEngine(config, players)
        engine.start_tournament()
        state = engine.start_new_hand()

        assert state.ante == 0
        assert sum(state.round_bets.values()) == 30
        assert sum(state.total_bets.values()) == 30
        assert all("鍓嶆敞" not in event["text"] for event in state.events)

    def test_fold_action(self):
        config = make_config()
        players = [make_player("p1"), make_player("p2"), make_player("p3")]
        engine = PokerEngine(config, players)
        engine.start_tournament()
        engine.start_new_hand()

        active_idx = engine.active_player_index
        assert active_idx is not None
        player = engine.players[active_idx]
        action = PlayerAction(player_id=player.player_id, action_type=ActionType.FOLD, amount=0)
        state = engine.apply_action(action)

        player_after = next(p for p in state.players if p.player_id == player.player_id)
        assert not player_after.is_active

    def test_call_action(self):
        config = make_config()
        players = [make_player("p1"), make_player("p2"), make_player("p3")]
        engine = PokerEngine(config, players)
        engine.start_tournament()
        engine.start_new_hand()

        active_idx = engine.active_player_index
        player = engine.players[active_idx]
        action = PlayerAction(player_id=player.player_id, action_type=ActionType.CALL, amount=0)
        state = engine.apply_action(action)

        # Player should have posted the bet
        bet = state.round_bets.get(player.player_id, 0)
        assert bet > 0

    def test_everyone_folds_to_last_player(self):
        config = make_config()
        players = [make_player("p1"), make_player("p2"), make_player("p3")]
        engine = PokerEngine(config, players)
        engine.start_tournament()
        engine.start_new_hand()

        # Have two players fold
        for _ in range(2):
            idx = engine.active_player_index
            if idx is None:
                break
            p = engine.players[idx]
            if p.is_active and not p.is_all_in:
                # Get legal actions - might need to call instead of fold
                legal = engine.get_legal_actions(p.player_id)
                action_type = ActionType.FOLD if ActionType.FOLD in legal else ActionType.CALL
                engine.apply_action(PlayerAction(
                    player_id=p.player_id,
                    action_type=action_type,
                    amount=0,
                ))

        # At this point, hand should be over or near over
        # The remaining player should win the pot

    def test_legal_actions_preflop_facing_raise(self):
        config = make_config()
        players = [make_player(f"p{i}") for i in range(4)]
        engine = PokerEngine(config, players)
        engine.start_tournament()
        engine.start_new_hand()

        # Get a player facing the BB
        active_idx = engine.active_player_index
        assert active_idx is not None
        player = engine.players[active_idx]
        legal = engine.get_legal_actions(player.player_id)

        assert ActionType.FOLD in legal
        assert ActionType.CALL in legal
        assert ActionType.RAISE in legal
        assert ActionType.ALL_IN in legal

    def test_tournament_elimination(self):
        config = make_config(initial_chips=100)
        players = [make_player("p1"), make_player("p2")]
        engine = PokerEngine(config, players)

        # Set p1 chips to 0
        engine.players[0].chips = 0
        engine.players[0].is_active = False

        assert engine.is_tournament_over()
        winner = engine.get_winner()
        assert winner is not None
        assert winner.player_id == "p2"

    def test_too_few_players(self):
        config = make_config()
        with pytest.raises(ValueError, match="At least 2"):
            PokerEngine(config, [make_player("p1")])

    def test_too_many_players(self):
        config = make_config(max_players=3)
        with pytest.raises(ValueError, match="Max 3"):
            PokerEngine(config, [make_player(f"p{i}") for i in range(5)])

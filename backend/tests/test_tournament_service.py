from app.core.engine import PokerEngine
from app.models.player import AIPlayerConfig
from app.models.tournament import BlindLevel, TournamentConfig
from app.services.tournament_service import TournamentService


class DummyAIService:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout


class DummyWSManager:
    pass


def make_player(player_id: str) -> AIPlayerConfig:
    return AIPlayerConfig(
        id=player_id,
        display_name=player_id,
        api_endpoint="http://test",
        api_key="test",
        model_name="test",
    )


def make_config() -> TournamentConfig:
    return TournamentConfig(
        initial_chips=1000,
        small_blind_initial=10,
        big_blind_initial=20,
        blind_level_minutes=3,  # now means "hands per level"
        blind_levels=[
            BlindLevel(level=1, small_blind=10, big_blind=20, ante=0),
            BlindLevel(level=2, small_blind=20, big_blind=40, ante=0),
            BlindLevel(level=3, small_blind=30, big_blind=60, ante=0),
            BlindLevel(level=4, small_blind=40, big_blind=80, ante=0),
        ],
        max_players=4,
    )


class TestTournamentServiceBlindTiming:
    def test_blinds_advance_by_hands(self):
        config = make_config()
        players = [make_player("p1"), make_player("p2")]
        engine = PokerEngine(config, players)
        service = TournamentService(
            engine=engine,
            players=players,
            ai_service=DummyAIService(),
            ws_manager=DummyWSManager(),
        )

        # Hand 1: no level change
        advanced = service._advance_blinds_by_hands()
        assert advanced == []
        assert engine.level_index == 0
        assert engine.current_blinds["level"] == 1

        # Hand 2: no change (still < 3 hands)
        advanced = service._advance_blinds_by_hands()
        assert advanced == []

        # Hand 3: advance to level 2
        advanced = service._advance_blinds_by_hands()
        assert [level["level"] for level in advanced] == [2]
        assert engine.level_index == 1
        assert engine.current_blinds["level"] == 2

        # Hands 4-5: no change
        for _ in range(2):
            advanced = service._advance_blinds_by_hands()
            assert advanced == []

        # Hand 6: advance to level 3
        advanced = service._advance_blinds_by_hands()
        assert [level["level"] for level in advanced] == [3]
        assert engine.level_index == 2
        assert engine.current_blinds["level"] == 3

        # Hands 7-8: no change
        for _ in range(2):
            advanced = service._advance_blinds_by_hands()
            assert advanced == []

        # Hand 9: advance to level 4
        advanced = service._advance_blinds_by_hands()
        assert [level["level"] for level in advanced] == [4]
        assert engine.level_index == 3
        assert engine.current_blinds["level"] == 4

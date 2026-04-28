from app.models.game import GameState, PlayerState
from app.models.player import AIPlayerConfig
from app.models.tournament import Phase
from app.prompts.builder import PromptBuilder


def make_player_config(player_id: str = "hero") -> AIPlayerConfig:
    return AIPlayerConfig(
        id=player_id,
        display_name=player_id,
        api_endpoint="http://test",
        api_key="test",
        model_name="test",
    )


def make_state(*, ante: int = 0, players: list[PlayerState] | None = None) -> GameState:
    return GameState(
        tournament_id="t1",
        hand_number=3,
        level=2,
        small_blind=50,
        big_blind=100,
        ante=ante,
        players=players or [],
        dealer_index=0,
        active_player_index=0,
        phase=Phase.PRE_FLOP,
        round_bets={},
        total_bets={},
        events=[],
    )


class TestPromptBuilder:
    def test_ante_hidden_when_disabled(self):
        builder = PromptBuilder()
        player_config = make_player_config()
        state = make_state(
            ante=0,
            players=[
                PlayerState("hero", "Hero", 1000, seat_index=0),
                PlayerState("villain", "Villain", 1000, seat_index=1),
            ],
        )

        system_prompt = builder.build_system_prompt(player_config, state)
        user_message = builder.build_user_message(player_config, state, [])

        assert "Ante=0" not in system_prompt
        assert "Ante=0" not in user_message
        assert "Ante=" not in user_message

    def test_busted_player_not_listed_as_alive(self):
        builder = PromptBuilder()
        player_config = make_player_config()
        players = [
            PlayerState("hero", "Hero", 1200, seat_index=0),
            PlayerState("allin", "AllIn", 0, is_active=True, is_all_in=True, seat_index=1),
            PlayerState("busted", "Busted", 0, is_active=True, is_all_in=False, seat_index=2),
        ]
        state = make_state(ante=25, players=players)

        user_message = builder.build_user_message(player_config, state, [])

        assert "Hero" in user_message
        assert "AllIn" in user_message
        assert "Busted" not in user_message


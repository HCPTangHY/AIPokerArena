from dataclasses import dataclass, field
from app.models.tournament import Phase, ActionType, TournamentConfig, BlindLevel


@dataclass
class PlayerAction:
    player_id: str
    action_type: ActionType
    amount: int = 0
    thinking_content: str = ""
    raw_response: str = ""


@dataclass
class Pot:
    amount: int
    eligible_players: set[str]


@dataclass
class PlayerState:
    player_id: str
    display_name: str
    chips: int
    hole_cards: list[str] = field(default_factory=list)
    is_active: bool = True  # still in the hand (hasn't folded)
    is_all_in: bool = False
    acted_this_round: bool = False
    last_action: PlayerAction | None = None
    seat_index: int = 0
    avatar_url: str = ""

    def reset_for_new_hand(self):
        self.hole_cards = []
        self.is_active = self.chips > 0
        self.is_all_in = False
        self.acted_this_round = False
        self.last_action = None


@dataclass
class GameState:
    tournament_id: str
    hand_number: int
    level: int
    small_blind: int
    big_blind: int
    ante: int
    players: list[PlayerState]
    dealer_index: int
    active_player_index: int | None
    community_cards: list[str] = field(default_factory=list)
    phase: Phase = Phase.PRE_FLOP
    pots: list[Pot] = field(default_factory=list)
    current_bet: int = 0
    min_raise: int = 0
    last_aggressor_index: int | None = None
    round_bets: dict[str, int] = field(default_factory=dict)  # player_id -> bet this round
    total_bets: dict[str, int] = field(default_factory=dict)  # player_id -> total bet this hand
    events: list[dict] = field(default_factory=list)
    hand_history: list[dict] = field(default_factory=list)
    action_timeout_seconds: float = 0
    action_deadline_ts: float | None = None
    # Track which players need to act in the current betting round
    players_to_act: set[str] = field(default_factory=set)
    equities: dict[str, float] = field(default_factory=dict)

    def to_public_dict(self) -> dict:
        """Serialise for spectator WebSocket broadcast (no hole cards)."""
        return {
            "tournament_id": self.tournament_id,
            "hand_number": self.hand_number,
            "level": self.level,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "ante": self.ante,
            "phase": self.phase.value,
            "community_cards": self.community_cards,
            "pots": [{"amount": p.amount, "eligible_count": len(p.eligible_players)} for p in self.pots],
            "current_bet": self.current_bet,
            "min_raise": self.min_raise,
            "dealer_index": self.dealer_index,
            "active_player_index": self.active_player_index,
            "action_timeout_seconds": self.action_timeout_seconds,
            "action_deadline_ts": self.action_deadline_ts,
            "players": [
                {
                    "id": p.player_id,
                    "display_name": p.display_name,
                    "chips": p.chips,
                    "is_active": p.is_active,
                    "is_all_in": p.is_all_in,
                    "seat_index": p.seat_index,
                    "bet_this_round": self.round_bets.get(p.player_id, 0),
                    "total_bet": self.total_bets.get(p.player_id, 0),
                    "last_action": {
                        "type": p.last_action.action_type.value,
                        "amount": p.last_action.amount,
                    } if p.last_action else None,
                    "hole_cards": p.hole_cards if p.is_active else [],
                    "avatar_url": p.avatar_url,
                    "equity": self.equities.get(p.player_id, 0) if p.is_active and p.hole_cards else None,
                }
                for p in self.players
            ],
            "events": self.events[-20:],  # last 20 events
            "hand_history": [
                {
                    "hand_number": hand.get("hand_number"),
                    "actions": hand.get("actions", []),
                    "settlement": [
                        {
                            "name": item.get("name", ""),
                            "player_id": item.get("player_id", ""),
                            "chip_change": item.get("chip_change", 0),
                            "cards": item.get("cards", []) if item.get("revealed") else [],
                            "revealed": item.get("revealed", False),
                        }
                        for item in hand.get("settlement", [])
                    ],
                    "flop_cards": hand.get("flop_cards", []),
                    "turn_card": hand.get("turn_card"),
                    "river_card": hand.get("river_card"),
                }
                for hand in self.hand_history[-8:]
            ],
        }

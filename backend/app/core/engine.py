import uuid
from app.core.deck import Deck
from app.core.evaluator import determine_winners, get_hand_name, evaluate_hand, calculate_equity
from app.models.tournament import Phase, ActionType, TournamentConfig
from app.models.player import AIPlayerConfig
from app.models.game import GameState, PlayerState, PlayerAction, Pot
from app.core.side_pots import calculate_side_pots


class PokerEngine:
    """Manages a single tournament. All state mutations happen here."""

    def __init__(self, config: TournamentConfig, players: list[AIPlayerConfig]):
        if len(players) < 2:
            raise ValueError("At least 2 players required")
        if len(players) > config.max_players:
            raise ValueError(f"Max {config.max_players} players allowed")

        self.config = config
        self.tournament_id = uuid.uuid4().hex[:12]
        self.hand_number = 0
        self.level_index = 0  # index into blind_levels
        self.blind_levels = self._build_blind_levels()
        self.deck = Deck()

        self.players = [
            PlayerState(
                player_id=p.id,
                display_name=p.display_name,
                chips=config.initial_chips,
                seat_index=i,
                avatar_url=p.avatar_url,
            )
            for i, p in enumerate(players)
        ]
        self.dealer_index = -1
        self.eliminated_order: list[str] = []
        self.is_running = False
        self._pending_eliminations: list[str] = []
        self.hand_history: list[dict] = []
        self._current_hand_actions: list[dict] = []
        self._current_hand_my_cards: dict[str, list[str]] = {}
        self._chips_before_hand: dict[str, int] = {}

        # Initialise hand state attributes (set properly in start_new_hand)
        self.community_cards: list[str] = []
        self.phase = Phase.PRE_FLOP
        self.pots: list[Pot] = []
        self.current_bet = 0
        self.min_raise = 0
        self.last_aggressor_index: int | None = None
        self.round_bets: dict[str, int] = {}
        self.total_bets: dict[str, int] = {}
        self.players_to_act: set[str] = set()
        self.active_player_index: int | None = None
        self._prev_events: list[dict] = []

    def _build_blind_levels(self) -> list[dict]:
        """Build blind schedule, auto-generating if needed."""
        if self.config.blind_levels:
            return [
                {
                    "level": bl.level,
                    "small_blind": bl.small_blind,
                    "big_blind": bl.big_blind,
                    "ante": bl.ante if self.config.ante_enabled else 0,
                }
                for bl in self.config.blind_levels
            ]
        sb = self.config.small_blind_initial
        bb = self.config.big_blind_initial
        levels = []
        for i in range(1, 21):
            ante = 0
            if self.config.ante_enabled and i >= self.config.ante_start_level:
                ante = max(1, bb // 4)
            levels.append({"level": i, "small_blind": sb, "big_blind": bb, "ante": ante})
            sb *= 2
            bb *= 2
        return levels

    @property
    def current_blinds(self) -> dict:
        if self.level_index < len(self.blind_levels):
            return self.blind_levels[self.level_index]
        return self.blind_levels[-1]

    @property
    def active_players(self) -> list[PlayerState]:
        return [p for p in self.players if p.chips > 0 or (p.is_active and p.is_all_in)]

    @property
    def players_with_chips(self) -> list[PlayerState]:
        return [p for p in self.players if p.chips > 0]

    def start_tournament(self) -> GameState:
        self.is_running = True
        self.dealer_index = -1
        return self._build_state([{"text": "锦标赛开始", "ts": 0}])

    def is_tournament_over(self) -> bool:
        return sum(1 for p in self.players if p.chips > 0) <= 1

    def get_winner(self) -> PlayerState | None:
        players_with_chips = self.players_with_chips
        if len(players_with_chips) == 1:
            return players_with_chips[0]
        if len(players_with_chips) == 0:
            # Everyone busted — last eliminated wins
            if self.eliminated_order:
                last_id = self.eliminated_order[-1]
                for p in self.players:
                    if p.player_id == last_id:
                        return p
        return None

    def start_new_hand(self) -> GameState:
        self.hand_number += 1

        # Process pending eliminations
        for pid in self._pending_eliminations:
            self.eliminated_order.append(pid)
        self._pending_eliminations = []

        # Reset tracking for new hand
        self._current_hand_actions = []
        self._current_hand_my_cards = {}
        self._chips_before_hand = {}  # track chips before hand for settlement
        self._prev_events = []  # clear previous hand events

        # Reset all players for new hand
        for p in self.players:
            self._chips_before_hand[p.player_id] = p.chips
            p.reset_for_new_hand()

        # Move dealer button
        active = [p for p in self.players if p.chips > 0]
        if not active:
            raise RuntimeError("No players with chips")
        self.dealer_index = (self.dealer_index + 1) % len(self.players)
        while self.players[self.dealer_index].chips <= 0:
            self.dealer_index = (self.dealer_index + 1) % len(self.players)

        blinds = self.current_blinds
        sb = blinds["small_blind"]
        bb = blinds["big_blind"]
        ante = blinds.get("ante", 0)

        self.deck.reset()
        self.deck.shuffle()

        # Initialise game state
        self.community_cards: list[str] = []
        self.phase = Phase.PRE_FLOP
        self.pots: list[Pot] = []
        self.current_bet = bb
        self.min_raise = bb
        self.last_aggressor_index = None
        self.round_bets = {}
        self.total_bets = {}
        self.players_to_act = set()

        events: list[dict] = []

        # Post antes
        if ante > 0:
            for p in self.players:
                if p.chips > 0:
                    ante_paid = min(ante, p.chips)
                    p.chips -= ante_paid
                    self.total_bets[p.player_id] = self.total_bets.get(p.player_id, 0) + ante_paid
            events.append({"text": f"全员支付前注 {ante}", "ts": 0})

        # Post blinds
        active_with_chips = [p for p in self.players if p.chips > 0]
        if len(active_with_chips) == 2:
            # Heads-up: dealer = SB, other = BB
            sb_index = self.dealer_index
            bb_index = self._next_active_seat(sb_index)
        else:
            sb_index = self._next_active_seat(self.dealer_index)
            bb_index = self._next_active_seat(sb_index)

        # Small blind
        sb_player = self.players[sb_index]
        sb_paid = min(sb, sb_player.chips)
        sb_player.chips -= sb_paid
        self.round_bets[sb_player.player_id] = sb_paid
        self.total_bets[sb_player.player_id] = self.total_bets.get(sb_player.player_id, 0) + sb_paid
        if sb_player.chips == 0:
            sb_player.is_all_in = True
        sb_player.last_action = PlayerAction(
            player_id=sb_player.player_id,
            action_type=ActionType.SMALL_BLIND,
            amount=sb_paid,
        )
        events.append({"text": f"{sb_player.display_name} 支付小盲 {sb_paid}", "ts": 0})
        self._current_hand_actions.append({
            "player_id": sb_player.player_id, "player_name": sb_player.display_name,
            "phase": "pre_flop", "position": self._get_position_name(sb_player.seat_index),
            "action": "small_blind", "amount": sb_paid,
        })

        # Big blind
        bb_player = self.players[bb_index]
        bb_paid = min(bb, bb_player.chips)
        bb_player.chips -= bb_paid
        self.round_bets[bb_player.player_id] = bb_paid
        self.total_bets[bb_player.player_id] = self.total_bets.get(bb_player.player_id, 0) + bb_paid
        if bb_player.chips == 0:
            bb_player.is_all_in = True
        bb_player.last_action = PlayerAction(
            player_id=bb_player.player_id,
            action_type=ActionType.BIG_BLIND,
            amount=bb_paid,
        )
        events.append({"text": f"{bb_player.display_name} 支付大盲 {bb_paid}", "ts": 0})
        self._current_hand_actions.append({
            "player_id": bb_player.player_id, "player_name": bb_player.display_name,
            "phase": "pre_flop", "position": self._get_position_name(bb_player.seat_index),
            "action": "big_blind", "amount": bb_paid,
        })

        # If BB is all-in from blind, current bet is still the BB amount (or their all-in if less)
        # Actually, the BB amount defines the minimum bet; if BB can't cover, max bet is their all-in
        if bb_paid < bb:
            self.current_bet = bb_paid
            self.min_raise = bb  # min raise is still the BB amount
        else:
            self.current_bet = bb
            self.min_raise = bb

        # Deal hole cards
        for p in self.players:
            if p.chips > 0 or p.is_all_in:
                p.hole_cards = self.deck.draw(2)
                p.is_active = True
                self._current_hand_my_cards[p.player_id] = list(p.hole_cards)

        # Set first player to act (UTG = after BB)
        first_to_act = self._next_active_seat(bb_index)
        self.active_player_index = first_to_act

        # All active players need to act in pre-flop
        # Except: in heads-up, dealer acts first pre-flop (SB is dealer, acts first)
        active_count = sum(1 for p in self.players if p.is_active and not p.is_all_in)
        if active_count == 2:
            # Heads-up: dealer/SB acts first pre-flop
            self.active_player_index = sb_index

        # Mark all non-all-in active players as needing to act
        for p in self.players:
            if p.is_active and not p.is_all_in and p.chips > 0:
                self.players_to_act.add(p.player_id)
                p.acted_this_round = False

        # If BB is all-in and no one else has chips, skip to showdown
        if len(self.players_to_act) == 0:
            return self.run_showdown()

        return self._build_state(events)

    def deal_flop(self) -> GameState:
        self.deck.draw(1)  # burn
        self.community_cards = self.deck.draw(3)
        self.phase = Phase.FLOP
        self._reset_round_for_new_street()
        return self._build_state([{"text": "发翻牌", "ts": 0}])

    def deal_turn(self) -> GameState:
        self.deck.draw(1)  # burn
        self.community_cards.append(self.deck.draw(1)[0])
        self.phase = Phase.TURN
        self._reset_round_for_new_street()
        return self._build_state([{"text": "发转牌", "ts": 0}])

    def deal_river(self) -> GameState:
        self.deck.draw(1)  # burn
        self.community_cards.append(self.deck.draw(1)[0])
        self.phase = Phase.RIVER
        self._reset_round_for_new_street()
        return self._build_state([{"text": "发河牌", "ts": 0}])

    def _reset_round_for_new_street(self):
        """Reset betting round state for a new street."""
        self.current_bet = 0
        self.min_raise = self.current_blinds["big_blind"]
        self.last_aggressor_index = None
        self.round_bets = {}
        self.players_to_act = set()

        # First active player after dealer
        first = self._next_active_seat(self.dealer_index)
        self.active_player_index = first

        for p in self.players:
            p.acted_this_round = False
            if p.is_active and not p.is_all_in and p.chips > 0:
                self.players_to_act.add(p.player_id)

        if self.should_auto_runout_board():
            self.players_to_act.clear()
            self.active_player_index = None

    def get_legal_actions(self, player_id: str) -> list[ActionType]:
        """Return legal actions for a player."""
        player = next((p for p in self.players if p.player_id == player_id), None)
        if not player or not player.is_active or player.is_all_in:
            return []

        to_call = self.current_bet - self.round_bets.get(player_id, 0)
        chips = player.chips

        if chips == 0:
            return []

        min_raise = max(self.min_raise, self.current_blinds["big_blind"])
        already_bet = self.round_bets.get(player_id, 0)
        max_possible = already_bet + chips

        if to_call <= 0:
            actions = [ActionType.CHECK]
            if chips > 0:
                # Only allow raise if player can afford minimum bet
                if max_possible >= self.current_bet + min_raise:
                    actions.append(ActionType.RAISE)
                actions.append(ActionType.ALL_IN)
            return actions

        actions = [ActionType.FOLD]
        if to_call >= chips:
            actions.append(ActionType.ALL_IN)
        else:
            actions.append(ActionType.CALL)
            # Only allow raise if minimum raise is possible
            min_raise_total = self.current_bet + min_raise
            if max_possible >= min_raise_total:
                actions.append(ActionType.RAISE)
            actions.append(ActionType.ALL_IN)
        return actions

    def apply_action(self, action: PlayerAction) -> GameState:
        """Apply a player action and return updated state."""
        player = next((p for p in self.players if p.player_id == action.player_id), None)
        if not player:
            raise ValueError(f"Player {action.player_id} not found")

        # Validate and correct
        action_type, amount = self._validate_action(action)
        action.action_type = action_type
        action.amount = amount

        events: list[dict] = []
        player.last_action = action
        self.players_to_act.discard(player.player_id)

        if action_type == ActionType.FOLD:
            player.is_active = False
            player.hole_cards = []
            events.append({"text": f"{player.display_name} 弃牌", "ts": 0})

        elif action_type == ActionType.CHECK:
            player.acted_this_round = True
            events.append({"text": f"{player.display_name} 过牌", "ts": 0})

        elif action_type == ActionType.CALL:
            to_call = self.current_bet - self.round_bets.get(player.player_id, 0)
            call_amount = min(to_call, player.chips)
            player.chips -= call_amount
            self.round_bets[player.player_id] = self.round_bets.get(player.player_id, 0) + call_amount
            self.total_bets[player.player_id] = self.total_bets.get(player.player_id, 0) + call_amount
            player.acted_this_round = True
            if player.chips == 0:
                player.is_all_in = True
            events.append({"text": f"{player.display_name} 跟注 {self.round_bets.get(player.player_id, 0)}", "ts": 0})

        elif action_type == ActionType.RAISE:
            to_call = self.current_bet - self.round_bets.get(player.player_id, 0)
            total = to_call + amount
            if total >= player.chips:
                # All-in
                total = player.chips
                action_type = ActionType.ALL_IN
                action.action_type = ActionType.ALL_IN
            player.chips -= total
            self.round_bets[player.player_id] = self.round_bets.get(player.player_id, 0) + total
            self.total_bets[player.player_id] = self.total_bets.get(player.player_id, 0) + total

            new_total_bet = self.round_bets[player.player_id]
            if new_total_bet > self.current_bet:
                self.current_bet = new_total_bet
                self.min_raise = amount
                self.last_aggressor_index = player.seat_index
                # Reset acted flags for other players (they need to respond to raise)
                for p in self.players:
                    if p.player_id != player.player_id and p.is_active and not p.is_all_in:
                        p.acted_this_round = False
                        self.players_to_act.add(p.player_id)

            player.acted_this_round = True
            if player.chips == 0:
                player.is_all_in = True
            events.append({"text": f"{player.display_name} 加注至 {new_total_bet}", "ts": 0})

        elif action_type == ActionType.ALL_IN:
            to_call = self.current_bet - self.round_bets.get(player.player_id, 0)
            total = player.chips
            player.chips = 0
            self.round_bets[player.player_id] = self.round_bets.get(player.player_id, 0) + total
            self.total_bets[player.player_id] = self.total_bets.get(player.player_id, 0) + total
            player.is_all_in = True
            player.acted_this_round = True

            new_total = self.round_bets[player.player_id]
            if new_total > self.current_bet:
                self.current_bet = new_total
                self.min_raise = new_total - self.current_bet + self.round_bets.get(player.player_id, 0)  # re-raise amount
                if self.min_raise < self.current_blinds["big_blind"]:
                    self.min_raise = self.current_blinds["big_blind"]
                self.last_aggressor_index = player.seat_index
                for p in self.players:
                    if p.player_id != player.player_id and p.is_active and not p.is_all_in and p.chips > 0:
                        p.acted_this_round = False
                        self.players_to_act.add(p.player_id)

            events.append({"text": f"{player.display_name} 全下 {self.round_bets.get(player.player_id, 0)}", "ts": 0})

        # Record action for hand history (after state is updated)
        new_bet = self.round_bets.get(player.player_id, 0)
        self._current_hand_actions.append({
            "player_id": player.player_id,
            "player_name": player.display_name,
            "phase": self.phase.value,
            "position": self._get_position_name(player.seat_index),
            "action": action_type.value,
            "amount": new_bet if action_type in (ActionType.RAISE, ActionType.CALL, ActionType.ALL_IN)
                      else action.amount if action_type == ActionType.ALL_IN else 0,
        })

        # Move to next player or check round completion
        if self.is_betting_round_complete():
            return self._finalise_betting_round(events)
        else:
            self.active_player_index = self._next_player_to_act()
            return self._build_state(events)

    def _validate_action(self, action: PlayerAction) -> tuple[ActionType, int]:
        """Validate and correct an action. Returns corrected (type, amount)."""
        player = next((p for p in self.players if p.player_id == action.player_id), None)
        if not player:
            return ActionType.FOLD, 0

        legal = self.get_legal_actions(player.player_id)

        if action.action_type not in legal:
            # Try to fix
            if action.action_type == ActionType.CHECK and ActionType.FOLD in legal:
                return ActionType.FOLD, 0
            if action.action_type == ActionType.CALL and ActionType.ALL_IN in legal:
                return ActionType.ALL_IN, player.chips
            if action.action_type == ActionType.RAISE:
                if ActionType.CALL in legal:
                    return ActionType.CALL, 0
                if ActionType.ALL_IN in legal:
                    return ActionType.ALL_IN, player.chips
            # Fallback: fold if possible, else check, else all-in
            if ActionType.FOLD in legal:
                return ActionType.FOLD, 0
            if ActionType.CHECK in legal:
                return ActionType.CHECK, 0
            return ActionType.ALL_IN, player.chips

        to_call = self.current_bet - self.round_bets.get(player.player_id, 0)
        amount = action.amount

        if action.action_type == ActionType.CALL:
            return ActionType.CALL, min(to_call, player.chips)

        if action.action_type == ActionType.RAISE:
            # amount from AI = total target (加注至), raise_size = how much above current bet
            raise_size = amount - self.current_bet
            if raise_size < 0:
                raise_size = 0
            min_raise = max(self.min_raise, self.current_blinds["big_blind"])
            if raise_size < min_raise:
                raise_size = min_raise
            total_needed = self.current_bet - self.round_bets.get(player.player_id, 0) + raise_size
            if total_needed >= player.chips:
                return ActionType.ALL_IN, player.chips
            return ActionType.RAISE, raise_size

        if action.action_type == ActionType.ALL_IN:
            return ActionType.ALL_IN, player.chips

        return action.action_type, amount

    def _next_active_seat(self, start_index: int) -> int:
        """Find the next seat with an active player still in the hand."""
        n = len(self.players)
        for i in range(1, n + 1):
            idx = (start_index + i) % n
            p = self.players[idx]
            if p.is_active and not p.is_all_in and p.chips > 0:
                return idx
        return start_index

    def _next_player_to_act(self) -> int:
        """Find the next player who needs to act."""
        if not self.players_to_act:
            return self.active_player_index or 0

        n = len(self.players)
        start = (self.active_player_index or 0) + 1
        for i in range(n):
            idx = (start + i) % n
            p = self.players[idx]
            if p.player_id in self.players_to_act and p.is_active and not p.is_all_in and p.chips > 0:
                return idx
        return self.active_player_index or 0

    def is_betting_round_complete(self) -> bool:
        """Check if the current betting round is complete."""
        # Hand ends immediately when only 1 player remains
        active_players = [p for p in self.players if p.is_active]
        if len(active_players) <= 1:
            self.players_to_act.clear()
            return True

        # Eliminate players who can't act from players_to_act
        for p in self.players:
            if not p.is_active or p.is_all_in or p.chips <= 0:
                self.players_to_act.discard(p.player_id)

        if not self.players_to_act:
            return True

        # All remaining players must have acted and bets equalized
        for pid in list(self.players_to_act):
            p = next((pl for pl in self.players if pl.player_id == pid), None)
            if not p or not p.is_active or p.is_all_in:
                self.players_to_act.discard(pid)
                continue
            player_bet = self.round_bets.get(pid, 0)
            if p.acted_this_round and player_bet == self.current_bet:
                self.players_to_act.discard(pid)

        return len(self.players_to_act) == 0

    def should_auto_runout_board(self) -> bool:
        active_players = [p for p in self.players if p.is_active]
        if len(active_players) <= 1:
            return False

        active_can_act = sum(1 for p in active_players if not p.is_all_in and p.chips > 0)
        all_in_count = sum(1 for p in active_players if p.is_all_in)
        return all_in_count >= 1 and active_can_act <= 1

    def _finalise_betting_round(self, events: list[dict]) -> GameState:
        """Move chips to pot and determine whether betting can continue."""
        self.pots = calculate_side_pots(
            self.total_bets,
            {p.player_id for p in self.players if p.is_active},
        )

        total_active = sum(1 for p in self.players if p.is_active)
        active_can_act = sum(
            1 for p in self.players if p.is_active and not p.is_all_in and p.chips > 0
        )
        all_in_count = sum(1 for p in self.players if p.is_active and p.is_all_in)

        if total_active == 1:
            return self._award_to_last_player(events)

        if all_in_count >= 1 and active_can_act <= 1:
            self.players_to_act.clear()
            self.active_player_index = None
            return self._build_state(events)

        if active_can_act == 1 and all_in_count == 0:
            return self._award_to_last_player(events)

        return self._build_state(events)

    def _award_to_last_player(self, events: list[dict]) -> GameState:
        """Award all pots to the last remaining active player."""
        self.phase = Phase.SHOWDOWN
        # Accept any active player, including all-in ones (they are the only one left)
        winner = next((p for p in self.players if p.is_active), None)
        if winner:
            total_pot = sum(pot.amount for pot in self.pots) if self.pots else sum(
                self.total_bets.values())
            if total_pot == 0:
                total_pot = sum(self.total_bets.values())
            # Recalculate pots
            self.pots = calculate_side_pots(
                self.total_bets,
                {p.player_id for p in self.players if p.is_active or self.total_bets.get(p.player_id, 0) > 0},
            )
            total_pot = sum(pot.amount for pot in self.pots)
            winner.chips += total_pot
            events.append({"text": f"{winner.display_name} 赢得 {total_pot}（无人跟注）", "ts": 0})
            self.pots = []
        return self._end_hand(events)

    def run_showdown(self) -> GameState:
        """Run showdown: evaluate hands, award pots."""
        events: list[dict] = []

        # If only one active player (others folded), they win
        active_players = [p for p in self.players if p.is_active]
        if len(active_players) == 1:
            total_pot = sum(self.total_bets.values())
            active_players[0].chips += total_pot
            events.append({"text": f"{active_players[0].display_name} 赢得底池 {total_pot}", "ts": 0})
            self.pots = []
            self.phase = Phase.SHOWDOWN
            return self._end_hand(events)

        self.phase = Phase.SHOWDOWN

        # Calculate pots
        self.pots = calculate_side_pots(
            self.total_bets,
            {p.player_id for p in self.players if p.is_active},
        )

        # Build hole cards map for showdown
        hole_cards_map = {
            p.player_id: p.hole_cards
            for p in self.players if p.is_active
        }

        for pot in self.pots:
            if pot.amount == 0:
                continue
            eligible = pot.eligible_players & {p.player_id for p in self.players if p.is_active}
            if not eligible:
                continue

            winners = determine_winners(hole_cards_map, self.community_cards, eligible)
            if not winners:
                continue

            split = pot.amount // len(winners)
            remainder = pot.amount % len(winners)

            for pid in winners:
                player = next((p for p in self.players if p.player_id == pid), None)
                if player:
                    win_amount = split + (1 if remainder > 0 else 0)
                    remainder -= 1
                    player.chips += win_amount
                    hand_name = get_hand_name(evaluate_hand(player.hole_cards, self.community_cards))
                    events.append({
                        "text": f"{player.display_name} 赢得 {win_amount}（{hand_name}）",
                        "ts": 0,
                    })

        self.pots = []
        return self._end_hand(events)

    def _end_hand(self, events: list[dict]) -> GameState:
        """Finish the hand, check eliminations, record history."""
        # Build hand summary for history
        summary = self._build_hand_summary()

        # Check for eliminated players
        for p in self.players:
            if p.chips == 0:
                p.is_active = False
                if p.player_id not in self._pending_eliminations and p.player_id not in self.eliminated_order:
                    self._pending_eliminations.append(p.player_id)
                    events.append({"text": f"{p.display_name} 被淘汰", "ts": 0})

        self.hand_history.append(summary)
        self.total_bets = {}
        self.round_bets = {}
        return self._build_state(events)

    def _build_hand_summary(self) -> dict:
        """Build a summary of the completed hand for history."""
        flop = self.community_cards[:3] if len(self.community_cards) >= 3 else []
        turn = self.community_cards[3] if len(self.community_cards) >= 4 else None
        river = self.community_cards[4] if len(self.community_cards) >= 5 else None

        settlement = []
        for p in self.players:
            before = self._chips_before_hand.get(p.player_id, 0)
            chip_change = p.chips - before
            # Only include players who participated (put money in or won)
            was_in_hand = p.player_id in self._current_hand_my_cards
            if chip_change != 0 or was_in_hand or p.is_active:
                # Reveal cards only at showdown (≥2 players reached end)
                active_count = sum(1 for pp in self.players if pp.is_active and pp.hole_cards)
                revealed = self.phase == Phase.SHOWDOWN and p.is_active and active_count >= 2
                settlement.append({
                    "name": p.display_name,
                    "player_id": p.player_id,
                    "chip_change": chip_change,
                    "cards": self._current_hand_my_cards.get(p.player_id, []),
                    "revealed": revealed,
                })

        return {
            "hand_number": self.hand_number,
            "actions": list(self._current_hand_actions),
            "settlement": settlement,
            "flop_cards": flop,
            "turn_card": turn,
            "river_card": river,
            "hole_cards_map": dict(self._current_hand_my_cards),  # per-player hole cards
        }

    def _get_position_name(self, seat_index: int) -> str:
        """Get position name for a seat in the current hand."""
        active = [p for p in self.players if p.chips > 0 or p.is_all_in]
        active_seats = sorted(p.seat_index for p in active)
        total = len(active_seats)
        if total <= 2:
            return "小盲/庄家" if seat_index == self.dealer_index else "大盲"

        positions = ["庄家", "小盲", "大盲", "枪口", "枪口+1", "枪口+2", "中位", "中位+1", "劫位", "关位"]
        try:
            dealer_pos = active_seats.index(self.dealer_index)
            seat_pos = active_seats.index(seat_index)
        except ValueError:
            return f"座{seat_index}"
        offset = (seat_pos - dealer_pos) % total
        return positions[offset] if offset < len(positions) else f"座{offset}"

    def get_hand_history(self) -> list[dict]:
        return list(self.hand_history)

    def advance_blinds_if_needed(self) -> bool:
        """Check if blinds should advance. Called between hands."""
        if self.level_index + 1 < len(self.blind_levels):
            self.level_index += 1
            return True
        return False

    def _build_state(self, events: list[dict] | None = None) -> GameState:
        if events is None:
            events = []

        all_events = []
        if hasattr(self, '_prev_events'):
            all_events = list(self._prev_events)
        all_events.extend(events)
        self._prev_events = all_events[-50:]  # keep last 50 events

        # Compute real-time equity for active players with hole cards
        equities: dict[str, float] = {}
        active_with_cards = [p for p in self.players if p.is_active and p.hole_cards]
        if len(active_with_cards) >= 2 and len(self.community_cards) >= 0:
            hole_map = {p.player_id: p.hole_cards for p in active_with_cards}
            active_ids = {p.player_id for p in active_with_cards}
            try:
                equities = calculate_equity(hole_map, self.community_cards, active_ids, iterations=2000)
            except Exception:
                pass

        return GameState(
            tournament_id=self.tournament_id,
            hand_number=self.hand_number,
            level=self.current_blinds["level"],
            small_blind=self.current_blinds["small_blind"],
            big_blind=self.current_blinds["big_blind"],
            ante=self.current_blinds.get("ante", 0),
            players=self.players,
            dealer_index=self.dealer_index,
            active_player_index=self.active_player_index,
            community_cards=list(self.community_cards),
            phase=self.phase,
            pots=self.pots,
            current_bet=self.current_bet,
            min_raise=self.min_raise,
            last_aggressor_index=self.last_aggressor_index,
            round_bets=dict(self.round_bets),
            total_bets=dict(self.total_bets),
            events=list(all_events[-50:]),
            hand_history=list(self.hand_history[-8:]),
            players_to_act=set(self.players_to_act),
            equities=equities,
        )

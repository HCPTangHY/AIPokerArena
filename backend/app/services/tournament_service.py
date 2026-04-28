import asyncio
import time
from app.core.engine import PokerEngine
from app.models.tournament import Phase, ActionType
from app.models.player import AIPlayerConfig
from app.models.game import GameState, PlayerAction
from app.services.ai_service import AIService
from app.prompts.builder import PromptBuilder
from app.ws.manager import ConnectionManager


class TournamentService:
    """Orchestrates the tournament lifecycle — engine + AI + WebSocket."""

    def __init__(
        self,
        engine: PokerEngine,
        players: list[AIPlayerConfig],
        ai_service: AIService,
        ws_manager: ConnectionManager,
        delay_between_actions: float = 1.0,
    ):
        self.engine = engine
        self.players_config = players
        self.ai = ai_service
        self.ws = ws_manager
        self.delay = delay_between_actions
        self._task: asyncio.Task | None = None
        self._running = False
        self._hands_in_level: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def _advance_blinds_by_hands(self) -> list[dict]:
        """Advance blind levels based on number of hands played."""
        hands_per_level = int(getattr(self.engine.config, "blind_level_minutes", 0) or 0)
        if hands_per_level <= 0:
            return []

        self._hands_in_level += 1
        if self._hands_in_level < hands_per_level:
            return []

        self._hands_in_level = 0
        advanced_levels: list[dict] = []
        if self.engine.advance_blinds_if_needed():
            advanced_levels.append(dict(self.engine.current_blinds))
        return advanced_levels

    def _build_safe_fallback_action(
        self,
        player_id: str,
        legal_actions: list[ActionType],
        reason: str = "",
    ) -> PlayerAction:
        """Pick a conservative action so the hand can continue after AI failures."""
        if ActionType.CHECK in legal_actions:
            action_type = ActionType.CHECK
        elif ActionType.CALL in legal_actions:
            action_type = ActionType.CALL
        elif ActionType.FOLD in legal_actions:
            action_type = ActionType.FOLD
        elif ActionType.ALL_IN in legal_actions:
            action_type = ActionType.ALL_IN
        elif ActionType.RAISE in legal_actions:
            action_type = ActionType.RAISE
        else:
            action_type = ActionType.FOLD

        return PlayerAction(
            player_id=player_id,
            action_type=action_type,
            amount=0,
            thinking_content=reason,
            raw_response=reason,
        )

    async def _finalize_thinking_safe(
        self,
        room: str,
        player_id: str,
        display_name: str,
        fallback_text: str = "",
    ) -> None:
        """Do not let thinking-finalization failures freeze the betting loop."""
        try:
            await self.ws.finalize_thinking(
                room,
                player_id,
                display_name,
                fallback_text=fallback_text,
            )
        except Exception as e:
            print(f"[TournamentService] finalize_thinking failed for {player_id}: {e}")

    async def _runout_to_showdown(self, state: GameState) -> GameState:
        """Reveal remaining board cards with pauses when no more betting is possible."""
        room = self.engine.tournament_id

        while len(self.engine.community_cards) < 5 and self._running:
            await asyncio.sleep(3)

            if len(self.engine.community_cards) == 0:
                state = self.engine.deal_flop()
                phase = "flop"
            elif len(self.engine.community_cards) == 3:
                state = self.engine.deal_turn()
                phase = "turn"
            elif len(self.engine.community_cards) == 4:
                state = self.engine.deal_river()
                phase = "river"
            else:
                break

            await self.ws.broadcast_event(room, "cards_dealt", {
                "phase": phase,
                "community_cards": state.community_cards,
            })
            await self.ws.broadcast_state(room, state)

        state = self.engine.run_showdown()
        await self.ws.broadcast_event(room, "showdown", {
            "phase": "showdown",
            "community_cards": state.community_cards,
        })
        await self.ws.broadcast_state(room, state)
        return state

    async def run(self):
        """Main tournament loop."""
        self._running = True
        room = self.engine.tournament_id

        try:
            self.ws.reset_room_history(room)
            await self.ws.broadcast_room_snapshot(room)
            state = self.engine.start_tournament()
            self._level_started_at = time.time()
            await self.ws.broadcast_event(room, "tournament_start", {"tournament_id": room})
            await self.ws.broadcast_state(room, state)

            while not self.engine.is_tournament_over():
                state = await self.run_hand()
                if not self._running:
                    break

                # 10s pause between hands for spectators to review
                await self.ws.broadcast_event(room, "hand_end", {
                    "hand_number": self.engine.hand_number,
                })
                for _ in range(10):
                    if not self._running:
                        break
                    await asyncio.sleep(1)

                # Eliminate busted players
                for p in self.engine.players:
                    if p.chips == 0 and p.player_id not in self.engine.eliminated_order:
                        await self.ws.broadcast_event(room, "player_eliminated", {
                            "player_id": p.player_id,
                            "display_name": p.display_name,
                        })

                # Advance blinds based on hands played
                advanced_levels = self._advance_blinds_by_hands()
                for blinds in advanced_levels:
                    await self.ws.broadcast_event(room, "blind_level_changed", {
                        "level": blinds["level"],
                        "small_blind": blinds["small_blind"],
                        "big_blind": blinds["big_blind"],
                        "ante": blinds.get("ante", 0),
                    })

                await self.ws.broadcast_state(room, state)

                if self.delay > 0:
                    await asyncio.sleep(self.delay * 2)

            # Tournament over
            winner = self.engine.get_winner()
            if winner:
                standings = self._build_standings()
                await self.ws.broadcast(room, {
                    "type": "tournament_over",
                    "data": {
                        "winner_id": winner.player_id,
                        "winner_name": winner.display_name,
                        "standings": standings,
                    },
                    "timestamp": time.time(),
                })

        except Exception as e:
            await self.ws.broadcast(room, {
                "type": "error",
                "data": {"message": f"Tournament error: {e}"},
                "timestamp": time.time(),
            })
            raise
        finally:
            self._running = False

    async def run_hand(self) -> GameState:
        """Run a single hand: pre-flop → flop → turn → river → showdown."""
        room = self.engine.tournament_id
        state = self.engine.start_new_hand()
        await self.ws.broadcast_state(room, state)

        if self.engine.should_auto_runout_board():
            return await self._runout_to_showdown(state)

        active_count = self._count_active(state)

        # Pre-flop betting
        if active_count > 1:
            state = await self._run_betting_round()
            await self.ws.broadcast_state(room, state)
            if self.engine.should_auto_runout_board():
                return await self._runout_to_showdown(state)

        # Flop
        active_count = self._count_active(state)
        if active_count > 1:
            state = self.engine.deal_flop()
            await self.ws.broadcast_event(room, "cards_dealt", {
                "phase": "flop",
                "community_cards": state.community_cards,
            })
            await self.ws.broadcast_state(room, state)
            if self.engine.should_auto_runout_board():
                return await self._runout_to_showdown(state)
            state = await self._run_betting_round()
            await self.ws.broadcast_state(room, state)
            if self.engine.should_auto_runout_board():
                return await self._runout_to_showdown(state)

        # Turn
        active_count = self._count_active(state)
        if active_count > 1:
            state = self.engine.deal_turn()
            await self.ws.broadcast_event(room, "cards_dealt", {
                "phase": "turn",
                "community_cards": state.community_cards,
            })
            await self.ws.broadcast_state(room, state)
            if self.engine.should_auto_runout_board():
                return await self._runout_to_showdown(state)
            state = await self._run_betting_round()
            await self.ws.broadcast_state(room, state)
            if self.engine.should_auto_runout_board():
                return await self._runout_to_showdown(state)

        # River
        active_count = self._count_active(state)
        if active_count > 1:
            state = self.engine.deal_river()
            await self.ws.broadcast_event(room, "cards_dealt", {
                "phase": "river",
                "community_cards": state.community_cards,
            })
            await self.ws.broadcast_state(room, state)
            if self.engine.should_auto_runout_board():
                return await self._runout_to_showdown(state)
            state = await self._run_betting_round()
            await self.ws.broadcast_state(room, state)
            if self.engine.should_auto_runout_board():
                return await self._runout_to_showdown(state)

        # Showdown (if needed — only when 2+ players reach the end)
        active_players = [p for p in state.players if p.is_active]
        if len(active_players) >= 2:
            state = self.engine.run_showdown()
            await self.ws.broadcast_event(room, "showdown", {
                "phase": "showdown",
                "community_cards": state.community_cards,
            })
            await self.ws.broadcast_state(room, state)
        # Uncontested win — pot already awarded, no reveal prompt
        return state

    async def _run_betting_round(self) -> GameState:
        """Run one betting round, collecting AI actions sequentially."""
        room = self.engine.tournament_id
        state = self.engine._build_state([])
        max_iterations = 100  # safety cap
        already_finalised = False

        for _ in range(max_iterations):
            if self.engine.is_betting_round_complete():
                if already_finalised:
                    return state
                return self.engine._finalise_betting_round([])

            # Find current player
            active_idx = state.active_player_index
            if active_idx is None:
                if self.engine.should_auto_runout_board():
                    return self.engine._finalise_betting_round([])
                break

            player_state = state.players[active_idx]
            if player_state.is_all_in or not player_state.is_active:
                # Move to next
                state = self.engine._build_state([])
                self.engine.active_player_index = self.engine._next_player_to_act()
                continue

            # Get AI config for this player
            ai_config = next(
                (p for p in self.players_config if p.id == player_state.player_id), None
            )
            if not ai_config:
                break

            legal_actions = self.engine.get_legal_actions(player_state.player_id)
            if not legal_actions:
                if self.engine.should_auto_runout_board() or self.engine.is_betting_round_complete():
                    return self.engine._finalise_betting_round([])
                break

            state.action_timeout_seconds = float(self.ai.timeout)
            state.action_deadline_ts = time.time() + float(self.ai.timeout)

            # Tell spectators this AI is thinking
            await self.ws.broadcast_event(room, "ai_thinking", {
                "player_id": player_state.player_id,
                "player_name": player_state.display_name,
            })
            await self.ws.broadcast_state(room, state)

            action: PlayerAction | None = None
            fallback_reason = ""
            try:
                # Build history-aware prompt for this AI
                history = self.engine.get_hand_history()
                custom_history = []
                for h in history:
                    h_copy = dict(h)
                    # Use per-player hole cards from the hand summary
                    cards_map = h.get("hole_cards_map", {})
                    my_cards = cards_map.get(ai_config.id)
                    if my_cards:
                        h_copy["my_hole_cards"] = my_cards
                    custom_history.append(h_copy)
                prompt_builder = PromptBuilder(history=custom_history, config=self.engine.config)

                # Broadcast debug prompt
                sys_prompt = prompt_builder.build_system_prompt(ai_config, state)
                user_prompt = prompt_builder.build_user_message(ai_config, state, legal_actions)
                await self.ws.broadcast_debug_prompt(
                    room, player_state.player_id, player_state.display_name,
                    sys_prompt, user_prompt,
                )

                # Get AI decision (use streaming if thinking is enabled)
                if ai_config.enable_thinking:
                    async def on_think(chunk: str):
                        await self.ws.broadcast_thinking_chunk(
                            room, player_state.player_id,
                            player_state.display_name, chunk,
                        )

                    action = await self.ai.stream_action(
                        ai_config, state, legal_actions,
                        on_thinking=on_think,
                        prompt_builder=prompt_builder,
                    )

                else:
                    action = await self.ai.get_action(
                        ai_config, state, legal_actions,
                        prompt_builder=prompt_builder,
                    )
            except Exception as e:
                fallback_reason = f"Auto fallback after AI error: {e}"
                print(f"[TournamentService] AI action failed for {player_state.player_id}: {e}")
                action = self._build_safe_fallback_action(
                    player_state.player_id,
                    legal_actions,
                    fallback_reason,
                )
            finally:
                if ai_config.enable_thinking:
                    await self._finalize_thinking_safe(
                        room,
                        player_state.player_id,
                        player_state.display_name,
                        fallback_text=(action.thinking_content if action else fallback_reason),
                    )

            # Apply action, and degrade once more if the proposed action explodes.
            try:
                state = self.engine.apply_action(action)
            except Exception as e:
                print(f"[TournamentService] apply_action failed for {player_state.player_id}: {e}")
                fallback_action = self._build_safe_fallback_action(
                    player_state.player_id,
                    self.engine.get_legal_actions(player_state.player_id),
                    f"Auto fallback after apply_action error: {e}",
                )
                action = fallback_action
                state = self.engine.apply_action(fallback_action)

            # Mark if the hand was finalised inside apply_action (to avoid double _end_hand)
            active_left = sum(1 for p in state.players if p.is_active)
            if active_left <= 1:
                already_finalised = True

            # Broadcast action event
            await self.ws.broadcast_event(room, "player_action", {
                "player_id": player_state.player_id,
                "player_name": player_state.display_name,
                "action": action.action_type.value,
                "amount": action.amount,
            })
            await self.ws.broadcast_state(room, state)

            # If hand ended (apply_action triggered _finalise_betting_round),
            # break immediately to avoid double _end_hand in loop re-check
            active_left = sum(1 for p in state.players if p.is_active)
            if active_left <= 1 or state.phase.value == "showdown":
                break

            if self.delay > 0:
                await asyncio.sleep(self.delay)

        return self.engine._build_state([])

    def _count_active(self, state: GameState) -> int:
        return sum(1 for p in state.players if p.is_active)

    def _build_standings(self) -> list[dict]:
        """Build final standings (sorted by chips, then elimination order)."""
        standings = []
        for i, p in enumerate(sorted(self.engine.players, key=lambda x: x.chips, reverse=True)):
            if p.chips > 0:
                standings.append({
                    "player_id": p.player_id,
                    "display_name": p.display_name,
                    "position": i + 1,
                    "chips": p.chips,
                })
        # Add eliminated players in reverse order
        for i, pid in enumerate(reversed(self.engine.eliminated_order)):
            p = next((pl for pl in self.engine.players if pl.player_id == pid), None)
            if p:
                standings.append({
                    "player_id": pid,
                    "display_name": p.display_name,
                    "position": len(standings) + 1,
                    "chips": 0,
                })
        return standings

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

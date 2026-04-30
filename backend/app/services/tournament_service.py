import asyncio
import time
import random
import re
from app.core.game_base import GameEngine
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
        engine: GameEngine,
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
        """Main tournament loop — dispatches to game-specific implementation."""
        game_type = getattr(self.engine, 'game_type', 'poker')
        if game_type == 'werewolf':
            await self._run_werewolf_loop()
        else:
            await self._run_poker_loop()

    async def _run_poker_loop(self):
        """Poker-specific tournament loop."""
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
                await self.ws.broadcast_to_target_rooms(room, {
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
        state = self.engine.get_state()
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
                state = self.engine.get_state()
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

        return self.engine.get_state()

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

    async def _run_werewolf_loop(self):
        """Werewolf-specific tournament loop."""
        self._running = True
        room = self.engine.tournament_id

        try:
            self.ws.reset_room_history(room)
            await self.ws.broadcast_room_snapshot(room)
            state = self.engine.start_game()
            await self.ws.broadcast_event(room, "tournament_start", {
                "tournament_id": room,
                "game_type": "werewolf",
            })
            await self.ws.broadcast_state(room, state)
            setup_hold = float(getattr(self.engine.config, "day_duration_seconds", 0) or 0)
            if setup_hold > 0:
                await asyncio.sleep(setup_hold)

            # --- 游戏主循环 ---
            while not self.engine.is_game_over() and self._running:
                state = await self._run_werewolf_round()
                if not self._running:
                    break

                await self.ws.broadcast_state(room, state)

                if self.delay > 0:
                    await asyncio.sleep(self.delay * 2)

            # Game over
            winner_info = self.engine.get_winner_dict()
            if winner_info:
                standings = self._build_werewolf_standings()
                await self.ws.broadcast_to_target_rooms(room, {
                    "type": "tournament_over",
                    "data": {
                        "winner_id": winner_info.get("team", ""),
                        "winner_name": winner_info.get("team_name", ""),
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

    async def _run_sheriff_election(self, room: str):
        """Run the sheriff election phase (上警环节)."""
        from app.prompts.werewolf_builder import WerewolfPromptBuilder
        from app.models.werewolf import WerewolfPhase

        self.engine.phase = WerewolfPhase.SHERIFF_ELECTION
        state = self.engine.get_state()
        await self.ws.broadcast_event(room, "phase_change", {"phase": "sheriff_election"})
        await self.ws.broadcast_state(room, state)

        # Step 1: AI decides whether to run for sheriff
        if self.engine.get_sheriff_candidates_needed():
            async def decide_campaign(player):
                ai_config = next((p for p in self.players_config if p.id == player.player_id), None)
                if not ai_config:
                    return None

                prompt_builder = WerewolfPromptBuilder(engine=self.engine)
                sys_prompt = prompt_builder.build_system_prompt(ai_config)
                user_prompt = prompt_builder.build_campaign_decision_prompt(ai_config)

                try:
                    await self.ws.broadcast_event(room, "ai_thinking", {
                        "player_id": player.player_id,
                        "player_name": player.display_name,
                        "phase": "sheriff_campaign",
                    })
                    await self.ws.broadcast_debug_prompt(
                        room, player.player_id, player.display_name,
                        sys_prompt, user_prompt,
                    )
                    action = await self.ai.get_action_werewolf(ai_config, sys_prompt, user_prompt)
                    raw = (action.raw_response or "").lower()
                    return player.player_id if "campaign" in raw else None
                except Exception as e:
                    print(f"[Sheriff] Campaign decision failed for {player.player_id}: {e}")
                    return None

            campaign_players = [p for p in self.engine.players if p.is_alive]
            campaign_results = await asyncio.gather(
                *(decide_campaign(player) for player in campaign_players),
            )
            candidates = [pid for pid in campaign_results if pid]
            for player_id in candidates:
                player = self.engine._get_player(player_id)
                if player:
                    self._add_system_event(f"{player.display_name} 决定参选警长")

            if candidates:
                self.engine.set_sheriff_candidates(candidates)
            else:
                self.engine.set_sheriff_candidates([])  # 会随机选人参选

        state = self.engine.get_state()
        await self.ws.broadcast_state(room, state)
        await asyncio.sleep(1)

        # Step 2: Candidate speeches are public and must be sequential so later
        # candidates can react to earlier speeches in their prompt history.
        for candidate_id in self.engine.get_sheriff_speaking_order():
            player = self.engine._get_player(candidate_id)
            if not player:
                continue
            ai_config = next((p for p in self.players_config if p.id == candidate_id), None)
            if not ai_config:
                continue

            prompt_builder = WerewolfPromptBuilder(engine=self.engine)
            sys_prompt = prompt_builder.build_system_prompt(ai_config)
            user_prompt = prompt_builder.build_sheriff_speech_prompt(ai_config)

            await self.ws.broadcast_event(room, "ai_thinking", {
                "player_id": candidate_id,
                "player_name": player.display_name,
                "phase": "sheriff_speech",
            })
            await self.ws.broadcast_debug_prompt(
                room, candidate_id, player.display_name,
                sys_prompt, user_prompt,
            )
            await self.ws.broadcast_state(room, self.engine.get_state())

            try:
                action, streamed_speech = await self._stream_werewolf_speech_action(
                    room=room,
                    ai_config=ai_config,
                    sys_prompt=sys_prompt,
                    user_prompt=user_prompt,
                    player_id=candidate_id,
                    player_name=player.display_name,
                    event_prefix=f"🎤 {player.display_name}（警长候选人）：",
                )

                await self._finalize_thinking_safe(
                    room, candidate_id, player.display_name,
                    fallback_text=action.thinking_content if action else "",
                )
                self.engine.record_sheriff_speech(
                    candidate_id,
                    action.raw_response if action else "",
                    announce=not streamed_speech,
                )
                await self.ws.broadcast_state(room, self.engine.get_state())
            except Exception as e:
                print(f"[Sheriff] Speech failed for {candidate_id}: {e}")
                await self._finalize_thinking_safe(
                    room, candidate_id, player.display_name,
                    fallback_text=f"Auto fallback: {e}",
                )
                self.engine.record_sheriff_speech(candidate_id, f"[{player.display_name} 沉默]")
                await self.ws.broadcast_state(room, self.engine.get_state())

            if self.delay > 0:
                await asyncio.sleep(self.delay)

        # Step 3: Vote for sheriff
        candidates_snapshot = set(self.engine.get_sheriff_candidates())

        async def run_sheriff_pk_speeches():
            for candidate_id in self.engine.get_sheriff_speaking_order():
                player = self.engine._get_player(candidate_id)
                ai_config = next((p for p in self.players_config if p.id == candidate_id), None)
                if not player or not ai_config:
                    continue

                prompt_builder = WerewolfPromptBuilder(engine=self.engine)
                sys_prompt = prompt_builder.build_system_prompt(ai_config)
                user_prompt = prompt_builder.build_sheriff_speech_prompt(ai_config)

                try:
                    await self.ws.broadcast_event(room, "ai_thinking", {
                        "player_id": candidate_id,
                        "player_name": player.display_name,
                        "phase": "sheriff_pk_speech",
                    })
                    await self.ws.broadcast_debug_prompt(
                        room, candidate_id, player.display_name,
                        sys_prompt, user_prompt,
                    )
                    action, streamed_speech = await self._stream_werewolf_speech_action(
                        room=room,
                        ai_config=ai_config,
                        sys_prompt=sys_prompt,
                        user_prompt=user_prompt,
                        player_id=candidate_id,
                        player_name=player.display_name,
                        event_prefix=f"🎤 {player.display_name}（警长候选人）：",
                    )
                    self.engine.record_sheriff_speech(
                        candidate_id,
                        action.raw_response if action else "",
                        announce=not streamed_speech,
                    )
                    await self._finalize_thinking_safe(
                        room, candidate_id, player.display_name,
                        fallback_text=action.thinking_content if action else "",
                    )
                except Exception as e:
                    print(f"[Sheriff] PK speech failed for {candidate_id}: {e}")
                    self.engine.record_sheriff_speech(candidate_id, f"[{player.display_name} 沉默]")
                    await self._finalize_thinking_safe(
                        room, candidate_id, player.display_name,
                        fallback_text=f"Auto fallback: {e}",
                    )

                await self.ws.broadcast_state(room, self.engine.get_state())
                if self.delay > 0:
                    await asyncio.sleep(self.delay)

        async def collect_sheriff_vote(voter):
            ai_config = next((p for p in self.players_config if p.id == voter.player_id), None)
            if not ai_config:
                return voter.player_id, None

            prompt_builder = WerewolfPromptBuilder(engine=self.engine)
            sys_prompt = prompt_builder.build_system_prompt(ai_config)
            user_prompt = prompt_builder.build_sheriff_vote_prompt(ai_config)

            try:
                await self.ws.broadcast_event(room, "ai_thinking", {
                    "player_id": voter.player_id,
                    "player_name": voter.display_name,
                    "phase": "sheriff_vote",
                })
                await self.ws.broadcast_debug_prompt(
                    room, voter.player_id, voter.display_name,
                    sys_prompt, user_prompt,
                )
                action = await self.ai.get_action_werewolf(ai_config, sys_prompt, user_prompt)
                raw = (action.raw_response or "").strip()
                target_id = self.engine._parse_target(raw)
                if target_id not in candidates_snapshot:
                    target_id = None
                return voter.player_id, target_id
            except Exception as e:
                print(f"[Sheriff] Vote failed for {voter.player_id}: {e}")
                return voter.player_id, None

        vote_results = await asyncio.gather(
            *(collect_sheriff_vote(voter) for voter in self.engine.get_sheriff_voters()),
        )
        for voter_id, target_id in vote_results:
            self.engine.cast_sheriff_vote(voter_id, target_id)

        # Step 4: Resolve
        state = self.engine.resolve_sheriff_election()
        await self.ws.broadcast_state(room, state)

        vote_result = getattr(state, "sheriff_vote_result", None) or {}
        if vote_result.get("is_tie") and not vote_result.get("no_sheriff"):
            if self.delay > 0:
                await asyncio.sleep(self.delay)
            await run_sheriff_pk_speeches()

            candidates_snapshot = set(self.engine.get_sheriff_candidates())
            vote_results = await asyncio.gather(
                *(collect_sheriff_vote(voter) for voter in self.engine.get_sheriff_voters()),
            )
            for voter_id, target_id in vote_results:
                self.engine.cast_sheriff_vote(voter_id, target_id)
            state = self.engine.resolve_sheriff_election()

        await self.ws.broadcast_event(room, "sheriff_elected", {
            "sheriff_id": self.engine.sheriff_id,
        })
        await self.ws.broadcast_state(room, state)
        await asyncio.sleep(2)

    async def _run_sheriff_speaking_order(self, room: str):
        """Let the sheriff choose day speaking order; sheriff speaks last."""
        sheriff_id = getattr(self.engine, "sheriff_id", None)
        sheriff = self.engine._get_player(sheriff_id) if sheriff_id else None
        if not sheriff or not sheriff.is_alive:
            return

        ai_config = next((p for p in self.players_config if p.id == sheriff.player_id), None)
        if not ai_config:
            self.engine.decide_day_speaking_order("")
            return

        from app.prompts.werewolf_builder import WerewolfPromptBuilder
        prompt_builder = WerewolfPromptBuilder(engine=self.engine)
        sys_prompt = prompt_builder.build_system_prompt(ai_config)
        user_prompt = prompt_builder.build_sheriff_order_prompt(ai_config)

        await self.ws.broadcast_event(room, "ai_thinking", {
            "player_id": sheriff.player_id,
            "player_name": sheriff.display_name,
            "phase": "sheriff_order",
        })
        await self.ws.broadcast_debug_prompt(
            room, sheriff.player_id, sheriff.display_name,
            sys_prompt, user_prompt,
        )

        try:
            if ai_config.enable_thinking:
                async def on_think(chunk: str, pid=sheriff.player_id, pname=sheriff.display_name):
                    await self.ws.broadcast_thinking_chunk(room, pid, pname, chunk)

                action = await self.ai.stream_action_werewolf(
                    ai_config, sys_prompt, user_prompt, on_thinking=on_think,
                )
            else:
                action = await self.ai.get_action_werewolf(ai_config, sys_prompt, user_prompt)

            raw = action.raw_response if action else ""
            self.engine.decide_day_speaking_order(raw or "")
            await self._finalize_thinking_safe(
                room, sheriff.player_id, sheriff.display_name,
                fallback_text=action.thinking_content if action else "",
            )
        except Exception as e:
            print(f"[Sheriff] Speaking order failed for {sheriff.player_id}: {e}")
            self.engine.decide_day_speaking_order("")
            await self._finalize_thinking_safe(
                room, sheriff.player_id, sheriff.display_name,
                fallback_text=f"Auto fallback: {e}",
            )

    @staticmethod
    def _extract_werewolf_speech(raw: str) -> str:
        label = r'(?:ACTION|SPEECH|VOTE|NOTES|TARGET)'
        matches = re.findall(
            rf'(?is)(?:^|\n)\s*SPEECH\s*[:：]\s*(.*?)(?=\n\s*{label}\s*[:：]|\Z)',
            raw,
        )
        if matches:
            return matches[-1].strip()
        match = re.search(r'(?:SPEECH|speech|Speech)[:：]\s*(.+)', raw, re.DOTALL)
        if match:
            return match.group(1).strip()
        return raw.strip()

    @staticmethod
    def _extract_streaming_werewolf_speech(raw: str) -> str:
        text = TournamentService._extract_werewolf_speech(raw)
        lines = text.splitlines()
        if not lines:
            return ""
        control_labels = ("ACTION", "VOTE", "NOTES", "TARGET")
        last = lines[-1].strip().upper()
        if last and any(label.startswith(last) for label in control_labels):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def _add_system_event(self, text: str):
        """Add an event to the engine's event list."""
        if hasattr(self.engine, '_events'):
            self.engine._events.append({"text": text, "hidden": False})

    async def _handle_sheriff_succession_request(self, room: str):
        """Ask the dying sheriff AI to choose a successor."""
        pending = self.engine.get_pending_sheriff_succession()
        if not pending:
            return

        old_sheriff_id = pending["old_sheriff_id"]
        old_sheriff_name = pending["old_sheriff_name"]
        self._add_system_event(f"📿 警长 {old_sheriff_name} 即将移交警徽")

        ai_config = next((p for p in self.players_config if p.id == old_sheriff_id), None)
        if not ai_config:
            # Fallback: random alive player
            alive = [p for p in self.engine.players if p.is_alive]
            if alive:
                successor = random.choice(alive)
                self.engine.apply_sheriff_succession(successor.player_id)
            await self.ws.broadcast_state(room, self.engine.get_state())
            return

        from app.prompts.werewolf_builder import WerewolfPromptBuilder
        prompt_builder = WerewolfPromptBuilder(engine=self.engine)
        sys_prompt = prompt_builder.build_system_prompt(ai_config)
        user_prompt = prompt_builder.build_sheriff_successor_prompt(ai_config)

        await self.ws.broadcast_event(room, "ai_thinking", {
            "player_id": old_sheriff_id,
            "player_name": old_sheriff_name,
            "phase": "sheriff_succession",
        })
        await self.ws.broadcast_debug_prompt(
            room, old_sheriff_id, old_sheriff_name,
            sys_prompt, user_prompt,
        )

        try:
            action = await self.ai.get_action_werewolf(ai_config, sys_prompt, user_prompt)
            raw = (action.raw_response or "").strip()
            raw_lower = raw.lower()

            # Check for "destroy / 撕警徽" intent first
            if any(token in raw_lower for token in ("destroy", "撕", "撕毁", "撕掉", "销毁", "撕警徽", "不要警徽")):
                self.engine.apply_sheriff_destroy()
                await self.ws.broadcast_state(room, self.engine.get_state())
                return

            target_id = self.engine._parse_target(raw)
            if target_id:
                target = self.engine._get_player(target_id)
                if target and target.is_alive:
                    self.engine.apply_sheriff_succession(target_id)
                    await self.ws.broadcast_state(room, self.engine.get_state())
                    return
        except Exception as e:
            print(f"[Sheriff] Succession decision failed: {e}")

        # Fallback: random alive player
        alive = [p for p in self.engine.players if p.is_alive]
        if alive:
            successor = random.choice(alive)
            self.engine.apply_sheriff_succession(successor.player_id)
        await self.ws.broadcast_state(room, self.engine.get_state())

    async def _stream_werewolf_speech_action(
        self,
        *,
        room: str,
        ai_config: AIPlayerConfig,
        sys_prompt: str,
        user_prompt: str,
        player_id: str,
        player_name: str,
        event_prefix: str,
    ) -> tuple[PlayerAction, bool]:
        """Stream public speech into the event list while preserving thinking stream."""
        event_index: int | None = None
        last_broadcast = 0.0

        def ensure_event() -> int | None:
            nonlocal event_index
            if not hasattr(self.engine, "_events"):
                return None
            if event_index is None:
                event_index = len(self.engine._events)
                self.engine._events.append({"text": f"{event_prefix}…", "hidden": False})
            return event_index

        async def update_event(raw_content: str, *, force: bool = False):
            nonlocal last_broadcast
            speech = self._extract_streaming_werewolf_speech(raw_content)
            if not speech:
                return
            idx = ensure_event()
            if idx is None:
                return
            self.engine._events[idx]["text"] = f"{event_prefix}{speech}"
            now = time.monotonic()
            if force or now - last_broadcast >= 0.15:
                last_broadcast = now
                await self.ws.broadcast_state(room, self.engine.get_state())

        async def on_think(chunk: str):
            await self.ws.broadcast_thinking_chunk(room, player_id, player_name, chunk)

        async def on_content(content: str):
            await update_event(content)

        action = await self.ai.stream_action_werewolf(
            ai_config,
            sys_prompt,
            user_prompt,
            on_thinking=on_think if ai_config.enable_thinking else None,
            on_content=on_content,
        )
        await update_event(action.raw_response or "", force=True)
        return action, event_index is not None

    async def _run_werewolf_round(self):
        """Run one werewolf round: night phase → day phase."""
        room = self.engine.tournament_id

        # Night phase
        night_state = self.engine.start_night()
        await self.ws.broadcast_event(room, "phase_change", {"phase": "night"})
        await self.ws.broadcast_state(room, night_state)
        night_hold = float(getattr(self.engine.config, "night_duration_seconds", 0) or 0)
        if night_hold > 0:
            await asyncio.sleep(night_hold)

        # --- 狼人夜间交流（多轮讨论+投票，共识后自动开刀）---
        from app.prompts.werewolf_builder import WerewolfPromptBuilder

        if self.engine.needs_werewolf_discussion():
            MAX_ROUNDS = 5
            discussion_round = 0

            while not self.engine.is_werewolf_consensus_reached() and discussion_round < MAX_ROUNDS:
                discussion_round += 1
                wolves = self.engine.get_werewolf_discussion_order()

                for wolf in wolves:
                    # 如果已经达成共识，提前结束本轮
                    if self.engine.is_werewolf_consensus_reached():
                        break

                    ai_config = next((p for p in self.players_config if p.id == wolf.player_id), None)
                    if not ai_config:
                        continue

                    await self.ws.broadcast_event(room, "ai_thinking", {
                        "player_id": wolf.player_id,
                        "player_name": wolf.display_name,
                        "phase": "werewolf_discussion",
                        "round": discussion_round,
                    })

                    prompt_builder = WerewolfPromptBuilder(engine=self.engine)

                    try:
                        sys_prompt = prompt_builder.build_system_prompt(ai_config)
                        user_prompt = prompt_builder.build_werewolf_discussion_prompt(ai_config, discussion_round)
                        await self.ws.broadcast_debug_prompt(
                            room, wolf.player_id, wolf.display_name,
                            sys_prompt, user_prompt,
                        )

                        action, streamed_speech = await self._stream_werewolf_speech_action(
                            room=room,
                            ai_config=ai_config,
                            sys_prompt=sys_prompt,
                            user_prompt=user_prompt,
                            player_id=wolf.player_id,
                            player_name=wolf.display_name,
                            event_prefix=f"🐺 {wolf.display_name}：",
                        )

                        speech = action.raw_response or action.thinking_content or ""
                        self.engine.record_werewolf_discussion(
                            wolf.player_id,
                            speech,
                            discussion_round,
                            announce=not streamed_speech,
                        )
                        await self._finalize_thinking_safe(
                            room, wolf.player_id, wolf.display_name,
                            fallback_text=speech,
                        )
                    except Exception as e:
                        print(f"[Werewolf] Discussion failed for {wolf.player_id}: {e}")
                        await self._finalize_thinking_safe(
                            room, wolf.player_id, wolf.display_name,
                            fallback_text=f"Error: {e}",
                        )

                    await self.ws.broadcast_state(room, self.engine.get_state())
                    if self.delay > 0:
                        await asyncio.sleep(self.delay / 3)

            self.engine.mark_werewolf_discussed()

        # --- 狼人刀人（共识自动执行 / 单狼人直接决定 / 未共识则AI决定）---
        if self.engine.needs_werewolf_kill_decision():
            kill_info = self.engine.get_werewolf_kill_action_info()
            if kill_info:
                consensus_target = kill_info.get("consensus_target")
                player_id = kill_info["player_id"]
                ai_config = next((p for p in self.players_config if p.id == player_id), None)

                if consensus_target:
                    # 共识达成，自动执行
                    victim = self.engine._get_player(consensus_target)
                    self._add_system_event(f"🐺 狼人达成共识，刀杀 {victim.display_name if victim else consensus_target}")
                    from app.models.game import PlayerAction
                    from app.models.tournament import ActionType
                    dummy_action = PlayerAction(
                        player_id=player_id,
                        action_type=ActionType.CALL,
                        raw_response=f"CONSENSUS: {consensus_target}",
                    )
                    self.engine.apply_night_action(player_id, dummy_action, consensus_target=consensus_target)
                elif ai_config:
                    # 未共识或单狼人，AI决定
                    await self.ws.broadcast_event(room, "ai_thinking", {
                        "player_id": player_id,
                        "player_name": kill_info.get("player_name", ""),
                        "phase": "werewolf_kill",
                    })

                    prompt_builder = WerewolfPromptBuilder(engine=self.engine)

                    try:
                        sys_prompt = prompt_builder.build_system_prompt(ai_config)
                        user_prompt = prompt_builder.build_werewolf_kill_decision_prompt(ai_config, kill_info)
                        await self.ws.broadcast_debug_prompt(
                            room, player_id, kill_info.get("player_name", ""),
                            sys_prompt, user_prompt,
                        )

                        if ai_config.enable_thinking:
                            async def on_think(chunk: str, pid=player_id, pname=kill_info.get("player_name", "")):
                                await self.ws.broadcast_thinking_chunk(room, pid, pname, chunk)

                            action = await self.ai.stream_action_werewolf(
                                ai_config, sys_prompt, user_prompt, on_thinking=on_think,
                            )
                        else:
                            action = await self.ai.get_action_werewolf(ai_config, sys_prompt, user_prompt)

                        self.engine.apply_night_action(player_id, action)
                        await self._finalize_thinking_safe(
                            room, player_id, kill_info.get("player_name", ""),
                            fallback_text=action.thinking_content if action else "",
                        )
                    except Exception as e:
                        print(f"[Werewolf] Kill decision failed for {player_id}: {e}")
                        self.engine.skip_night_action(player_id)
                        await self._finalize_thinking_safe(
                            room, player_id, kill_info.get("player_name", ""),
                            fallback_text=f"Auto fallback: {e}",
                        )
                else:
                    self.engine.skip_night_action(player_id)

        # --- 其他角色夜晚行动（预言家、女巫、守卫）---
        night_action_guard = 0
        while self.engine.has_pending_night_actions():
            night_action_guard += 1
            if night_action_guard > len(self.engine.players) + 4:
                print("[Werewolf] Night action guard tripped; forcing night resolution")
                break
            action_info = self.engine.get_next_night_action()
            if not action_info:
                break

            player_id = action_info["player_id"]
            role = action_info["role"]
            if not action_info.get("targets"):
                self.engine.skip_night_action(player_id)
                continue

            ai_config = next((p for p in self.players_config if p.id == player_id), None)
            if not ai_config:
                self.engine.skip_night_action(player_id)
                continue

            role_id = action_info.get("role_id")
            public_role_events = {
                "seer": "🔮 预言家行动中",
                "witch": "💊 女巫行动中",
                "guard": "🛡️ 守卫行动中",
            }
            if role_id in public_role_events:
                self._add_system_event(public_role_events[role_id])

            await self.ws.broadcast_event(room, "ai_thinking", {
                "player_id": player_id,
                "player_name": action_info.get("player_name", ""),
                "phase": f"night_{role_id or action_info.get('action_type', 'action')}",
                "role": role,
            })

            await self.ws.broadcast_state(room, self.engine.get_state())

            try:
                from app.prompts.werewolf_builder import WerewolfPromptBuilder
                prompt_builder = WerewolfPromptBuilder(engine=self.engine)

                sys_prompt = prompt_builder.build_system_prompt(ai_config)
                user_prompt = prompt_builder.build_night_action_prompt(ai_config, action_info)
                await self.ws.broadcast_debug_prompt(
                    room, player_id, action_info.get("player_name", ""),
                    sys_prompt, user_prompt,
                )

                if ai_config.enable_thinking:
                    async def on_think(chunk: str):
                        await self.ws.broadcast_thinking_chunk(
                            room, player_id, action_info.get("player_name", ""), chunk,
                        )

                    action = await self.ai.stream_action_werewolf(
                        ai_config, sys_prompt, user_prompt, on_thinking=on_think,
                    )
                else:
                    action = await self.ai.get_action_werewolf(ai_config, sys_prompt, user_prompt)

                self.engine.apply_night_action(player_id, action)
                await self._finalize_thinking_safe(
                    room, player_id, action_info.get("player_name", ""),
                    fallback_text=action.thinking_content if action else "",
                )
            except Exception as e:
                print(f"[Werewolf] AI action failed for {player_id}: {e}")
                self.engine.skip_night_action(player_id)
                await self._finalize_thinking_safe(
                    room, player_id, action_info.get("player_name", ""),
                    fallback_text=f"Auto fallback: {e}",
                )

            await self.ws.broadcast_state(room, self.engine.get_state())
            if self.delay > 0:
                await asyncio.sleep(self.delay)

        # Resolve night
        night_result = self.engine.resolve_night()
        await self.ws.broadcast_event(room, "night_result", night_result.to_public_dict())
        await self.ws.broadcast_state(room, night_result)

        # Handle sheriff succession (night death)
        if self.engine.get_pending_sheriff_succession():
            await self._handle_sheriff_succession_request(room)

        if self.engine.is_game_over():
            return night_result

        await asyncio.sleep(2)

        if (
            self.engine.round_number == 1
            and self.engine.config.sheriff_election
            and not getattr(self, "_werewolf_sheriff_election_done", False)
        ):
            await self._run_sheriff_election(room)
            self._werewolf_sheriff_election_done = True

        # Day phase - discussion
        day_state = self.engine.start_day()
        await self.ws.broadcast_event(room, "phase_change", {"phase": "day"})
        await self.ws.broadcast_state(room, day_state)
        await self._run_sheriff_speaking_order(room)
        await self.ws.broadcast_state(room, self.engine.get_state())
        day_hold = float(getattr(self.engine.config, "day_duration_seconds", 0) or 0)
        if day_hold > 0:
            await asyncio.sleep(day_hold)

        # Day discussion is one full speaking order: sheriff chooses direction and speaks last.
        # After the sheriff finishes, the game moves directly to voting.
        for round_idx in range(1):
            for player in self.engine.get_speaking_order():
                if not player.is_alive:
                    continue

                ai_config = next((p for p in self.players_config if p.id == player.player_id), None)
                if not ai_config:
                    continue

                await self.ws.broadcast_event(room, "ai_thinking", {
                    "player_id": player.player_id,
                    "player_name": player.display_name,
                    "phase": "discussion",
                })

                try:
                    from app.prompts.werewolf_builder import WerewolfPromptBuilder
                    prompt_builder = WerewolfPromptBuilder(engine=self.engine)
                    sys_prompt = prompt_builder.build_system_prompt(ai_config)
                    user_prompt = prompt_builder.build_discussion_prompt(ai_config)
                    await self.ws.broadcast_debug_prompt(
                        room, player.player_id, player.display_name,
                        sys_prompt, user_prompt,
                    )

                    action, streamed_speech = await self._stream_werewolf_speech_action(
                        room=room,
                        ai_config=ai_config,
                        sys_prompt=sys_prompt,
                        user_prompt=user_prompt,
                        player_id=player.player_id,
                        player_name=player.display_name,
                        event_prefix=f"🎤 {player.display_name}：",
                    )

                    raw = action.raw_response or action.thinking_content or ""
                    self.engine.record_speech(
                        player.player_id,
                        raw,
                        round_idx + 1,
                        announce=not streamed_speech,
                    )
                    await self._finalize_thinking_safe(
                        room, player.player_id, player.display_name,
                        fallback_text=action.thinking_content or "",
                    )
                except Exception as e:
                    print(f"[Werewolf] Discussion failed for {player.player_id}: {e}")
                    self.engine.record_speech(player.player_id, f"[{player.display_name} 沉默]")
                    await self._finalize_thinking_safe(
                        room, player.player_id, player.display_name,
                        fallback_text=f"Auto fallback: {e}",
                    )

                await self.ws.broadcast_state(room, self.engine.get_state())
                if self.delay > 0:
                    await asyncio.sleep(self.delay / 2)

            if self.engine.is_game_over():
                return self.engine.get_state()

        # Vote phase
        vote_state = self.engine.start_vote()
        await self.ws.broadcast_event(room, "phase_change", {"phase": "vote"})
        await self.ws.broadcast_state(room, vote_state)

        async def collect_vote_round(thinking_phase: str = "vote"):
            voting_players = self.engine.get_voting_players()

            async def collect_single_vote(player):
                ai_config = next((p for p in self.players_config if p.id == player.player_id), None)
                if not ai_config:
                    return player, None

                await self.ws.broadcast_event(room, "ai_thinking", {
                    "player_id": player.player_id,
                    "player_name": player.display_name,
                    "phase": thinking_phase,
                })

                try:
                    from app.prompts.werewolf_builder import WerewolfPromptBuilder
                    prompt_builder = WerewolfPromptBuilder(engine=self.engine)
                    sys_prompt = prompt_builder.build_system_prompt(ai_config)
                    user_prompt = prompt_builder.build_vote_prompt(ai_config)
                    await self.ws.broadcast_debug_prompt(
                        room, player.player_id, player.display_name,
                        sys_prompt, user_prompt,
                    )

                    if ai_config.enable_thinking:
                        async def on_think(chunk: str, pid=player.player_id, pname=player.display_name):
                            await self.ws.broadcast_thinking_chunk(room, pid, pname, chunk)

                        action = await self.ai.stream_action_werewolf(
                            ai_config, sys_prompt, user_prompt, on_thinking=on_think,
                        )
                    else:
                        action = await self.ai.get_action_werewolf(ai_config, sys_prompt, user_prompt)

                    await self._finalize_thinking_safe(
                        room, player.player_id, player.display_name,
                        fallback_text=action.thinking_content if action else "",
                    )
                    return player, action
                except Exception as e:
                    print(f"[Werewolf] Vote failed for {player.player_id}: {e}")
                    await self._finalize_thinking_safe(
                        room, player.player_id, player.display_name,
                        fallback_text=f"Auto fallback: {e}",
                    )
                    return player, None

            # Concurrent AI voting
            results = await asyncio.gather(
                *(collect_single_vote(p) for p in voting_players),
            )

            # Apply votes sequentially to engine
            for player, action in results:
                if action is not None:
                    self.engine.cast_vote(player.player_id, action)
                else:
                    self.engine.cast_vote(player.player_id, None)

            await self.ws.broadcast_state(room, self.engine.get_state())

        async def run_vote_pk_speeches():
            for player in self.engine.get_vote_pk_candidates():
                ai_config = next((p for p in self.players_config if p.id == player.player_id), None)
                if not ai_config:
                    continue

                await self.ws.broadcast_event(room, "ai_thinking", {
                    "player_id": player.player_id,
                    "player_name": player.display_name,
                    "phase": "vote_pk_speech",
                })

                try:
                    from app.prompts.werewolf_builder import WerewolfPromptBuilder
                    prompt_builder = WerewolfPromptBuilder(engine=self.engine)
                    sys_prompt = prompt_builder.build_system_prompt(ai_config)
                    user_prompt = prompt_builder.build_discussion_prompt(ai_config)
                    await self.ws.broadcast_debug_prompt(
                        room, player.player_id, player.display_name,
                        sys_prompt, user_prompt,
                    )

                    action, streamed_speech = await self._stream_werewolf_speech_action(
                        room=room,
                        ai_config=ai_config,
                        sys_prompt=sys_prompt,
                        user_prompt=user_prompt,
                        player_id=player.player_id,
                        player_name=player.display_name,
                        event_prefix=f"🎤 {player.display_name}：",
                    )

                    raw = action.raw_response or action.thinking_content or ""
                    self.engine.record_speech(
                        player.player_id,
                        raw,
                        2,
                        announce=not streamed_speech,
                    )
                    await self._finalize_thinking_safe(
                        room, player.player_id, player.display_name,
                        fallback_text=action.thinking_content if action else "",
                    )
                except Exception as e:
                    print(f"[Werewolf] Vote PK speech failed for {player.player_id}: {e}")
                    self.engine.record_speech(player.player_id, f"[{player.display_name} 沉默]")
                    await self._finalize_thinking_safe(
                        room, player.player_id, player.display_name,
                        fallback_text=f"Auto fallback: {e}",
                    )

                await self.ws.broadcast_state(room, self.engine.get_state())
                if self.delay > 0:
                    await asyncio.sleep(self.delay / 2)

        # Collect votes
        await collect_vote_round("vote")

        # Resolve vote
        result = self.engine.resolve_vote()
        await self.ws.broadcast_event(room, "vote_result", result.to_public_dict())
        await self.ws.broadcast_state(room, result)

        # Handle sheriff succession (voted out)
        if self.engine.get_pending_sheriff_succession():
            await self._handle_sheriff_succession_request(room)

        vote_result_data = getattr(result, "vote_result", None) or {}
        if vote_result_data.get("is_tie") and not vote_result_data.get("no_elimination"):
            if self.delay > 0:
                await asyncio.sleep(self.delay)
            await run_vote_pk_speeches()
            pk_vote_state = self.engine.start_vote_pk()
            await self.ws.broadcast_state(room, pk_vote_state)
            await collect_vote_round("vote_pk")
            result = self.engine.resolve_vote()
            await self.ws.broadcast_event(room, "vote_result", result.to_public_dict())
            await self.ws.broadcast_state(room, result)

            # Handle sheriff succession (PK voted out)
            if self.engine.get_pending_sheriff_succession():
                await self._handle_sheriff_succession_request(room)

        return result

    def _build_werewolf_standings(self) -> list[dict]:
        """Build final standings for werewolf."""
        standings = []
        for p in self.engine.players:
            role = getattr(p, 'role_name', '未知')
            standings.append({
                "player_id": p.player_id,
                "display_name": p.display_name,
                "role": role,
                "is_alive": p.is_alive,
            })
        return standings

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

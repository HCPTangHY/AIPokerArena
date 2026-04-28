export interface PlayerState {
  id: string;
  display_name: string;
  chips: number;
  is_active: boolean;
  is_all_in: boolean;
  seat_index: number;
  bet_this_round: number;
  total_bet: number;
  last_action: {
    type: string;
    amount: number;
  } | null;
  hole_cards: string[];
  avatar_url: string;
  equity: number | null;
}

export interface PotInfo {
  amount: number;
  eligible_count: number;
}

export interface GameStateData {
  tournament_id: string;
  hand_number: number;
  level: number;
  small_blind: number;
  big_blind: number;
  ante: number;
  phase: string;
  community_cards: string[];
  pots: PotInfo[];
  current_bet: number;
  min_raise: number;
  dealer_index: number;
  active_player_index: number | null;
  action_timeout_seconds?: number;
  action_deadline_ts?: number | null;
  players: PlayerState[];
  events: GameEvent[];
  hand_history: HandHistoryItem[];
}

export interface GameEvent {
  text: string;
  ts: number;
}

export interface HandHistoryAction {
  player_id: string;
  player_name: string;
  phase: string;
  position: string;
  action: string;
  amount: number;
}

export interface HandHistorySettlement {
  name: string;
  player_id: string;
  chip_change: number;
  cards: string[];
  revealed: boolean;
}

export interface HandHistoryItem {
  hand_number: number;
  actions: HandHistoryAction[];
  settlement: HandHistorySettlement[];
  flop_cards: string[];
  turn_card: string | null;
  river_card: string | null;
}

export interface ChatMessage {
  player_id: string;
  player_name: string;
  message: string;
  is_thinking: boolean;
  is_spectator?: boolean;
  timestamp: number;
}

export interface ActiveThinkingData {
  player_id: string;
  player_name: string;
  text: string;
}

export interface HistorySnapshotData {
  chat_messages: ChatMessage[];
  active_thinking: ActiveThinkingData | null;
}

export interface TournamentOverData {
  winner_id: string;
  winner_name: string;
  standings: {
    player_id: string;
    display_name: string;
    position: number;
    chips: number;
  }[];
}

export interface DebugPrompt {
  player_id: string;
  player_name: string;
  system_prompt: string;
  user_message: string;
  timestamp: number;
}

export type WSMessage =
  | { type: 'game_state'; data: GameStateData; timestamp: number }
  | { type: 'game_event'; data: { event_type: string } & Record<string, unknown>; timestamp: number }
  | { type: 'chat'; player_id: string; player_name: string; message: string; is_thinking: boolean; is_spectator?: boolean; timestamp: number }
  | { type: 'thinking_chunk'; player_id: string; player_name: string; chunk: string; timestamp: number }
  | { type: 'debug_prompt'; player_id: string; player_name: string; system_prompt: string; user_message: string; timestamp: number }
  | { type: 'tournament_start'; data: { tournament_id: string }; timestamp: number }
  | { type: 'tournament_over'; data: TournamentOverData; timestamp: number }
  | { type: 'history_snapshot'; data: HistorySnapshotData; timestamp: number }
  | { type: 'spectator_count'; data: { count: number }; timestamp: number }
  | { type: 'error'; data: { message: string }; timestamp: number };

export interface WerewolfPlayer {
  id: string;
  display_name: string;
  role_name: string;
  team: string | null;
  spectator_role_name?: string;
  spectator_team?: string | null;
  is_alive: boolean;
  is_sheriff: boolean;
  has_voted: boolean;
  vote_target: string | null;
  seat_index: number;
  avatar_url: string;
  speech_count: number;
  death_cause: string;
}

export interface WerewolfGameState {
  tournament_id: string;
  game_type: string;
  round_number: number;
  phase: string;
  players: WerewolfPlayer[];
  sheriff_id: string | null;
  sheriff_candidates: string[];
  speaking_order: string[];
  current_speaker: string | null;
  night_kill_target: string | null;
  votes: Record<string, string>;
  vote_result: WerewolfVoteResult | null;
  sheriff_vote_result: WerewolfSheriffVoteResult | null;
  events: WerewolfEvent[];
  night_log: NightLogEntry[];
  is_over: boolean;
  winner_team: string | null;
}

export interface WerewolfVoteResult {
  eliminated_id: string;
  eliminated_name: string;
  votes: Record<string, string>;
  tally: Record<string, number>;
  round?: number;
  is_tie?: boolean;
  tie_ids?: string[];
  no_elimination?: boolean;
}

export interface WerewolfSheriffVoteResult {
  winner_id: string;
  winner_name: string;
  votes: Record<string, string>;
  tally: Record<string, number>;
  candidate_ids: string[];
  round?: number;
  is_tie?: boolean;
  tie_ids?: string[];
  no_sheriff?: boolean;
}

export interface WerewolfEvent {
  text: string;
  hidden?: boolean;
}

export interface NightLogEntry {
  action: string;
  actor: string;
  target: string;
  result?: string;
}

export interface WerewolfWSMessage {
  type: string;
  data?: WerewolfGameState;
  player_id?: string;
  player_name?: string;
  message?: string;
  chunk?: string;
  timestamp: number;
}

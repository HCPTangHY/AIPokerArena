export interface BlindLevel {
  level: number;
  small_blind: number;
  big_blind: number;
  ante: number;
}

export interface TournamentConfig {
  name: string;
  initial_chips: number;
  small_blind_initial: number;
  big_blind_initial: number;
  blind_level_minutes: number;
  blind_levels: BlindLevel[];
  ante_enabled: boolean;
  ante_start_level: number;
  max_players: number;
  action_timeout_seconds: number;
}

export interface AIPlayerConfig {
  id: string;
  display_name: string;
  api_endpoint: string;
  api_key: string;
  model_name: string;
  enable_thinking: boolean;
  thinking_visible: boolean;
  thinking_budget_tokens: number;
  reasoning_effort: string;
  prompt_override: string;
  avatar_url: string;
}

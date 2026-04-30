let API_BASE = '/poker/api';

function getApiBase() {
  const gamePrefix = window.location.pathname.split('/').filter(Boolean)[0];
  if (gamePrefix === 'poker' || gamePrefix === 'werewolf') {
    return `/${gamePrefix}/api`;
  }
  return API_BASE;
}

export function setApiBase(gameType: string) {
  API_BASE = `/${gameType}/api`;
}

function getToken(): string | null {
  return localStorage.getItem('token');
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${getApiBase()}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Auth
  getLoginUrl: (next?: string) => {
    const qs = next ? `?next=${encodeURIComponent(next)}` : '';
    return request<{ url: string }>(`/auth/login${qs}`);
  },
  getCallback: (code: string, state: string) =>
    request<{ token: string; user: Record<string, unknown> }>(`/auth/callback?code=${code}&state=${state}`),
  getMe: () => request<{ user: Record<string, unknown> }>('/auth/me'),

  // Config
  getTournamentConfig: (gameType?: string) => {
    const qs = gameType ? `?game_type=${gameType}` : '';
    return request<Record<string, unknown>>(`/config/tournament${qs}`);
  },
  updateTournamentConfig: (config: Record<string, unknown>) =>
    request('/config/tournament', { method: 'PUT', body: JSON.stringify(config) }),
  getPlayers: (gameType?: string) => {
    const qs = gameType ? `?game_type=${gameType}` : '';
    return request<Record<string, unknown>[]>(`/config/players${qs}`);
  },
  addPlayer: (player: Record<string, unknown>, gameType?: string) => {
    const qs = gameType ? `?game_type=${gameType}` : '';
    return request(`/config/players${qs}`, { method: 'POST', body: JSON.stringify(player) });
  },
  updatePlayer: (id: string, player: Record<string, unknown>, gameType?: string) => {
    const qs = gameType ? `?game_type=${gameType}` : '';
    return request(`/config/players/${id}${qs}`, { method: 'PUT', body: JSON.stringify(player) });
  },
  deletePlayer: (id: string, gameType?: string) => {
    const qs = gameType ? `?game_type=${gameType}` : '';
    return request(`/config/players/${id}${qs}`, { method: 'DELETE' });
  },

  // Tournament
  startTournament: (gameType?: string) => {
    const qs = gameType ? `?game_type=${gameType}` : '';
    return request<{ status: string; tournament_id: string }>(`/tournament/start${qs}`, { method: 'POST' });
  },
  stopTournament: (gameType?: string) => {
    const qs = gameType ? `?game_type=${gameType}` : '';
    return request<{ status: string }>(`/tournament/stop${qs}`, { method: 'POST' });
  },
  getTournamentStatus: (gameType?: string) => {
    const qs = gameType ? `?game_type=${gameType}` : '';
    return request<{ running: boolean; tournament_id?: string; state?: Record<string, unknown> }>(`/tournament/status${qs}`);
  },
};

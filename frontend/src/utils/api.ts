const API_BASE = '/poker/api';

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

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Auth
  getLoginUrl: () => request<{ url: string }>('/auth/login'),
  getCallback: (code: string, state: string) =>
    request<{ token: string; user: Record<string, unknown> }>(`/auth/callback?code=${code}&state=${state}`),
  getMe: () => request<{ user: Record<string, unknown> }>('/auth/me'),

  // Config
  getTournamentConfig: () => request<Record<string, unknown>>('/config/tournament'),
  updateTournamentConfig: (config: Record<string, unknown>) =>
    request('/config/tournament', { method: 'PUT', body: JSON.stringify(config) }),
  getPlayers: () => request<Record<string, unknown>[]>('/config/players'),
  addPlayer: (player: Record<string, unknown>) =>
    request('/config/players', { method: 'POST', body: JSON.stringify(player) }),
  updatePlayer: (id: string, player: Record<string, unknown>) =>
    request(`/config/players/${id}`, { method: 'PUT', body: JSON.stringify(player) }),
  deletePlayer: (id: string) =>
    request(`/config/players/${id}`, { method: 'DELETE' }),

  // Tournament
  startTournament: () =>
    request<{ status: string; tournament_id: string }>('/tournament/start', { method: 'POST' }),
  stopTournament: () =>
    request<{ status: string }>('/tournament/stop', { method: 'POST' }),
  getTournamentStatus: () =>
    request<{ running: boolean; tournament_id?: string; state?: Record<string, unknown> }>('/tournament/status'),
};

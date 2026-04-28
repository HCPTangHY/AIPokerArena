import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import type { TournamentConfig, AIPlayerConfig } from '../types/config';

const DEFAULT_CONFIG: TournamentConfig = {
  name: 'AI Poker Tournament',
  initial_chips: 10000,
  small_blind_initial: 25,
  big_blind_initial: 50,
  blind_level_minutes: 3,
  blind_levels: [],
  ante_enabled: false,
  ante_start_level: 0,
  max_players: 10,
  action_timeout_seconds: 30,
};

const DEFAULT_PLAYER: AIPlayerConfig = {
  id: '',
  display_name: '',
  api_endpoint: 'https://api.openai.com',
  api_key: '',
  model_name: 'gpt-4o',
  enable_thinking: false,
  thinking_visible: false,
  thinking_budget_tokens: 4096,
  reasoning_effort: 'high',
  prompt_override: '',
  avatar_url: '',
};

export function ConfigPage() {
  const [config, setConfig] = useState<TournamentConfig>(DEFAULT_CONFIG);
  const [players, setPlayers] = useState<AIPlayerConfig[]>([]);
  const [editingPlayer, setEditingPlayer] = useState<AIPlayerConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const [cfg, pls] = await Promise.all([
          api.getTournamentConfig(),
          api.getPlayers(),
        ]);
        setConfig(cfg as unknown as TournamentConfig);
        setPlayers(pls as unknown as AIPlayerConfig[]);
      } catch (e) {
        console.error('加载配置失败：', e);
      } finally {
        setLoading(false);
      }
    };

    void loadConfig();
  }, []);

  const saveConfig = async () => {
    await api.updateTournamentConfig(config as unknown as Record<string, unknown>);
    alert('配置已保存');
  };

  const addPlayer = async () => {
    if (players.length >= 10) {
      alert('最多 10 名玩家');
      return;
    }
    const p = { ...DEFAULT_PLAYER, id: `ai_${Date.now()}` };
    setEditingPlayer(p);
  };

  const savePlayer = async () => {
    if (!editingPlayer) return;
    try {
      const existing = players.find((p) => p.id === editingPlayer.id);
      if (existing) {
        await api.updatePlayer(editingPlayer.id, editingPlayer as unknown as Record<string, unknown>);
        setPlayers((prev) => prev.map((p) => (p.id === editingPlayer.id ? editingPlayer : p)));
      } else {
        await api.addPlayer(editingPlayer as unknown as Record<string, unknown>);
        setPlayers((prev) => [...prev, editingPlayer]);
      }
      setEditingPlayer(null);
    } catch (e) {
      alert('错误：' + (e as Error).message);
    }
  };

  const deletePlayer = async (id: string) => {
    if (!confirm('确认删除此玩家？')) return;
    await api.deletePlayer(id);
    setPlayers((prev) => prev.filter((p) => p.id !== id));
  };

  if (loading) return <div style={{ padding: 24, color: '#eee' }}>Loading config...</div>;

  return (
    <div className="config-page" style={styles.container}>
      <h1 style={styles.title}>配置</h1>

      {/* Tournament Settings */}
      <section className="config-section" style={styles.section}>
        <h2>Tournament Settings</h2>
        <div className="config-form-grid" style={styles.formGrid}>
          <label>
            Name:
            <input value={config.name} onChange={(e) => setConfig({ ...config, name: e.target.value })} />
          </label>
          <label>
            Initial Chips:
            <input type="number" value={config.initial_chips}
              onChange={(e) => setConfig({ ...config, initial_chips: Number(e.target.value) })} />
          </label>
          <label>
            Small Blind:
            <input type="number" value={config.small_blind_initial}
              onChange={(e) => setConfig({ ...config, small_blind_initial: Number(e.target.value) })} />
          </label>
          <label>
            Big Blind:
            <input type="number" value={config.big_blind_initial}
              onChange={(e) => setConfig({ ...config, big_blind_initial: Number(e.target.value) })} />
          </label>
          <label>
            Blind Level (min):
            <input type="number" value={config.blind_level_minutes}
              onChange={(e) => setConfig({ ...config, blind_level_minutes: Number(e.target.value) })} />
          </label>
          <label>
            Action Timeout (s):
            <input type="number" value={config.action_timeout_seconds}
              onChange={(e) => setConfig({ ...config, action_timeout_seconds: Number(e.target.value) })} />
          </label>
          <label>
            Max Players:
            <input type="number" min={2} max={10} value={config.max_players}
              onChange={(e) => setConfig({ ...config, max_players: Number(e.target.value) })} />
          </label>
          <label>
            <input type="checkbox" checked={config.ante_enabled}
              onChange={(e) => setConfig({ ...config, ante_enabled: e.target.checked })} />
            Ante Enabled
          </label>
          {config.ante_enabled && (
            <label>
              Ante Start Level:
              <input type="number" value={config.ante_start_level}
                onChange={(e) => setConfig({ ...config, ante_start_level: Number(e.target.value) })} />
            </label>
          )}
        </div>
        <button onClick={saveConfig} style={styles.saveBtn}>Save Config</button>
      </section>

      {/* Player Management */}
      <section className="config-section" style={styles.section}>
        <h2>AI Players ({players.length}/10)</h2>
        <button onClick={addPlayer} style={styles.addBtn}>Add Player</button>

        <div className="config-player-list" style={styles.playerList}>
          {players.map((p) => (
            <div key={p.id} className="config-player-item" style={styles.playerItem}>
              <div className="config-player-meta" style={styles.playerMeta}>
                <strong>{p.display_name || p.id}</strong>
                <span>{p.model_name} @ {p.api_endpoint}</span>
                <span>思考：{p.enable_thinking ? (p.thinking_visible ? '可见' : '隐藏') : '关闭'}</span>
              </div>
              <div className="config-player-actions">
                <button onClick={() => setEditingPlayer({ ...p })} style={styles.editBtn}>Edit</button>
                <button onClick={() => deletePlayer(p.id)} style={styles.deleteBtn}>Delete</button>
              </div>
            </div>
          ))}
          {players.length === 0 && <p style={{ color: '#666' }}>No players configured.</p>}
        </div>
      </section>

      {/* Edit Player Modal */}
      {editingPlayer && (
        <div className="config-modal" style={styles.modal}>
          <div className="config-modal-content" style={styles.modalContent}>
            <h2>{players.find((p) => p.id === editingPlayer.id) ? '编辑' : 'Add'} Player</h2>
            <div className="config-form-grid" style={styles.formGrid}>
              <label>
                ID:
                <input value={editingPlayer.id}
                  onChange={(e) => setEditingPlayer({ ...editingPlayer, id: e.target.value })}
                  disabled={!!players.find((p) => p.id === editingPlayer.id)} />
              </label>
              <label>
                显示名称：
                <input value={editingPlayer.display_name}
                  onChange={(e) => setEditingPlayer({ ...editingPlayer, display_name: e.target.value })} />
              </label>
              <label>
                API Endpoint:
                <input value={editingPlayer.api_endpoint}
                  onChange={(e) => setEditingPlayer({ ...editingPlayer, api_endpoint: e.target.value })} />
              </label>
              <label>
                API Key:
                <input type="password" value={editingPlayer.api_key}
                  onChange={(e) => setEditingPlayer({ ...editingPlayer, api_key: e.target.value })} />
              </label>
              <label>
                Model Name:
                <input value={editingPlayer.model_name}
                  onChange={(e) => setEditingPlayer({ ...editingPlayer, model_name: e.target.value })} />
              </label>
              <label>
                <input type="checkbox" checked={editingPlayer.enable_thinking}
                  onChange={(e) => setEditingPlayer({ ...editingPlayer, enable_thinking: e.target.checked })} />
                Enable Thinking
              </label>
              {editingPlayer.enable_thinking && (
                <>
                  <label>
                    <input type="checkbox" checked={editingPlayer.thinking_visible}
                      onChange={(e) => setEditingPlayer({ ...editingPlayer, thinking_visible: e.target.checked })} />
                    Thinking Visible to Spectators
                  </label>
                  <label>
                    Reasoning Effort:
                    <select value={editingPlayer.reasoning_effort}
                      onChange={(e) => setEditingPlayer({ ...editingPlayer, reasoning_effort: e.target.value })}>
                      <option value="high">High</option>
                      <option value="max">Max</option>
                    </select>
                  </label>
                  <label>
                    Budget Tokens (Claude only):
                    <input type="number" min={256} max={32768} value={editingPlayer.thinking_budget_tokens}
                      onChange={(e) => setEditingPlayer({ ...editingPlayer, thinking_budget_tokens: Number(e.target.value) })} />
                  </label>
                </>
              )}
              <label>
                System Prompt Template (empty = default):
                <textarea value={editingPlayer.prompt_override}
                  onChange={(e) => setEditingPlayer({ ...editingPlayer, prompt_override: e.target.value })}
                  rows={8}
                  placeholder="Leave empty to use the default poker prompt. Customize to give this AI a unique playing style." />
              </label>
            </div>
            <div className="config-modal-actions" style={styles.modalActions}>
              <button onClick={savePlayer} style={styles.saveBtn}>Save Player</button>
              <button onClick={() => setEditingPlayer(null)} style={styles.cancelBtn}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    color: '#eee',
    background: '#1a1a2e',
  },
  title: {
    color: '#e94560',
    marginBottom: '24px',
  },
  section: {
    padding: '16px',
    background: '#16213e',
    borderRadius: '8px',
  },
  formGrid: {
    marginBottom: '12px',
  },
  saveBtn: {
    padding: '8px 16px',
    background: '#27ae60',
    color: '#fff',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontWeight: 600,
  },
  addBtn: {
    padding: '8px 16px',
    background: '#3498db',
    color: '#fff',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontWeight: 600,
    marginBottom: '12px',
  },
  playerList: {
    gap: '8px',
  },
  playerItem: {
    padding: '8px 12px',
    background: '#0f3460',
    borderRadius: '6px',
  },
  playerMeta: {
    minWidth: 0,
  },
  editBtn: {
    padding: '4px 8px',
    background: '#f39c12',
    color: '#fff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    marginRight: '4px',
  },
  deleteBtn: {
    padding: '4px 8px',
    background: '#e74c3c',
    color: '#fff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  modal: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.7)',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 100,
  },
  modalContent: {
    background: '#16213e',
    borderRadius: '12px',
    padding: '24px',
    overflow: 'auto',
  },
  modalActions: {
    marginTop: '16px',
  },
  cancelBtn: {
    padding: '8px 16px',
    background: '#555',
    color: '#fff',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
  },
};

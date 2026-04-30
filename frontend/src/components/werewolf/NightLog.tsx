import type { NightLogEntry } from '../../types/werewolf';

interface Props {
  entries: NightLogEntry[];
  getPlayerName: (id: string) => string;
}

const ACTION_LABELS: Record<string, string> = {
  kill: '🐺 狼人刀杀',
  check: '🔍 预言家查验',
  save: '💊 女巫解药',
  poison: '☠️ 女巫毒药',
  guard: '🛡️ 守卫守护',
};

export function NightLog({ entries, getPlayerName }: Props) {
  if (entries.length === 0) return null;

  return (
    <div style={{
      background: 'rgba(255,255,255,0.03)',
      borderRadius: '12px',
      border: '1px solid rgba(255,255,255,0.08)',
      padding: '12px',
    }}>
      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#ccc', marginBottom: '8px' }}>
        🌙 夜晚行动记录
      </div>
      {entries.map((entry, i) => (
        <div key={i} style={{
          padding: '4px 0',
          fontSize: '0.75rem',
          color: '#999',
          borderBottom: i < entries.length - 1 ? '1px solid rgba(255,255,255,0.03)' : 'none',
        }}>
          {ACTION_LABELS[entry.action] || entry.action}：
          {getPlayerName(entry.actor)} → {getPlayerName(entry.target)}
          {entry.result ? ` (${entry.result})` : ''}
        </div>
      ))}
    </div>
  );
}

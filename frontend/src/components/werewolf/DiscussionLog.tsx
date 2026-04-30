import type { WerewolfEvent } from '../../types/werewolf';

interface Props {
  events: WerewolfEvent[];
}

export function DiscussionLog({ events }: Props) {
  // Show only speech events (those with 🎤)
  const speeches = events.filter(e => !e.hidden && e.text.includes('🎤'));

  if (speeches.length === 0) return null;

  return (
    <div style={{
      background: 'rgba(255,255,255,0.03)',
      borderRadius: '12px',
      border: '1px solid rgba(255,255,255,0.08)',
      padding: '12px',
      maxHeight: '300px',
      overflowY: 'auto',
    }}>
      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#ccc', marginBottom: '8px' }}>
        💬 发言记录
      </div>
      {speeches.slice(-15).map((e, i) => (
        <div key={i} style={{
          padding: '3px 0',
          fontSize: '0.75rem',
          color: '#bbb',
          borderBottom: '1px solid rgba(255,255,255,0.03)',
        }}>
          {e.text}
        </div>
      ))}
    </div>
  );
}

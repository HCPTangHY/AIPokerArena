import type { WerewolfPlayer } from '../../types/werewolf';

interface Props {
  player: WerewolfPlayer;
  isActive: boolean;
  isCurrentSpeaker: boolean;
  onClick?: () => void;
}

export function PlayerCard({ player, isActive, isCurrentSpeaker, onClick }: Props) {
  const borderColor = !player.is_alive
    ? '#555'
    : player.is_sheriff
      ? '#f0c040'
      : isCurrentSpeaker
        ? '#4fc3f7'
        : 'rgba(255,255,255,0.15)';

  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '6px',
        padding: '10px',
        background: isActive ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.03)',
        borderRadius: '12px',
        border: `2px solid ${borderColor}`,
        cursor: onClick ? 'pointer' : 'default',
        opacity: player.is_alive ? 1 : 0.5,
        transition: 'all 0.3s ease',
        minWidth: '90px',
        boxShadow: isCurrentSpeaker ? '0 0 12px rgba(79,195,247,0.3)' : undefined,
      }}
    >
      {/* Avatar */}
      <div style={{ position: 'relative' }}>
        {player.avatar_url ? (
          <img
            src={player.avatar_url}
            alt={player.display_name}
            style={{
              width: '48px', height: '48px', borderRadius: '50%',
              border: `2px solid ${borderColor}`,
              objectFit: 'cover',
            }}
          />
        ) : (
          <div style={{
            width: '48px', height: '48px', borderRadius: '50%',
            background: player.is_alive ? '#334' : '#222',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '1.2rem', color: '#aaa',
            border: `2px solid ${borderColor}`,
          }}>
            {player.display_name[0]}
          </div>
        )}
        {/* Sheriff badge */}
        {player.is_sheriff && (
          <div style={{
            position: 'absolute', top: '-6px', right: '-6px',
            background: '#f0c040', color: '#1a1a2e',
            borderRadius: '50%', width: '22px', height: '22px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '0.75rem', fontWeight: 'bold',
            border: '2px solid #1a1a2e',
          }}>
            ★
          </div>
        )}
        {/* Death marker */}
        {!player.is_alive && (
          <div style={{
            position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
            fontSize: '2rem', opacity: 0.8,
          }}>
            💀
          </div>
        )}
      </div>

      {/* Name */}
      <div style={{
        fontSize: '0.8rem', fontWeight: 600, color: '#d0d0d0',
        textAlign: 'center', maxWidth: '90px',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {player.display_name}
      </div>

      {/* Role (if revealed) */}
      {player.role_name !== '???' && (
        <div style={{
          fontSize: '0.7rem', color: player.team === 'werewolf' ? '#ef5350' : '#66bb6a',
          background: 'rgba(255,255,255,0.06)', padding: '2px 8px', borderRadius: '6px',
        }}>
          {player.role_name}
        </div>
      )}

      {/* Vote target */}
      {player.has_voted && player.vote_target && (
        <div style={{ fontSize: '0.65rem', color: '#ff9800' }}>
          投了票
        </div>
      )}

      {/* Death cause */}
      {!player.is_alive && player.death_cause && (
        <div style={{ fontSize: '0.6rem', color: '#888' }}>
          {player.death_cause === 'killed' ? '被杀' :
           player.death_cause === 'voted_out' ? '被放逐' :
           player.death_cause === 'poisoned' ? '被毒杀' : player.death_cause}
        </div>
      )}
    </div>
  );
}

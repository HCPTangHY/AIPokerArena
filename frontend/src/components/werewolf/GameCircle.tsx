import { useEffect, useState } from 'react';
import type { WerewolfPlayer } from '../../types/werewolf';

interface Props {
  players: WerewolfPlayer[];
  currentSpeaker: string | null;
  sheriffId: string | null;
}

export function GameCircle({ players, currentSpeaker, sheriffId }: Props) {
  const [size, setSize] = useState(380);

  useEffect(() => {
    const updateSize = () => {
      setSize(Math.min(380, Math.max(300, window.innerWidth - 32)));
    };
    updateSize();
    window.addEventListener('resize', updateSize);
    return () => window.removeEventListener('resize', updateSize);
  }, []);

  const n = Math.max(players.length, 1);
  const radius = size * 0.42;
  const centerX = size / 2;
  const centerY = size / 2;
  const centerSize = Math.max(82, size * 0.26);
  const playerWidth = Math.max(68, size * 0.21);
  const avatarSize = Math.max(36, size * 0.105);

  return (
    <div style={{
      position: 'relative',
      width: `${size}px`,
      height: `${size}px`,
      maxWidth: '100%',
      margin: '0 auto',
    }}>
      {/* Center area */}
      <div style={{
        position: 'absolute',
        top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        width: `${centerSize}px`, height: `${centerSize}px`,
        borderRadius: '50%',
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.1)',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        gap: '4px',
      }}>
        <span style={{ fontSize: '0.7rem', color: '#888' }}>
          {players.filter(p => p.is_alive).length}/{players.length} 存活
        </span>
        {sheriffId && (
          <span style={{ fontSize: '0.65rem', color: '#f0c040' }}>
            警长: {players.find(p => p.id === sheriffId)?.display_name || '?'}
          </span>
        )}
      </div>

      {/* Player positions */}
      {players.map((player, i) => {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2;
        const x = centerX + radius * Math.cos(angle);
        const y = centerY + radius * Math.sin(angle);

        const isActive = currentSpeaker === player.id;
        const borderColor = !player.is_alive
          ? '#444'
          : player.is_sheriff
            ? '#f0c040'
            : isActive
              ? '#4fc3f7'
              : 'rgba(255,255,255,0.15)';

        return (
          <div
            key={player.id}
            style={{
              position: 'absolute',
              left: x - playerWidth / 2,
              top: y - avatarSize * 1.38,
              width: `${playerWidth}px`,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '3px',
              transition: 'all 0.3s ease',
            }}
          >
            <div style={{
              position: 'relative',
              width: `${avatarSize}px`, height: `${avatarSize}px`,
              borderRadius: '50%',
              border: `2px solid ${borderColor}`,
              overflow: 'hidden',
              background: '#222',
              opacity: player.is_alive ? 1 : 0.4,
              boxShadow: isActive ? '0 0 12px rgba(79,195,247,0.4)' : undefined,
            }}>
              {player.avatar_url ? (
                <img src={player.avatar_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <div style={{
                  width: '100%', height: '100%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '0.9rem', color: '#888',
                }}>
                  {player.display_name[0]}
                </div>
              )}
              {!player.is_alive && (
                <div style={{
                  position: 'absolute', top: 0, left: 0,
                  width: '100%', height: '100%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: 'rgba(0,0,0,0.5)', fontSize: '1rem',
                }}>
                  💀
                </div>
              )}
              {player.is_sheriff && player.is_alive && (
                <div style={{
                  position: 'absolute', top: '-4px', right: '-4px',
                  background: '#f0c040', color: '#1a1a2e',
                  borderRadius: '50%', width: '16px', height: '16px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '0.6rem', fontWeight: 'bold', border: '1px solid #1a1a2e',
                }}>
                  ★
                </div>
              )}
            </div>
            <div style={{
              fontSize: '0.6rem', color: isActive ? '#fff' : '#aaa',
              textAlign: 'center', maxWidth: `${playerWidth}px`,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              fontWeight: isActive ? 600 : 400,
            }}>
              {player.display_name}
            </div>
            {player.role_name !== '???' && !player.is_alive && (
              <div style={{ fontSize: '0.55rem', color: '#888' }}>
                {player.role_name}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

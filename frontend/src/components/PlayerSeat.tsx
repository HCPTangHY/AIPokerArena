import type { PlayerState } from '../types/game';
import { ChipStack } from './ChipStack';
import { ActionIndicator } from './ActionIndicator';
import { PlayerHand } from './PlayerHand';

interface Props {
  player: PlayerState;
  isDealer: boolean;
  isActive: boolean;
  showCards?: boolean;
}

function getInitials(name: string) {
  return name
    .trim()
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase() || 'AI';
}

export function PlayerSeat({ player, isDealer, isActive, showCards }: Props) {
  const isEliminated = player.chips === 0 && !player.is_active && !player.is_all_in;
  if (isEliminated) return null;

  const visibleCards = showCards || false;
  const isMuted = !player.is_active && !player.is_all_in;

  return (
    <div className={`player-seat ${isActive ? 'is-active' : ''} ${isMuted ? 'is-muted' : ''}`}>
      <div className="seat-avatar-wrap">
        <div className="seat-avatar">
          {player.avatar_url ? (
            <img src={player.avatar_url} alt="" />
          ) : (
            <span>{getInitials(player.display_name)}</span>
          )}
        </div>
        <span className="seat-number">{player.seat_index + 1}</span>
      </div>

      <div className="seat-panel">
        <div className="seat-title-row">
          <strong>{player.display_name}</strong>
          {isDealer && <span className="dealer-badge">D</span>}
        </div>
        <div className="seat-status-row">
          <span>{player.is_all_in ? '全下' : isActive ? '决策中' : player.is_active ? '观察' : '已弃牌'}</span>
          {visibleCards && player.equity != null && player.is_active && (
            <em>{player.equity.toFixed(1)}%</em>
          )}
        </div>

        <PlayerHand holeCards={player.hole_cards} visible={visibleCards} />

        <div className="seat-stack-row">
          <ChipStack amount={player.chips} />
        </div>
      </div>

      {player.last_action && (
        <ActionIndicator action={player.last_action.type} amount={player.last_action.amount} />
      )}
    </div>
  );
}

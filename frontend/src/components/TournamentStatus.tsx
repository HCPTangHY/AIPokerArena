import type { GameStateData } from '../types/game';

interface Props {
  status: string;
  gameState: GameStateData | null;
  isConnected: boolean;
  reconnectAttempt: number;
}

export function TournamentStatus({ status, gameState, isConnected, reconnectAttempt }: Props) {
  const text = status === 'running' && gameState
    ? `第 ${gameState.hand_number} 手 · Lv${gameState.level} · ${gameState.small_blind}/${gameState.big_blind}${gameState.ante > 0 ? ` (${gameState.ante} Ante)` : ''}`
    : status === 'finished'
      ? '已结束'
      : isConnected
        ? '已连接'
        : reconnectAttempt > 0
          ? `重连中 (${reconnectAttempt})`
          : '未连接';

  return (
    <div className={`tournament-status ${isConnected ? 'is-online' : 'is-offline'}`}>
      <span className="status-dot" />
      <span className="status-text">{text}</span>
    </div>
  );
}

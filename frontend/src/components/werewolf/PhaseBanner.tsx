const PHASE_NAMES: Record<string, string> = {
  role_assign: '分配角色',
  sheriff_election: '上警环节',
  night: '夜晚',
  day: '讨论阶段',
  vote: '放逐投票',
  game_over: '游戏结束',
};

const PHASE_ICONS: Record<string, string> = {
  role_assign: '🎭',
  sheriff_election: '⭐',
  night: '🌙',
  day: '☀️',
  vote: '🗳️',
  game_over: '🏆',
};

export function PhaseBanner({ phase, roundNumber }: { phase: string; roundNumber: number }) {
  const phaseName = PHASE_NAMES[phase] || phase;

  return (
    <div className="phase-banner" aria-label={`当前阶段：${phaseName}`} aria-live="polite">
      <span className="phase-banner-icon" aria-hidden="true">{PHASE_ICONS[phase] || '🎮'}</span>
      <span className="phase-banner-title">{phaseName}</span>
      {roundNumber > 0 && (
        <span className="phase-banner-round">
          第 {roundNumber} 轮
        </span>
      )}
    </div>
  );
}

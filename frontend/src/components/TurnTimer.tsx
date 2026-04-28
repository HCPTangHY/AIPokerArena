import { useEffect, useMemo, useState } from 'react';

interface Props {
  playerName: string;
  deadlineTs: number | null | undefined;
  timeoutSeconds: number | null | undefined;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function TurnTimer({ playerName, deadlineTs, timeoutSeconds }: Props) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!deadlineTs || !timeoutSeconds) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setNowMs(Date.now());
    }, 100);

    return () => window.clearInterval(timer);
  }, [deadlineTs, timeoutSeconds]);

  const remainingMs = useMemo(() => {
    if (!deadlineTs) return 0;
    return Math.max(0, deadlineTs * 1000 - nowMs);
  }, [deadlineTs, nowMs]);

  if (!deadlineTs || !timeoutSeconds) {
    return null;
  }

  const totalMs = Math.max(1000, timeoutSeconds * 1000);
  const progress = clamp(remainingMs / totalMs, 0, 1);
  const remainingSeconds = Math.ceil(remainingMs / 1000);
  const isUrgent = progress <= 0.2;

  return (
    <div className={`turn-timer ${isUrgent ? 'is-urgent' : ''}`}>
      <div className="turn-timer-head">
        <span>正在思考</span>
        <strong>{remainingSeconds}s</strong>
      </div>
      <div className="turn-timer-player">{playerName || '等待行动'}</div>
      <div className="turn-timer-track">
        <span style={{ width: `${progress * 100}%` }} />
      </div>
    </div>
  );
}

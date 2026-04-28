import type { PotInfo } from '../types/game';

interface Props {
  amount: number;
  pots: PotInfo[];
}

export function PotDisplay({ amount, pots }: Props) {
  if (amount <= 0 && pots.every((pot) => pot.amount <= 0)) return null;

  return (
    <div className="pot-display">
      <span>底池</span>
      <strong>{amount.toLocaleString('en-US')}</strong>
      {pots.length > 1 && (
        <em>+{pots.slice(1).map((pot) => pot.amount).join(' + ')} 边池</em>
      )}
    </div>
  );
}

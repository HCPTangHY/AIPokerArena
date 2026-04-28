interface Props {
  action: string;
  amount: number;
}

const ACTION_LABELS: Record<string, string> = {
  fold: '弃牌',
  check: '过牌',
  call: '跟注',
  raise: '加注',
  all_in: 'ALL IN',
  small_blind: '小盲',
  big_blind: '大盲',
};

export function ActionIndicator({ action, amount }: Props) {
  const label = ACTION_LABELS[action] || action;

  return (
    <div className={`action-indicator action-${action}`}>
      {action === 'all_in' && <span className="action-allin-fire" aria-hidden="true" />}
      {label}{amount > 0 ? ` ${amount}` : ''}
    </div>
  );
}

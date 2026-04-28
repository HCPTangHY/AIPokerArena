interface Props {
  amount: number;
}

const CHIP_COLORS = [
  '#ff4d5f',
  '#37a6ff',
  '#35d58a',
  '#12172a',
  '#f7a733',
  '#a66dff',
  '#ffd65c',
];

function getChipColor(amount: number): string {
  if (amount >= 5000) return CHIP_COLORS[6];
  if (amount >= 1000) return CHIP_COLORS[5];
  if (amount >= 500) return CHIP_COLORS[4];
  if (amount >= 100) return CHIP_COLORS[3];
  if (amount >= 25) return CHIP_COLORS[2];
  if (amount >= 5) return CHIP_COLORS[1];
  return CHIP_COLORS[0];
}

function formatStack(amount: number) {
  if (amount >= 10000) return `${(amount / 1000).toFixed(0)}K`;
  if (amount >= 1000) return `${(amount / 1000).toFixed(1)}K`;
  return String(amount);
}

export function ChipStack({ amount }: Props) {
  const chips = amount > 0 ? Math.min(Math.ceil(Math.log2(amount / 10 + 1)), 5) : 0;
  const chipColor = getChipColor(amount);

  return (
    <div className="chip-stack">
      {chips > 0 && (
        <div className="chip-stack-tokens" style={{ height: `calc(${chips} * 3px + 14px)` }}>
          {Array.from({ length: chips }).map((_, index) => (
            <span
              key={index}
              className="chip-token"
              style={{
                bottom: `calc(${index} * 3px)`,
                background: `linear-gradient(135deg, ${chipColor}, ${chipColor}cc)`,
              }}
            />
          ))}
        </div>
      )}
      <strong>{formatStack(amount)}</strong>
    </div>
  );
}

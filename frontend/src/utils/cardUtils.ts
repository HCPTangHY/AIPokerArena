const SUIT_SYMBOLS: Record<string, string> = {
  s: '♠', // ♠
  h: '♥', // ♥
  d: '♦', // ♦
  c: '♣', // ♣
};

const SUIT_COLORS: Record<string, string> = {
  s: '#1a1a2e',
  h: '#e74c3c',
  d: '#e74c3c',
  c: '#1a1a2e',
};

export interface CardInfo {
  rank: string;
  suit: string;
  color: string;
  symbol: string;
}

export function parseCard(card: string): CardInfo {
  if (!card || card.length < 2) {
    return { rank: '?', suit: '?', color: '#999', symbol: '?' };
  }
  const rank = card.slice(0, -1);
  const suit = card.slice(-1).toLowerCase();
  return {
    rank,
    suit,
    color: SUIT_COLORS[suit] || '#999',
    symbol: SUIT_SYMBOLS[suit] || suit,
  };
}

export function formatCard(card: string): string {
  const { rank, symbol } = parseCard(card);
  return `${rank}${symbol}`;
}

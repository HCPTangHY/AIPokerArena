import type { CardInfo } from '../utils/cardUtils';
import { parseCard } from '../utils/cardUtils';

interface Props {
  holeCards: string[];
  visible: boolean;
}

function CardFace({ card }: { card: CardInfo }) {
  return (
    <div className="poker-card hand-card is-face" style={{ color: card.color }}>
      <span className="card-corner top">
        {card.rank}
        <small>{card.symbol}</small>
      </span>
      <span className="card-symbol">{card.symbol}</span>
      <span className="card-corner bottom">
        {card.rank}
        <small>{card.symbol}</small>
      </span>
    </div>
  );
}

function CardBack() {
  return (
    <div className="poker-card hand-card is-back">
      <span className="card-back-pattern" />
    </div>
  );
}

export function PlayerHand({ holeCards, visible }: Props) {
  const cards = holeCards && holeCards.length >= 2 ? holeCards : ['?', '?'];

  return (
    <div className="player-hand" aria-label="玩家手牌">
      {cards.map((card, index) => (
        visible && card !== '?'
          ? <CardFace key={`${card}-${index}`} card={parseCard(card)} />
          : <CardBack key={`${card}-${index}`} />
      ))}
    </div>
  );
}

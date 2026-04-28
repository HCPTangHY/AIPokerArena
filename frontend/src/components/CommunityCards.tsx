import { parseCard } from '../utils/cardUtils';

interface Props {
  cards: string[];
}

export function CommunityCards({ cards }: Props) {
  return (
    <div className="community-cards" aria-label="公共牌">
      {[0, 1, 2, 3, 4].map((index) => {
        const card = cards[index];
        const info = card ? parseCard(card) : null;

        return (
          <div
            key={`${card ?? 'empty'}-${index}`}
            className={`poker-card community-card ${info ? 'is-face' : 'is-back'}`}
            style={{
              color: info?.color,
              animationDelay: `${index * 0.07}s`,
            }}
          >
            {info ? (
              <>
                <span className="card-corner top">
                  {info.rank}
                  <small>{info.symbol}</small>
                </span>
                <span className="card-symbol">{info.symbol}</span>
                <span className="card-corner bottom">
                  {info.rank}
                  <small>{info.symbol}</small>
                </span>
              </>
            ) : (
              <span className="card-back-pattern" />
            )}
          </div>
        );
      })}
    </div>
  );
}

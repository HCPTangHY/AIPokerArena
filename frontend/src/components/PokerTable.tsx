/* eslint-disable react-hooks/refs */
import { useEffect, useRef } from 'react';
import type { GameStateData } from '../types/game';
import { CommunityCards } from './CommunityCards';
import { PlayerSeat } from './PlayerSeat';
import { PotDisplay } from './PotDisplay';
import { TurnTimer } from './TurnTimer';

interface Props {
  gameState: GameStateData;
  showCards?: boolean;
}

const SEAT_POSITIONS: { top: string; left: string }[] = [
  { top: '84%', left: '50%' },
  { top: '73%', left: '28%' },
  { top: '48%', left: '13%' },
  { top: '25%', left: '23%' },
  { top: '13%', left: '45%' },
  { top: '13%', left: '65%' },
  { top: '25%', left: '86%' },
  { top: '48%', left: '94%' },
  { top: '73%', left: '80%' },
  { top: '84%', left: '64%' },
];

const PHASE_LABELS: Record<string, string> = {
  pre_flop: 'Pre-Flop',
  flop: 'Flop',
  turn: 'Turn',
  river: 'River',
  showdown: 'Showdown',
};

export function PokerTable({ gameState, showCards }: Props) {
  const { players, community_cards, pots, phase, dealer_index, active_player_index } = gameState;
  const totalPot = pots.reduce((sum, pot) => sum + pot.amount, 0);
  const activePlayer = active_player_index == null
    ? null
    : players.find((player) => player.seat_index === active_player_index) ?? players[active_player_index] ?? null;
  const handKey = `${gameState.tournament_id}:${gameState.hand_number}`;
  const handKeyRef = useRef(handKey);
  const holeCardCacheRef = useRef(new Map<string, string[]>());

  const timerRef = useRef<{ deadlineTs: number; timeoutSeconds: number } | null>(null);
  if (gameState.action_deadline_ts && gameState.action_timeout_seconds) {
    timerRef.current = {
      deadlineTs: gameState.action_deadline_ts,
      timeoutSeconds: gameState.action_timeout_seconds,
    };
  }
  const timer = timerRef.current;

  const holeCardCache = handKeyRef.current === handKey
    ? holeCardCacheRef.current
    : new Map<string, string[]>();

  useEffect(() => {
    if (handKeyRef.current !== handKey) {
      handKeyRef.current = handKey;
      holeCardCacheRef.current = new Map();
    }

    for (const player of players) {
      if (player.hole_cards.length > 0) {
        holeCardCacheRef.current.set(player.id, [...player.hole_cards]);
      }
    }
  }, [handKey, players]);

  return (
    <div className="poker-table-wrapper">
      <div className="poker-table" aria-label="德州扑克牌桌">
        <div className="poker-table-felt">
          <div className="poker-table-vignette" />
          <div className="poker-table-center">
            <PotDisplay amount={totalPot} pots={pots} />
            <CommunityCards cards={community_cards} />
            <div className="phase-badge">{PHASE_LABELS[phase] || phase}</div>
            <TurnTimer
              playerName={activePlayer?.display_name ?? ''}
              deadlineTs={timer?.deadlineTs}
              timeoutSeconds={timer?.timeoutSeconds}
            />
          </div>
        </div>

        {players.map((player) => {
          const pos = SEAT_POSITIONS[player.seat_index] || SEAT_POSITIONS[0];
          const isDealer = player.seat_index === dealer_index;
          const isActive = player.seat_index === active_player_index;
          const preservedHoleCards = player.hole_cards.length > 0
            ? player.hole_cards
            : holeCardCache.get(player.id) ?? [];

          return (
            <div
              key={player.id}
              className={`table-seat seat-index-${player.seat_index}`}
              style={{
                top: pos.top,
                left: pos.left,
                zIndex: isActive ? 12 : 3,
              }}
            >
              <PlayerSeat
                player={{ ...player, hole_cards: preservedHoleCards }}
                isDealer={isDealer}
                isActive={isActive}
                showCards={showCards}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

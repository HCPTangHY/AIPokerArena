import { useState } from 'react';
import type { GameStateData, HandHistoryItem } from '../types/game';
import { formatCard } from '../utils/cardUtils';

interface Props {
  gameState: GameStateData | null;
}

function buildBoard(hand: HandHistoryItem) {
  return [
    ...hand.flop_cards,
    ...(hand.turn_card ? [hand.turn_card] : []),
    ...(hand.river_card ? [hand.river_card] : []),
  ];
}

function formatDelta(value: number) {
  if (value > 0) return `+${value}`;
  if (value < 0) return `${value}`;
  return '0';
}

function buildSettlementPreview(hand: HandHistoryItem) {
  if (hand.settlement.length === 0) {
    return '无摊牌数据';
  }

  const topResult = [...hand.settlement].sort((a, b) => b.chip_change - a.chip_change)[0];
  return `${topResult.name} ${formatDelta(topResult.chip_change)}`;
}

export function HandHistoryPanel({ gameState }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const currentEvents = gameState?.events.slice(-8) ?? [];
  const recentHands = [...(gameState?.hand_history ?? [])].reverse();

  return (
    <div className={`history-panel ${collapsed ? 'is-collapsed' : ''}`}>
      <button
        type="button"
        className="history-title"
        onClick={() => setCollapsed((value) => !value)}
      >
        <span>对局历史</span>
        <small>{collapsed ? '展开' : '折叠'}</small>
      </button>

      {!collapsed && (
        <div className="history-scroll">
          <details className="history-section" open>
            <summary>
              <span>当前手牌</span>
              <small>{currentEvents.length} 条事件</small>
            </summary>
            <div className="history-section-body">
              {currentEvents.length === 0 ? (
                <p className="muted-copy">等待牌局动作...</p>
              ) : (
                currentEvents.map((event, index) => (
                  <div key={`${event.ts}-${index}`} className="event-item">
                    {event.text}
                  </div>
                ))
              )}
            </div>
          </details>

          <details className="history-section" open>
            <summary>
              <span>历史手牌</span>
              <small>{recentHands.length} 手</small>
            </summary>
            <div className="history-section-body">
              {recentHands.length === 0 ? (
                <p className="muted-copy">暂无已完成的手牌。</p>
              ) : (
                recentHands.map((hand) => {
                  const board = buildBoard(hand);
                  const settlementPreview = buildSettlementPreview(hand);

                  return (
                    <details key={hand.hand_number} className="hand-history-card">
                      <summary>
                        <div>
                          <strong>#{hand.hand_number}</strong>
                          <span>{board.length > 0 ? board.map(formatCard).join(' ') : '无公共牌'}</span>
                        </div>
                        <small>{settlementPreview}</small>
                      </summary>

                      <div className="hand-history-body">
                        {hand.actions.length > 0 && (
                          <div className="action-list">
                            {hand.actions.map((action, index) => (
                              <div key={`${action.player_id}-${index}`} className="action-row">
                                <span>{action.player_name}</span>
                                <strong>
                                  {action.action}
                                  {action.amount > 0 ? ` ${action.amount}` : ''}
                                </strong>
                              </div>
                            ))}
                          </div>
                        )}

                        {hand.settlement.length > 0 && (
                          <div className="settlement-list">
                            {hand.settlement
                              .slice()
                              .sort((a, b) => b.chip_change - a.chip_change)
                              .map((item) => (
                                <div key={item.player_id} className="settlement-row">
                                  <span>{item.name}</span>
                                  <strong className={item.chip_change >= 0 ? 'is-positive' : 'is-negative'}>
                                    {formatDelta(item.chip_change)}
                                  </strong>
                                  {item.revealed && item.cards.length > 0 && (
                                    <em>{item.cards.map(formatCard).join(' ')}</em>
                                  )}
                                </div>
                              ))}
                          </div>
                        )}
                      </div>
                    </details>
                  );
                })
              )}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

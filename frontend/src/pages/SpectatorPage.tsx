import { useEffect, useState, useRef, useCallback, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWebSocket } from '../hooks/useWebSocket';
import { useGameContext } from '../context/GameContext';
import { useAuthContext } from '../context/AuthContext';
import { PokerTable } from '../components/PokerTable';
import { ChatPanel } from '../components/ChatPanel';
import { ThinkingPanel } from '../components/ThinkingPanel';
import { DebugPanel } from '../components/DebugPanel';
import { HandHistoryPanel } from '../components/HandHistoryPanel';
import { TournamentStatus } from '../components/TournamentStatus';
import { api } from '../utils/api';
import { formatCard } from '../utils/cardUtils';
import type { ActiveThinking } from '../context/GameContext';
import type { ChatMessage, GameStateData, PlayerState, TournamentOverData } from '../types/game';

const HAND_RANKINGS = [
  { name: '皇家同花顺', example: '同花色的 A-K-Q-J-10' },
  { name: '同花顺', example: '同花色的五张连续牌' },
  { name: '四条', example: '四张同点数的牌' },
  { name: '葫芦', example: '三条加一对' },
  { name: '同花', example: '同花色五张不连续牌' },
  { name: '顺子', example: '不同花色的五张连续牌' },
  { name: '三条', example: '三张同点数的牌' },
  { name: '两对', example: '两个不同点数的对子' },
  { name: '一对', example: '两张同点数的牌' },
  { name: '高牌', example: '没有任何其他牌型时' },
];

const PHASE_LABELS: Record<string, string> = {
  pre_flop: '起手牌分析',
  flop: '公共牌面分析',
  turn: '转牌决策',
  river: '河牌决策',
  showdown: '摊牌结算',
};

const ICON_PATHS = {
  table: ['M4 10c0-3 3.6-5 8-5s8 2 8 5-3.6 5-8 5-8-2-8-5Z', 'M7 13v4m10-4v4'],
  chart: ['M5 19V9', 'M12 19V5', 'M19 19v-7'],
  history: ['M3 12a9 9 0 1 0 3-6.7', 'M3 4v5h5', 'M12 7v5l3 2'],
  info: ['M12 17v-6', 'M12 7h.01', 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z'],
  settings: ['M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z', 'M19.4 15a8 8 0 0 0 .1-2l2-1.2-2-3.5-2.3.7a8 8 0 0 0-1.7-1L15 5.6h-4L10.5 8a8 8 0 0 0-1.7 1l-2.3-.7-2 3.5 2 1.2a8 8 0 0 0 .1 2l-2 1.2 2 3.5 2.3-.7a8 8 0 0 0 1.7 1l.5 2.4h4l.5-2.4a8 8 0 0 0 1.7-1l2.3.7 2-3.5-2.2-1.2Z'],
  bug: ['M8 7V5a4 4 0 0 1 8 0v2', 'M6 12h12', 'M7 8h10v8a5 5 0 0 1-10 0V8Z', 'M3 9l3 2', 'M21 9l-3 2', 'M3 17l3-2', 'M21 17l-3-2'],
  eye: ['M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z'],
  play: ['M8 5v14l11-7-11-7Z'],
  stop: ['M6 6h12v12H6Z'],
  logout: ['M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4', 'M10 17l5-5-5-5', 'M15 12H3'],
  users: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z', 'M22 21v-2a4 4 0 0 0-3-3.9', 'M16 3.1a4 4 0 0 1 0 7.8'],
  spark: ['M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2Z'],
  trophy: ['M8 21h8', 'M12 17v4', 'M7 4h10v4a5 5 0 0 1-10 0V4Z', 'M5 5H3v2a3 3 0 0 0 4 2.8', 'M19 5h2v2a3 3 0 0 1-4 2.8'],
} as const;

type IconName = keyof typeof ICON_PATHS;
type DockTab = 'view' | 'analysis' | 'history';
type MobileView = 'table' | 'analysis' | 'thinking' | 'chat';

function ArenaIcon({ name }: { name: IconName }) {
  return (
    <svg className="arena-icon" viewBox="0 0 24 24" aria-hidden="true">
      {ICON_PATHS[name].map((path) => (
        <path key={path} d={path} />
      ))}
    </svg>
  );
}

function formatNumber(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '--';
  return value.toLocaleString('en-US');
}

function formatPercent(value: number) {
  return `${value.toFixed(value >= 10 ? 1 : 2)}%`;
}

function isSeated(player: PlayerState) {
  return !(player.chips === 0 && !player.is_active && !player.is_all_in);
}

function getActivePlayers(gameState: GameStateData | null) {
  return gameState?.players.filter(isSeated) ?? [];
}

function MatchInfoPanel({ gameState }: { gameState: GameStateData | null }) {
  const players = getActivePlayers(gameState);
  const totalChips = players.reduce((sum, player) => sum + player.chips, 0);
  const averageStack = players.length ? Math.round(totalChips / players.length) : null;
  const phase = gameState ? PHASE_LABELS[gameState.phase] ?? gameState.phase.replace('_', ' ') : '等待开局';

  return (
    <aside className="match-card" aria-label="当前对局信息">
      <h2>当前对局</h2>
      <dl>
        <div>
          <dt>对局 ID</dt>
          <dd>{gameState ? `#${gameState.tournament_id.slice(-6).toUpperCase()}` : '--'}</dd>
        </div>
        <div>
          <dt>游戏类型</dt>
          <dd>无限注德州扑克</dd>
        </div>
        <div>
          <dt>盲注级别</dt>
          <dd>
            {gameState
              ? `${gameState.small_blind} / ${gameState.big_blind}${gameState.ante ? ` (${gameState.ante} Ante)` : ''}`
              : '--'}
          </dd>
        </div>
        <div>
          <dt>对局阶段</dt>
          <dd>{phase}</dd>
        </div>
        <div>
          <dt>剩余玩家</dt>
          <dd>{gameState ? `${players.length} / ${gameState.players.length}` : '--'}</dd>
        </div>
        <div>
          <dt>平均筹码</dt>
          <dd>{formatNumber(averageStack)}</dd>
        </div>
        <div>
          <dt>你的身份</dt>
          <dd>观众模式</dd>
        </div>
      </dl>
    </aside>
  );
}

function AnalysisDock({
  gameState,
  dockTab,
  onDockTabChange,
}: {
  gameState: GameStateData | null;
  dockTab: DockTab;
  onDockTabChange: (tab: DockTab) => void;
}) {
  const players = getActivePlayers(gameState);
  const totalChips = players.reduce((sum, player) => sum + player.chips, 0);
  const totalPot = gameState?.pots.reduce((sum, pot) => sum + pot.amount, 0) ?? 0;
  const leader = [...players].sort((a, b) => b.chips - a.chips)[0];
  const board = gameState?.community_cards ?? [];
  const hasEquity = players.some((player) => player.equity != null);
  const equityRows = players
    .map((player) => ({
      id: player.id,
      name: player.display_name,
      value: player.equity ?? (totalChips > 0 ? (player.chips / totalChips) * 100 : 0),
      highlighted: gameState?.active_player_index === player.seat_index,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);

  return (
    <section className="analysis-dock">
      <div className="arena-tabbar" role="tablist" aria-label="观战信息切换">
        <button
          type="button"
          className={dockTab === 'view' ? 'is-active' : ''}
          onClick={() => onDockTabChange('view')}
        >
          观战视角
        </button>
        <button
          type="button"
          className={dockTab === 'analysis' ? 'is-active' : ''}
          onClick={() => onDockTabChange('analysis')}
        >
          数据分析
        </button>
        <button
          type="button"
          className={dockTab === 'history' ? 'is-active' : ''}
          onClick={() => onDockTabChange('history')}
        >
          历史对局
        </button>
      </div>

      {dockTab === 'history' ? (
        <div className="dock-history">
          <HandHistoryPanel gameState={gameState} />
        </div>
      ) : (
        <div className="analysis-grid">
          <div className="analysis-card">
            <div className="analysis-heading">
              <span>{hasEquity ? '胜率预测' : '筹码态势'}</span>
              <small>{hasEquity ? '基于可见信息' : '基于当前筹码'}</small>
            </div>
            <div className="equity-list">
              {equityRows.length === 0 ? (
                <p className="muted-copy">等待玩家入座...</p>
              ) : (
                equityRows.map((row) => (
                  <div key={row.id} className={`equity-chip ${row.highlighted ? 'is-active' : ''}`}>
                    <span>{row.name}</span>
                    <strong>{formatPercent(row.value)}</strong>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="analysis-card hand-readout">
            <div className="analysis-heading">
              <span>牌型分析</span>
              <small>{PHASE_LABELS[gameState?.phase ?? ''] ?? '等待牌面'}</small>
            </div>
            <div className="board-readout">
              {board.length > 0 ? (
                board.map((card) => <span key={card}>{formatCard(card)}</span>)
              ) : (
                <span className="board-placeholder">公共牌尚未发出</span>
              )}
            </div>
            <div className="analysis-metrics">
              <div>
                <span>底池</span>
                <strong>{formatNumber(totalPot)}</strong>
              </div>
              <div>
                <span>当前下注</span>
                <strong>{formatNumber(gameState?.current_bet)}</strong>
              </div>
              <div>
                <span>筹码领先</span>
                <strong>{leader?.display_name ?? '--'}</strong>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function MobileTableThinking({
  thinkingMessages,
  activeThinking,
}: {
  thinkingMessages: ChatMessage[];
  activeThinking: ActiveThinking | null;
}) {
  const bodyRef = useRef<HTMLParagraphElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const latestThinking = thinkingMessages[thinkingMessages.length - 1];
  const playerName = activeThinking?.player_name ?? latestThinking?.player_name ?? 'AI 思考';
  const text = activeThinking?.text ?? latestThinking?.message ?? '等待下一次 AI 决策...';

  useEffect(() => {
    const node = bodyRef.current;
    if (!node || !shouldAutoScrollRef.current) return;
    node.scrollTop = node.scrollHeight;
  }, [text]);

  const handleScroll = () => {
    const node = bodyRef.current;
    if (!node) return;
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 24;
  };

  return (
    <section className={`mobile-table-feed mobile-table-thinking ${activeThinking ? 'is-live' : ''}`}>
      <div className="mobile-feed-head">
        <span>{activeThinking ? '正在思考' : '最近思考'}</span>
        <strong>{playerName}</strong>
      </div>
      <p ref={bodyRef} onScroll={handleScroll}>{text}</p>
    </section>
  );
}

function anonymizeChatName(_name: string, seed: string) {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = ((hash << 5) - hash + seed.charCodeAt(i)) | 0;
  }
  return `观众${Math.abs(hash % 999)}`;
}

function MobileTableChat({
  messages,
  onSend,
  hideNames,
}: {
  messages: ChatMessage[];
  onSend: (message: string) => void;
  hideNames?: boolean;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const [input, setInput] = useState('');

  useEffect(() => {
    const node = listRef.current;
    if (!node || !shouldAutoScrollRef.current) return;
    node.scrollTop = node.scrollHeight;
  }, [messages.length]);

  const handleScroll = () => {
    const node = listRef.current;
    if (!node) return;
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 24;
  };

  const submit = () => {
    const text = input.trim();
    if (!text) return;
    onSend(text);
    setInput('');
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      submit();
    }
  };

  return (
    <section className="mobile-table-feed mobile-table-chat">
      <div className="mobile-feed-head">
        <span>观众聊天</span>
        <strong>{messages.length.toLocaleString('en-US')} 条</strong>
      </div>
      <div ref={listRef} className="mobile-chat-snippets" onScroll={handleScroll}>
        {messages.length === 0 ? (
          <p className="mobile-empty-copy">暂无聊天，发一句开场。</p>
        ) : (
          messages.slice(-20).map((message, index) => (
            <article className="mobile-chat-snippet" key={`${message.player_id}-${message.timestamp}-${index}`}>
              <strong>{hideNames ? anonymizeChatName(message.player_name, message.player_id) : message.player_name}</strong>
              <span>{message.message}</span>
            </article>
          ))
        )}
      </div>
      <div className="mobile-table-chat-input">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="发到观众聊天..."
        />
        <button type="button" onClick={submit}>发送</button>
      </div>
    </section>
  );
}

function RulesModal({ gameState, onClose }: { gameState: GameStateData | null; onClose: () => void }) {
  return (
    <div className="arena-modal-backdrop" onClick={onClose}>
      <section className="arena-modal" onClick={(event) => event.stopPropagation()} aria-modal="true" role="dialog">
        <div className="arena-modal-head">
          <div>
            <span className="modal-kicker">AI 介绍</span>
            <h2>锦标赛规则</h2>
          </div>
          <button type="button" className="arena-text-button" onClick={onClose}>关闭</button>
        </div>

        <div className="arena-modal-body">
          <p className="rules-intro">无限注德州扑克。所有 AI 玩家会根据自身模型策略、公共牌面、筹码量和历史行动做出决策，最后持有筹码的玩家赢得锦标赛。</p>

          <ul className="rules-list">
            <li>每位玩家发 2 张手牌。翻牌、转牌、河牌共揭示最多 5 张公共牌。</li>
            <li>下注动作包括：弃牌、过牌、跟注、加注、全下。</li>
            <li>多人进入摊牌时，最佳 5 张牌组合获胜。</li>
            <li>盲注根据锦标赛配置随时间递增，可开启前注。</li>
            <li>除一人外全部弃牌时，该玩家立即赢得底池。</li>
            <li>全下后无人可继续下注时，系统自动发完公共牌并进入摊牌。</li>
          </ul>

          <div className="hand-rank-grid">
            {HAND_RANKINGS.map((rank, index) => (
              <div key={rank.name} className="hand-rank-item">
                <span>{index + 1}</span>
                <div>
                  <strong>{rank.name}</strong>
                  <small>{rank.example}</small>
                </div>
              </div>
            ))}
          </div>

          <div className="rules-meta">
            <div>
              <span>当前盲注</span>
              <strong>{gameState ? `${gameState.small_blind}/${gameState.big_blind}` : '等待中...'}</strong>
            </div>
            <div>
              <span>前注</span>
              <strong>{gameState?.ante ? gameState.ante : '关闭'}</strong>
            </div>
            <div>
              <span>阶段</span>
              <strong>{gameState ? gameState.phase.replace('_', ' ') : '空闲'}</strong>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function StandingsModal({
  gameState,
  winner,
  onClose,
}: {
  gameState: GameStateData | null;
  winner: TournamentOverData | null;
  onClose: () => void;
}) {
  const standings = winner?.standings.map((item) => ({
    id: item.player_id,
    name: item.display_name,
    chips: item.chips,
    position: item.position,
  })) ?? [...getActivePlayers(gameState)]
    .sort((a, b) => b.chips - a.chips)
    .map((player, index) => ({
      id: player.id,
      name: player.display_name,
      chips: player.chips,
      position: index + 1,
    }));

  return (
    <div className="arena-modal-backdrop" onClick={onClose}>
      <section className="arena-modal standings-modal" onClick={(event) => event.stopPropagation()} aria-modal="true" role="dialog">
        <div className="arena-modal-head">
          <div>
            <span className="modal-kicker">Leaderboard</span>
            <h2>排行榜</h2>
          </div>
          <button type="button" className="arena-text-button" onClick={onClose}>关闭</button>
        </div>
        <div className="standings-list">
          {standings.length === 0 ? (
            <p className="muted-copy">暂无排名数据。</p>
          ) : (
            standings.map((item) => (
              <div key={item.id} className="standing-row">
                <span>#{item.position}</span>
                <strong>{item.name}</strong>
                <em>{formatNumber(item.chips)}</em>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

export function SpectatorPage() {
  const { logout, user, isAdmin } = useAuthContext();
  const {
    gameState,
    chatMessages,
    tournamentStatus,
    winner,
    activeThinking,
    debugPrompts,
    spectatorCount,
    handleWSMessage,
    setIsConnected,
    reset,
  } = useGameContext();
  const [showDebug, setShowDebug] = useState(false);
  const [showAllCards, setShowAllCards] = useState(false);
  const [hideChatNames, setHideChatNames] = useState(false);
  const [showRules, setShowRules] = useState(false);
  const [showStandings, setShowStandings] = useState(false);
  const [dockTab, setDockTab] = useState<DockTab>('view');
  const [mobileView, setMobileView] = useState<MobileView>('table');

  const thinkingMessages = chatMessages.filter((message) => message.is_thinking);
  const spectatorMessages = chatMessages.filter((message) => message.is_spectator);
  const wsRef = useRef<WebSocket | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.getTournamentStatus().then((data) => {
      void data;
    });
  }, []);

  const { isConnected, reconnectAttempt } = useWebSocket(null, {
    onMessage: handleWSMessage,
    onConnect: () => setIsConnected(true),
    onDisconnect: () => setIsConnected(false),
    enabled: true,
    wsRef,
  });

  const sendChat = useCallback((message: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'chat', message }));
    }
  }, []);

  const handleStartTournament = async () => {
    try {
      reset();
      await api.startTournament();
    } catch (error) {
      alert('启动锦标赛失败：' + (error as Error).message);
    }
  };

  const handleStopTournament = async () => {
    try {
      await api.stopTournament();
      reset();
    } catch (error) {
      alert('停止锦标赛失败：' + (error as Error).message);
    }
  };

  const statusText = tournamentStatus === 'running'
    ? '正在对局'
    : tournamentStatus === 'finished'
      ? '锦标赛结束'
      : '等待开局';
  const activePlayer = gameState?.active_player_index == null
    ? null
    : gameState.players.find((player) => player.seat_index === gameState.active_player_index)
      ?? gameState.players[gameState.active_player_index]
      ?? null;
  const displayName = user?.global_name || user?.username || '观众';

  return (
    <div className="spectator-page arena-page">
      <header className="arena-topbar">
        <div className="arena-brand">
          <div className="arena-brand-mark" aria-hidden="true">
            <ArenaIcon name="spark" />
          </div>
          <div>
            <h1>AI 德州扑克竞技场</h1>
            <p>智能对决 · 策略至上</p>
          </div>
        </div>

        <nav className="arena-nav" aria-label="竞技场导航">
          <button type="button" className="arena-nav-btn is-active" onClick={() => setDockTab('view')}>
            <ArenaIcon name="table" />
            竞技场
          </button>
          <button type="button" className="arena-nav-btn" onClick={() => setShowStandings(true)}>
            <ArenaIcon name="chart" />
            排行榜
          </button>
          <button type="button" className="arena-nav-btn" onClick={() => setDockTab('history')}>
            <ArenaIcon name="history" />
            历史对局
          </button>
          <button type="button" className="arena-nav-btn" onClick={() => setShowRules(true)}>
            <ArenaIcon name="info" />
            AI 介绍
          </button>
        </nav>

        <div className="arena-actions">
          <div className="arena-live-pill">
            <TournamentStatus
              status={tournamentStatus}
              gameState={gameState}
              isConnected={isConnected}
              reconnectAttempt={reconnectAttempt}
            />
          </div>
          <button
            type="button"
            className="arena-icon-button mobile-only-action"
            onClick={() => setShowStandings(true)}
            title="排行榜"
            aria-label="排行榜"
          >
            <ArenaIcon name="chart" />
          </button>
          <button
            type="button"
            className="arena-icon-button mobile-only-action"
            onClick={() => setShowRules(true)}
            title="AI 介绍"
            aria-label="AI 介绍"
          >
            <ArenaIcon name="info" />
          </button>

          {isAdmin && tournamentStatus !== 'running' && (
            <button type="button" className="arena-icon-button is-success" onClick={handleStartTournament} title="开始锦标赛" aria-label="开始锦标赛">
              <ArenaIcon name="play" />
            </button>
          )}
          {isAdmin && tournamentStatus === 'running' && (
            <button type="button" className="arena-icon-button is-danger" onClick={handleStopTournament} title="停止锦标赛" aria-label="停止锦标赛">
              <ArenaIcon name="stop" />
            </button>
          )}
          {isAdmin && (
            <button type="button" className="arena-icon-button" onClick={() => navigate('/config')} title="配置" aria-label="配置">
              <ArenaIcon name="settings" />
            </button>
          )}
          {isAdmin && (
            <button
              type="button"
              className={`arena-icon-button ${showDebug ? 'is-active' : ''}`}
              onClick={() => setShowDebug((value) => !value)}
              title="调试"
              aria-label="调试"
            >
              <ArenaIcon name="bug" />
            </button>
          )}
          <button
            type="button"
            className={`arena-icon-button ${showAllCards ? 'is-active' : ''}`}
            onClick={() => setShowAllCards((value) => !value)}
            title={showAllCards ? '隐藏手牌' : '显示手牌'}
            aria-label={showAllCards ? '隐藏手牌' : '显示手牌'}
          >
            <ArenaIcon name="eye" />
          </button>
          <div className="viewer-pill" title="当前观众数">
            <ArenaIcon name="users" />
            <span>观众 {formatNumber(spectatorCount)}</span>
          </div>
          <button type="button" className="follow-pill" onClick={() => setShowAllCards((value) => !value)}>
            {showAllCards ? '隐藏' : '亮牌'}
          </button>
          <button type="button" className="follow-pill" onClick={() => setHideChatNames((value) => !value)}>
            {hideChatNames ? '显示昵称' : '匿名聊天'}
          </button>
          <button type="button" className="arena-icon-button" onClick={logout} title={`退出 ${displayName}`} aria-label="退出">
            <ArenaIcon name="logout" />
          </button>
        </div>
      </header>

      <main className={`arena-main mobile-view-${mobileView} ${showDebug ? 'has-debug' : ''}`}>
        <section className="arena-table-section">
          <div className="arena-stage-card">
            <MatchInfoPanel gameState={gameState} />
            <div className="arena-status-strip">
              <span>{statusText}</span>
              {activePlayer && <strong>{activePlayer.display_name} 正在行动</strong>}
            </div>
            <MobileTableThinking thinkingMessages={thinkingMessages} activeThinking={activeThinking} />
            {gameState ? (
              <PokerTable gameState={gameState} showCards={showAllCards} />
            ) : (
              <div className="arena-empty-state">
                <ArenaIcon name="trophy" />
                <h2>
                  {tournamentStatus === 'finished'
                    ? '锦标赛结束'
                    : tournamentStatus === 'idle'
                      ? '等待锦标赛开局'
                      : '连接牌桌中'}
                </h2>
                <p>
                  {tournamentStatus === 'idle'
                    ? isAdmin
                      ? '点击开始按钮创建新的 AI 对局。'
                      : '等待管理员开始新的 AI 对局。'
                    : '牌桌状态会在这里实时同步。'}
                </p>
                {winner && <strong className="winner-banner">冠军：{winner.winner_name}</strong>}
                {isAdmin && tournamentStatus !== 'running' && (
                  <button type="button" className="arena-primary-button" onClick={handleStartTournament}>
                    开始锦标赛
                  </button>
                )}
              </div>
            )}
            <MobileTableChat messages={spectatorMessages} onSend={sendChat} hideNames={hideChatNames} />
          </div>

          <AnalysisDock gameState={gameState} dockTab={dockTab} onDockTabChange={setDockTab} />
        </section>

        <aside className="arena-side-rail">
          <section className="spectator-panel spectator-thinking">
            <ThinkingPanel thinkingMessages={thinkingMessages} activeThinking={activeThinking} />
          </section>
          <section className="spectator-panel spectator-chat">
            <ChatPanel messages={spectatorMessages} onSend={sendChat} hideNames={hideChatNames} />
          </section>
        </aside>

        {showDebug && (
          <aside className="arena-debug spectator-debug">
            <DebugPanel prompts={debugPrompts} />
          </aside>
        )}
      </main>

      <nav className="mobile-tabbar" aria-label="移动端视图切换">
        <button
          type="button"
          className={mobileView === 'table' ? 'is-active' : ''}
          onClick={() => setMobileView('table')}
        >
          <ArenaIcon name="table" />
          <span>牌桌</span>
        </button>
        <button
          type="button"
          className={mobileView === 'analysis' ? 'is-active' : ''}
          onClick={() => {
            setDockTab('analysis');
            setMobileView('analysis');
          }}
        >
          <ArenaIcon name="chart" />
          <span>数据</span>
        </button>
        <button
          type="button"
          className={mobileView === 'thinking' ? 'is-active' : ''}
          onClick={() => setMobileView('thinking')}
        >
          <ArenaIcon name="spark" />
          <span>思考</span>
        </button>
        <button
          type="button"
          className={mobileView === 'chat' ? 'is-active' : ''}
          onClick={() => setMobileView('chat')}
        >
          <ArenaIcon name="users" />
          <span>聊天</span>
        </button>
      </nav>

      <footer className="arena-footer">
        <span>技术驱动的公平竞技环境</span>
        <span className={isConnected ? 'is-online' : 'is-offline'}>
          {isConnected ? 'AI 模型运行正常' : '连接中断'}
        </span>
        <span>服务器延迟：实时同步</span>
        <span>对局公平性：100%</span>
        <span>版本 v2.1.0</span>
      </footer>

      {showRules && <RulesModal gameState={gameState} onClose={() => setShowRules(false)} />}
      {showStandings && (
        <StandingsModal
          gameState={gameState}
          winner={winner}
          onClose={() => setShowStandings(false)}
        />
      )}
    </div>
  );
}

import { useEffect, useRef, useCallback, useState, type MutableRefObject } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWerewolfContext } from '../context/WerewolfContext';
import { useAuthContext } from '../context/AuthContext';
import { PhaseBanner } from '../components/werewolf/PhaseBanner';
import { VoteTracker } from '../components/werewolf/VoteTracker';
import { ThinkingPanel } from '../components/ThinkingPanel';
import { ChatPanel } from '../components/ChatPanel';
import { DebugPanel } from '../components/DebugPanel';
import type { WerewolfPlayer } from '../types/werewolf';

const WEREWOLF_WS_PATH = '/werewolf/ws/spectate';
const API_BASE = '/werewolf';

const ICON_PATHS = {
  moon: ['M21 12.8A8.5 8.5 0 1 1 11.2 3 6.5 6.5 0 0 0 21 12.8Z'],
  chart: ['M5 19V9', 'M12 19V5', 'M19 19v-7'],
  spark: ['M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2Z'],
  play: ['M8 5v14l11-7-11-7Z'],
  stop: ['M6 6h12v12H6Z'],
  settings: ['M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z', 'M19.4 15a8 8 0 0 0 .1-2l2-1.2-2-3.5-2.3.7a8 8 0 0 0-1.7-1L15 5.6h-4L10.5 8a8 8 0 0 0-1.7 1l-2.3-.7-2 3.5 2 1.2a8 8 0 0 0 .1 2l-2 1.2 2 3.5 2.3-.7a8 8 0 0 0 1.7 1l.5 2.4h4l.5-2.4a8 8 0 0 0 1.7-1l2.3.7 2-3.5-2.2-1.2Z'],
  bug: ['M8 2l1.8 2h4.4L16 2', 'M12 4v17', 'M5 8h14', 'M7 8v5a5 5 0 0 0 10 0V8', 'M3 13h4', 'M17 13h4', 'M4 19l3-3', 'M20 19l-3-3'],
  users: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z', 'M22 21v-2a4 4 0 0 0-3-3.9', 'M16 3.1a4 4 0 0 1 0 7.8'],
  logout: ['M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4', 'M10 17l5-5-5-5', 'M15 12H3'],
} as const;

type IconName = keyof typeof ICON_PATHS;
type MobileView = 'table' | 'analysis' | 'thinking' | 'chat';
type PlayerRailSide = 'left' | 'right' | 'mobile';

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

function phaseText(phase?: string) {
  const labels: Record<string, string> = {
    role_assign: '角色分配',
    sheriff_election: '上警竞选',
    night: '夜晚行动',
    day: '白天发言',
    vote: '放逐投票',
    game_over: '游戏结束',
  };
  return labels[phase || ''] || '等待开局';
}

function roleText(player: WerewolfPlayer, showRoles: boolean) {
  if (!showRoles && player.is_alive) return '身份隐藏';
  return player.spectator_role_name || player.role_name || '未知身份';
}

function teamClass(player: WerewolfPlayer, showRoles: boolean) {
  const team = showRoles || !player.is_alive ? (player.spectator_team || player.team) : null;
  return team ? `team-${team}` : 'team-hidden';
}

function playerStateText(player: WerewolfPlayer) {
  if (!player.is_alive) return player.death_cause ? `出局 · ${player.death_cause}` : '已出局';
  if (player.has_voted) return '已投票';
  return '存活';
}

function PlayerRail({
  players,
  side,
  showRoles,
  currentSpeaker,
  sheriffId,
}: {
  players: WerewolfPlayer[];
  side: PlayerRailSide;
  showRoles: boolean;
  currentSpeaker: string | null;
  sheriffId: string | null;
}) {
  return (
    <div className={`werewolf-seat-rail is-${side}`}>
      {players.map((player) => (
        <article
          key={player.id}
          className={[
            'werewolf-seat-card',
            player.is_alive ? 'is-alive' : 'is-dead',
            currentSpeaker === player.id ? 'is-speaking' : '',
            player.id === sheriffId ? 'is-sheriff' : '',
            teamClass(player, showRoles),
          ].filter(Boolean).join(' ')}
        >
          <div className="werewolf-seat-avatar">
            {player.avatar_url ? <img src={player.avatar_url} alt="" /> : <span>{player.display_name.slice(0, 1)}</span>}
            <em>{player.seat_index + 1}</em>
          </div>
          <div className="werewolf-seat-body">
            <strong>{player.display_name}</strong>
            <span>{roleText(player, showRoles)}</span>
          </div>
          {player.id === sheriffId && <b>警</b>}
        </article>
      ))}
    </div>
  );
}

function PlayerOverview({
  players,
  showRoles,
  currentSpeaker,
  sheriffId,
}: {
  players: WerewolfPlayer[];
  showRoles: boolean;
  currentSpeaker: string | null;
  sheriffId: string | null;
}) {
  if (players.length === 0) {
    return (
      <section className="werewolf-roster-panel">
        <div className="werewolf-panel-heading">
          <div>
            <h2>玩家状态</h2>
            <span>等待玩家入场</span>
          </div>
        </div>
        <p className="werewolf-mobile-empty">开局后这里会显示所有玩家的生存、身份和发言状态。</p>
      </section>
    );
  }

  return (
    <section className="werewolf-roster-panel">
      <div className="werewolf-panel-heading">
        <div>
          <h2>玩家状态</h2>
          <span>{players.filter((player) => player.is_alive).length} / {players.length} 存活</span>
        </div>
      </div>
      <div className="werewolf-roster-list">
        {players.map((player) => (
          <article
            key={player.id}
            className={[
              'werewolf-roster-card',
              player.is_alive ? 'is-alive' : 'is-dead',
              currentSpeaker === player.id ? 'is-speaking' : '',
              player.id === sheriffId ? 'is-sheriff' : '',
              teamClass(player, showRoles),
            ].filter(Boolean).join(' ')}
          >
            <div className="werewolf-roster-avatar">
              {player.avatar_url ? <img src={player.avatar_url} alt="" /> : <span>{player.display_name.slice(0, 1)}</span>}
              <em>{player.seat_index + 1}</em>
            </div>
            <div className="werewolf-roster-main">
              <strong>{player.display_name}</strong>
              <span>{roleText(player, showRoles)}</span>
            </div>
            <div className="werewolf-roster-meta">
              {player.id === sheriffId && <b>警长</b>}
              {currentSpeaker === player.id && <b className="is-live">发言中</b>}
              <small>{playerStateText(player)}</small>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function WerewolfPage() {
  const {
    gameState, chatMessages, tournamentStatus, winner,
    isConnected, spectatorCount, activeThinking, debugPrompts,
    handleWSMessage, setIsConnected,
  } = useWerewolfContext();

  const { user, isAdmin, logout } = useAuthContext();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const reconnectAttemptsRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const handleWSMessageRef = useRef(handleWSMessage);
  const connectRef = useRef<() => void>(() => undefined);
  const [mobileView, setMobileView] = useState<MobileView>('table');
  const [showRoles, setShowRoles] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    handleWSMessageRef.current = handleWSMessage;
  }, [handleWSMessage]);

  const connect = useCallback(() => {
    const token = localStorage.getItem('token');
    if (!token) return;
    if (
      wsRef.current?.readyState === WebSocket.OPEN
      || wsRef.current?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }
    shouldReconnectRef.current = true;

    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${WEREWOLF_WS_PATH}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      reconnectAttemptsRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        handleWSMessageRef.current(JSON.parse(event.data));
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
      if (!shouldReconnectRef.current) return;
      const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 10000);
      reconnectAttemptsRef.current++;
      reconnectTimerRef.current = setTimeout(() => connectRef.current(), delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [setIsConnected]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();
    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.onmessage = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const sendChat = useCallback((message: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'chat', message }));
    }
  }, []);

  const startTournament = async () => {
    const token = localStorage.getItem('token');
    const res = await fetch(`${API_BASE}/api/tournament/start?game_type=werewolf`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      alert('启动狼人杀失败：' + (err.detail || res.statusText));
    }
  };

  const stopTournament = async () => {
    const token = localStorage.getItem('token');
    const res = await fetch(`${API_BASE}/api/tournament/stop?game_type=werewolf`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      alert('停止狼人杀失败：' + (err.detail || res.statusText));
    }
  };

  const players = gameState?.players || [];
  const leftPlayers = players.slice(0, Math.ceil(players.length / 2));
  const rightPlayers = players.slice(Math.ceil(players.length / 2));
  const alivePlayers = players.filter((player) => player.is_alive);
  const thinkingMessages = chatMessages.filter((message) => message.is_thinking);
  const spectatorMessages = chatMessages.filter((message) => message.is_spectator);
  const visibleEvents = (gameState?.events || []).filter((event) => !event.hidden);
  const latestVisibleEvent = visibleEvents[visibleEvents.length - 1]?.text || '';
  const centerFeedRef = useRef<HTMLDivElement>(null);
  const mobileEventFeedRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollCenterRef = useRef(true);
  const shouldAutoScrollMobileEventsRef = useRef(true);
  const sheriffPlayer = players.find((player) => player.id === gameState?.sheriff_id);
  const currentSpeaker = players.find((player) => player.id === gameState?.current_speaker);
  const displayName = user?.global_name || user?.username || '观众';
  const statusText = tournamentStatus === 'running'
    ? phaseText(gameState?.phase)
    : tournamentStatus === 'finished'
      ? '游戏结束'
      : '等待开局';
  const navButtonClass = (view: MobileView) => `arena-nav-btn ${mobileView === view ? 'is-active' : ''}`;

  useEffect(() => {
    requestAnimationFrame(() => {
      const centerFeed = centerFeedRef.current;
      const mobileFeed = mobileEventFeedRef.current;
      if (centerFeed && shouldAutoScrollCenterRef.current) {
        centerFeed.scrollTop = centerFeed.scrollHeight;
      }
      if (mobileFeed && shouldAutoScrollMobileEventsRef.current) {
        mobileFeed.scrollTop = mobileFeed.scrollHeight;
      }
    });
  }, [visibleEvents.length, latestVisibleEvent]);

  const updateAutoScrollIntent = (
    node: HTMLDivElement | null,
    intentRef: MutableRefObject<boolean>,
  ) => {
    if (!node) return;
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
    intentRef.current = distanceFromBottom < 56;
  };

  const handleCenterFeedScroll = () => {
    updateAutoScrollIntent(centerFeedRef.current, shouldAutoScrollCenterRef);
  };

  const handleMobileEventFeedScroll = () => {
    updateAutoScrollIntent(mobileEventFeedRef.current, shouldAutoScrollMobileEventsRef);
  };

  return (
    <div className="spectator-page arena-page werewolf-arena-page">
      <header className="arena-topbar">
        <div className="arena-brand">
          <div className="arena-brand-mark" aria-hidden="true">
            <ArenaIcon name="moon" />
          </div>
          <div>
            <h1>AI 狼人杀竞技场</h1>
            <p>推理发言 · 阵营博弈</p>
          </div>
        </div>

        <nav className="arena-nav" aria-label="狼人杀导航">
          <button type="button" className={navButtonClass('table')} onClick={() => setMobileView('table')}>
            <ArenaIcon name="moon" />
            圆桌
          </button>
          <button type="button" className={navButtonClass('analysis')} onClick={() => setMobileView('analysis')}>
            <ArenaIcon name="chart" />
            票型
          </button>
          <button type="button" className={navButtonClass('thinking')} onClick={() => setMobileView('thinking')}>
            <ArenaIcon name="spark" />
            思考
          </button>
        </nav>

        <div className="arena-actions">
          <div className="arena-live-pill">
            <span className={isConnected ? 'is-online' : 'is-offline'}>
              {isConnected ? '实时连接' : '连接中断'}
            </span>
            <strong>{statusText}</strong>
          </div>
          {isAdmin && tournamentStatus !== 'running' && (
            <button type="button" className="arena-icon-button is-success" onClick={startTournament} title="开始游戏" aria-label="开始游戏">
              <ArenaIcon name="play" />
            </button>
          )}
          {isAdmin && tournamentStatus === 'running' && (
            <button type="button" className="arena-icon-button is-danger" onClick={stopTournament} title="停止游戏" aria-label="停止游戏">
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
          <div className="viewer-pill" title="当前观众数">
            <ArenaIcon name="users" />
            <span>观众 {formatNumber(spectatorCount)}</span>
          </div>
          <button type="button" className={`follow-pill ${showRoles ? 'is-active' : ''}`} onClick={() => setShowRoles((value) => !value)}>
            {showRoles ? '隐藏身份' : '显示身份'}
          </button>
          <button type="button" className="arena-icon-button" onClick={logout} title={`退出 ${displayName}`} aria-label="退出">
            <ArenaIcon name="logout" />
          </button>
        </div>
      </header>

      <main className={`arena-main werewolf-arena-main mobile-view-${mobileView} ${showDebug ? 'has-debug' : ''}`}>
        <section className="arena-table-section">
          <div className="arena-stage-card werewolf-stage-card">
            <PhaseBanner
              phase={gameState?.phase || 'role_assign'}
              roundNumber={gameState?.round_number || 0}
            />
            <div className="arena-status-strip">
              <span>{statusText}</span>
              <strong>{gameState ? `${alivePlayers.length} / ${players.length} 存活` : '等待玩家入场'}</strong>
            </div>
            {tournamentStatus === 'finished' && winner && (
              <div className="winner-banner">胜利阵营：{winner.winner_name}</div>
            )}
            {gameState && (
              <>
                <section className="werewolf-mobile-summary" aria-label="当前局势">
                  <div>
                    <span>阶段</span>
                    <strong>{statusText}</strong>
                  </div>
                  <div>
                    <span>发言</span>
                    <strong>{currentSpeaker?.display_name || '等待中'}</strong>
                  </div>
                  <div>
                    <span>警长</span>
                    <strong>{sheriffPlayer?.display_name || '未产生'}</strong>
                  </div>
                </section>
                <section className="werewolf-player-strip" aria-label="玩家横向列表">
                  <PlayerRail
                    players={players}
                    side="mobile"
                    showRoles={showRoles}
                    currentSpeaker={gameState.current_speaker || null}
                    sheriffId={gameState.sheriff_id || null}
                  />
                </section>
              </>
            )}
            {gameState ? (
              <div className="werewolf-room-board">
                <PlayerRail
                  players={leftPlayers}
                  side="left"
                  showRoles={showRoles}
                  currentSpeaker={gameState.current_speaker || null}
                  sheriffId={gameState.sheriff_id || null}
                />
                <section className="werewolf-room-center">
                  <div className="werewolf-corner-status">
                    <strong>第 {gameState.round_number} 天</strong>
                    <span>{statusText}</span>
                  </div>
                  <div ref={centerFeedRef} className="werewolf-center-feed" onScroll={handleCenterFeedScroll}>
                    {visibleEvents.slice(-20).map((event, index) => (
                      <article key={`${event.text}-${index}`}>
                        <span>{index + 1}</span>
                        <p>{event.text}</p>
                      </article>
                    ))}
                  </div>
                  <div className="werewolf-center-panels">
                    <VoteTracker gameState={gameState} players={players} />
                  </div>
                </section>
                <PlayerRail
                  players={rightPlayers}
                  side="right"
                  showRoles={showRoles}
                  currentSpeaker={gameState.current_speaker || null}
                  sheriffId={gameState.sheriff_id || null}
                />
              </div>
            ) : (
              <div className="arena-empty-state werewolf-empty-state">
                <ArenaIcon name="moon" />
                <h2>{tournamentStatus === 'idle' ? '等待狼人杀开局' : '连接圆桌中'}</h2>
                <p>{isAdmin ? '点击开始按钮创建新的 AI 狼人杀对局。' : '等待管理员开启新的 AI 狼人杀对局。'}</p>
                {isAdmin && tournamentStatus !== 'running' && (
                  <button type="button" className="arena-primary-button" onClick={startTournament}>
                    开始游戏
                  </button>
                )}
              </div>
            )}
            <section className="mobile-table-feed werewolf-mobile-events">
              <div className="mobile-feed-head">
                <span>公开事件</span>
                <strong>{visibleEvents.length}</strong>
              </div>
              <div ref={mobileEventFeedRef} className="werewolf-event-list" onScroll={handleMobileEventFeedScroll}>
                {visibleEvents.slice(-6).map((event, index) => (
                  <p key={`${event.text}-${index}`}>{event.text}</p>
                ))}
              </div>
            </section>
          </div>

        </section>

        <section className="spectator-panel werewolf-mobile-panel werewolf-analysis-panel" aria-label="票型与玩家状态">
          <div className="panel-title-row">
            <div>
              <h2>票型与玩家</h2>
              <span>{gameState ? `${alivePlayers.length} / ${players.length} 存活` : '等待开局'}</span>
            </div>
            <span className="panel-select">{statusText}</span>
          </div>
          <div className="werewolf-analysis-scroll">
            <VoteTracker gameState={gameState} players={players} showEmpty />
            <PlayerOverview
              players={players}
              showRoles={showRoles}
              currentSpeaker={gameState?.current_speaker || null}
              sheriffId={gameState?.sheriff_id || null}
            />
          </div>
        </section>

        <aside className="arena-side-rail">
          <section className="spectator-panel spectator-thinking">
            <ThinkingPanel thinkingMessages={thinkingMessages} activeThinking={activeThinking} />
          </section>
          <section className="spectator-panel spectator-chat">
            <ChatPanel messages={spectatorMessages} onSend={sendChat} />
          </section>
        </aside>

        {showDebug && (
          <aside className="arena-debug spectator-debug">
            <DebugPanel prompts={debugPrompts} />
          </aside>
        )}
      </main>

      <nav className="mobile-tabbar" aria-label="移动端视图切换">
        <button type="button" className={mobileView === 'table' ? 'is-active' : ''} onClick={() => setMobileView('table')}>
          <ArenaIcon name="moon" />
          <span>圆桌</span>
        </button>
        <button type="button" className={mobileView === 'analysis' ? 'is-active' : ''} onClick={() => setMobileView('analysis')}>
          <ArenaIcon name="chart" />
          <span>票型</span>
        </button>
        <button type="button" className={mobileView === 'thinking' ? 'is-active' : ''} onClick={() => setMobileView('thinking')}>
          <ArenaIcon name="spark" />
          <span>思考</span>
        </button>
        <button type="button" className={mobileView === 'chat' ? 'is-active' : ''} onClick={() => setMobileView('chat')}>
          <ArenaIcon name="users" />
          <span>聊天</span>
        </button>
      </nav>
    </div>
  );
}

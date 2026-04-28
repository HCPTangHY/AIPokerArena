/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useCallback, useRef, type MutableRefObject, type ReactNode } from 'react';
import type {
  GameStateData,
  ChatMessage,
  WSMessage,
  TournamentOverData,
  DebugPrompt,
  HistorySnapshotData,
} from '../types/game';

export interface ActiveThinking {
  player_id: string;
  player_name: string;
  text: string;
}

interface GameContextValue {
  gameState: GameStateData | null;
  chatMessages: ChatMessage[];
  tournamentStatus: 'idle' | 'running' | 'finished';
  winner: TournamentOverData | null;
  isConnected: boolean;
  spectatorCount: number;
  activeThinking: ActiveThinking | null;
  debugPrompts: DebugPrompt[];
  handleWSMessage: (msg: WSMessage) => void;
  setIsConnected: (v: boolean) => void;
  reset: () => void;
}

const GameContext = createContext<GameContextValue | null>(null);

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function readString(value: unknown) {
  if (typeof value === 'string') return value;
  if (value == null) return '';
  return String(value);
}

function readBoolean(value: unknown) {
  return value === true || value === 'true' || value === 1 || value === '1';
}

function readThinkingChunkPayload(msg: WSMessage) {
  const root = toRecord(msg);
  const data = toRecord(root.data);
  return {
    player_id: readString(root.player_id ?? data.player_id),
    player_name: readString(root.player_name ?? data.player_name),
    chunk: readString(root.chunk ?? data.chunk ?? root.text ?? data.text),
  };
}

function readChatPayload(msg: WSMessage) {
  const root = toRecord(msg);
  const data = toRecord(root.data);
  return {
    player_id: readString(root.player_id ?? data.player_id),
    player_name: readString(root.player_name ?? data.player_name),
    message: readString(root.message ?? data.message),
    is_thinking: readBoolean(root.is_thinking ?? data.is_thinking),
    is_spectator: readBoolean(root.is_spectator ?? data.is_spectator),
    timestamp:
      typeof (root.timestamp ?? data.timestamp) === 'number'
        ? Number(root.timestamp ?? data.timestamp)
        : Date.now() / 1000,
  };
}

function applyHistorySnapshot(
  snapshot: HistorySnapshotData,
  setChatMessages: (value: ChatMessage[]) => void,
  setActiveThinking: (value: ActiveThinking | null) => void,
  thinkingBuffersRef: MutableRefObject<Map<string, string>>,
  cancelPendingThinkingClear: () => void,
) {
  cancelPendingThinkingClear();
  thinkingBuffersRef.current.clear();
  setChatMessages(Array.isArray(snapshot.chat_messages) ? snapshot.chat_messages : []);

  if (snapshot.active_thinking) {
    thinkingBuffersRef.current.set(
      snapshot.active_thinking.player_id,
      snapshot.active_thinking.text,
    );
    setActiveThinking({
      player_id: snapshot.active_thinking.player_id,
      player_name: snapshot.active_thinking.player_name,
      text: snapshot.active_thinking.text,
    });
  } else {
    setActiveThinking(null);
  }
}

export function GameProvider({ children }: { children: ReactNode }) {
  const [gameState, setGameState] = useState<GameStateData | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [tournamentStatus, setTournamentStatus] = useState<'idle' | 'running' | 'finished'>('idle');
  const [winner, setWinner] = useState<TournamentOverData | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [spectatorCount, setSpectatorCount] = useState(0);
  const [activeThinking, setActiveThinking] = useState<ActiveThinking | null>(null);
  const [debugPrompts, setDebugPrompts] = useState<DebugPrompt[]>([]);
  const thinkingBuffersRef = useRef(new Map<string, string>());
  const clearThinkingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancelPendingThinkingClear = useCallback(() => {
    if (clearThinkingTimerRef.current) {
      clearTimeout(clearThinkingTimerRef.current);
      clearThinkingTimerRef.current = null;
    }
  }, []);

  const scheduleThinkingClear = useCallback((delayMs = 1500) => {
    cancelPendingThinkingClear();
    clearThinkingTimerRef.current = setTimeout(() => {
      setActiveThinking(null);
      thinkingBuffersRef.current.clear();
      clearThinkingTimerRef.current = null;
    }, delayMs);
  }, [cancelPendingThinkingClear]);

  const handleWSMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'game_state':
        setGameState(msg.data as GameStateData);
        if (tournamentStatus === 'idle') setTournamentStatus('running');
        scheduleThinkingClear();
        break;
      case 'history_snapshot':
        applyHistorySnapshot(
          msg.data,
          setChatMessages,
          setActiveThinking,
          thinkingBuffersRef,
          cancelPendingThinkingClear,
        );
        break;
      case 'thinking_chunk':
      {
        const payload = readThinkingChunkPayload(msg);
        if (!payload.chunk) {
          break;
        }
        cancelPendingThinkingClear();
        setActiveThinking((prev) => {
          if (prev && prev.player_id !== payload.player_id) {
            thinkingBuffersRef.current.clear();
          }

          const previousText = thinkingBuffersRef.current.get(payload.player_id) ?? '';
          const nextText = payload.chunk.startsWith(previousText)
            ? payload.chunk
            : `${previousText}${payload.chunk}`;
          thinkingBuffersRef.current.set(payload.player_id, nextText);

          return {
            player_id: payload.player_id,
            player_name: payload.player_name,
            text: nextText,
          };
        });
        break;
      }
      case 'chat':
      {
        const payload = readChatPayload(msg);
        if (!payload.is_spectator) {
          cancelPendingThinkingClear();
          thinkingBuffersRef.current.delete(payload.player_id);
          setActiveThinking((prev) => prev?.player_id === payload.player_id ? null : prev);
        }
        setChatMessages((prev) => [...prev, {
          player_id: payload.player_id,
          player_name: payload.player_name,
          message: payload.message,
          is_thinking: payload.is_thinking,
          is_spectator: payload.is_spectator,
          timestamp: payload.timestamp,
        }]);
        break;
      }
      case 'debug_prompt':
        setDebugPrompts((prev) => [...prev, {
          player_id: msg.player_id,
          player_name: msg.player_name,
          system_prompt: msg.system_prompt,
          user_message: msg.user_message,
          timestamp: msg.timestamp,
        }]);
        break;
      case 'tournament_start':
        setTournamentStatus('running');
        break;
      case 'tournament_over':
        setTournamentStatus('finished');
        setWinner(msg.data as TournamentOverData);
        break;
      case 'spectator_count':
        setSpectatorCount(Number(msg.data.count) || 0);
        break;
    }
  }, [cancelPendingThinkingClear, scheduleThinkingClear, tournamentStatus]);

  const reset = useCallback(() => {
    cancelPendingThinkingClear();
    thinkingBuffersRef.current.clear();
    setGameState(null);
    setChatMessages([]);
    setTournamentStatus('idle');
    setWinner(null);
    setActiveThinking(null);
    setDebugPrompts([]);
  }, [cancelPendingThinkingClear]);

  return (
    <GameContext.Provider
      value={{
        gameState,
        chatMessages,
        tournamentStatus,
        winner,
        isConnected,
        spectatorCount,
        activeThinking,
        debugPrompts,
        handleWSMessage,
        setIsConnected,
        reset,
      }}
    >
      {children}
    </GameContext.Provider>
  );
}

export function useGameContext() {
  const ctx = useContext(GameContext);
  if (!ctx) throw new Error('useGameContext must be used within GameProvider');
  return ctx;
}

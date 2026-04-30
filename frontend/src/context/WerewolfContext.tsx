/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useCallback, useRef, type ReactNode } from 'react';
import type { WerewolfGameState, WerewolfWSMessage } from '../types/werewolf';

interface ChatMessage {
  player_id: string;
  player_name: string;
  message: string;
  is_thinking: boolean;
  is_spectator?: boolean;
  timestamp: number;
}

interface ActiveThinking {
  player_id: string;
  player_name: string;
  text: string;
}

interface DebugPrompt {
  player_id: string;
  player_name: string;
  system_prompt: string;
  user_message: string;
  timestamp: number;
}

interface WerewolfContextValue {
  gameState: WerewolfGameState | null;
  chatMessages: ChatMessage[];
  tournamentStatus: 'idle' | 'running' | 'finished';
  winner: { winner_id: string; winner_name: string; standings: unknown[] } | null;
  isConnected: boolean;
  spectatorCount: number;
  activeThinking: ActiveThinking | null;
  debugPrompts: DebugPrompt[];
  handleWSMessage: (msg: WerewolfWSMessage & Record<string, unknown>) => void;
  setIsConnected: (v: boolean) => void;
  reset: () => void;
}

const WerewolfContext = createContext<WerewolfContextValue | null>(null);

function readString(value: unknown) {
  if (typeof value === 'string') return value;
  if (value == null) return '';
  return String(value);
}

export function WerewolfProvider({ children }: { children: ReactNode }) {
  const [gameState, setGameState] = useState<WerewolfGameState | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [tournamentStatus, setTournamentStatus] = useState<'idle' | 'running' | 'finished'>('idle');
  const [winner, setWinner] = useState<WerewolfContextValue['winner']>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [spectatorCount, setSpectatorCount] = useState(0);
  const [activeThinking, setActiveThinking] = useState<ActiveThinking | null>(null);
  const [debugPrompts, setDebugPrompts] = useState<DebugPrompt[]>([]);
  const thinkingBuffersRef = useRef(new Map<string, string>());

  const handleWSMessage = useCallback((msg: WerewolfWSMessage & Record<string, unknown>) => {
    const eventData = msg.type === 'game_event'
      ? ((msg.data as unknown) as Record<string, unknown> | undefined)
      : undefined;
    const messageType = eventData?.event_type ? readString(eventData.event_type) : msg.type;

    switch (messageType) {
      case 'game_state':
        setGameState(msg.data as WerewolfGameState);
        if ((msg.data as WerewolfGameState | undefined)?.is_over) {
          setTournamentStatus('finished');
        } else {
          setTournamentStatus((prev) => prev === 'idle' ? 'running' : prev);
        }
        break;
      case 'history_snapshot':
      {
        const snapshot = (msg.data as unknown) as {
          chat_messages?: ChatMessage[];
          active_thinking?: ActiveThinking | null;
        };
        thinkingBuffersRef.current.clear();
        setChatMessages(Array.isArray(snapshot.chat_messages) ? snapshot.chat_messages : []);
        if (snapshot.active_thinking) {
          thinkingBuffersRef.current.set(snapshot.active_thinking.player_id, snapshot.active_thinking.text);
          setActiveThinking(snapshot.active_thinking);
        } else {
          setActiveThinking(null);
        }
        break;
      }
      case 'thinking_chunk':
      {
        const pid = readString(msg.player_id);
        const chunk = readString(msg.chunk);
        if (!chunk) break;

        setActiveThinking(() => {
          thinkingBuffersRef.current.set(pid, chunk);
          return {
            player_id: pid,
            player_name: readString(msg.player_name),
            text: chunk,
          };
        });
        break;
      }
      case 'chat':
      {
        const chat = {
          player_id: readString(msg.player_id),
          player_name: readString(msg.player_name),
          message: readString(msg.message),
          is_thinking: Boolean(msg.is_thinking),
          is_spectator: Boolean(msg.is_spectator),
          timestamp: Number(msg.timestamp) || Date.now() / 1000,
        };
        if (!chat.is_spectator) {
          thinkingBuffersRef.current.delete(chat.player_id);
          setActiveThinking((prev) => prev?.player_id === chat.player_id ? null : prev);
        }
        setChatMessages((prev) => [...prev, chat]);
        break;
      }
      case 'debug_prompt':
        setDebugPrompts((prev) => [...prev, {
          player_id: readString(msg.player_id),
          player_name: readString(msg.player_name),
          system_prompt: readString(msg.system_prompt),
          user_message: readString(msg.user_message),
          timestamp: Number(msg.timestamp) || Date.now(),
        }]);
        break;
      case 'tournament_start':
        setTournamentStatus('running');
        break;
      case 'tournament_over':
        setTournamentStatus('finished');
        setWinner((msg.data as unknown) as WerewolfContextValue['winner']);
        break;
      case 'spectator_count':
        setSpectatorCount(Number(((msg.data as unknown) as Record<string, unknown>)?.count) || 0);
        break;
      case 'phase_change':
      case 'night_result':
      case 'vote_result':
      case 'sheriff_elected':
        // Phase events - state will be updated via subsequent game_state
        break;
    }
  }, []);

  const reset = useCallback(() => {
    thinkingBuffersRef.current.clear();
    setGameState(null);
    setChatMessages([]);
    setTournamentStatus('idle');
    setWinner(null);
    setActiveThinking(null);
    setDebugPrompts([]);
  }, []);

  return (
    <WerewolfContext.Provider
      value={{
        gameState, chatMessages, tournamentStatus, winner,
        isConnected, spectatorCount, activeThinking, debugPrompts,
        handleWSMessage, setIsConnected, reset,
      }}
    >
      {children}
    </WerewolfContext.Provider>
  );
}

export function useWerewolfContext() {
  const ctx = useContext(WerewolfContext);
  if (!ctx) throw new Error('useWerewolfContext must be used within WerewolfProvider');
  return ctx;
}

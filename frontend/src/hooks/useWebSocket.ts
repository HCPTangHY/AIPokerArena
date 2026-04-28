/* eslint-disable react-hooks/refs, react-hooks/immutability */
import { useRef, useEffect, useCallback, useState } from 'react';
import type { WSMessage } from '../types/game';

interface UseWebSocketOptions {
  onMessage?: (msg: WSMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  enabled?: boolean;
  wsRef?: React.MutableRefObject<WebSocket | null>;
}

export function useWebSocket(
  tournamentId: string | null,
  options: UseWebSocketOptions = {},
) {
  const { onMessage, onConnect, onDisconnect, enabled = true, wsRef: externalRef } = options;
  const internalRef = useRef<WebSocket | null>(null);
  const wsRef = externalRef || internalRef;
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempt = useRef(0);
  const [isConnected, setIsConnected] = useState(false);
  const [displayAttempt, setDisplayAttempt] = useState(0);

  // Keep callbacks in refs to avoid stale closures
  const onMessageRef = useRef(onMessage);
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);
  onMessageRef.current = onMessage;
  onConnectRef.current = onConnect;
  onDisconnectRef.current = onDisconnect;

  const connect = useCallback(() => {
    if (!enabled) return;

    const token = localStorage.getItem('token');
    if (!token) return;

    // Clean up previous connection
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
    }
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const roomId = tournamentId ?? '';
    const url = `${protocol}//${host}/poker/ws/spectate?token=${encodeURIComponent(token)}&tournament_id=${encodeURIComponent(roomId)}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      reconnectAttempt.current = 0;
      setDisplayAttempt(0);
      onConnectRef.current?.();
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WSMessage;
        onMessageRef.current?.(msg);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      onDisconnectRef.current?.();

      const attempt = reconnectAttempt.current + 1;
      reconnectAttempt.current = attempt;
      setDisplayAttempt(attempt);

      const delay = Math.min(1000 * Math.pow(2, attempt - 1), 10000);
      reconnectTimeout.current = setTimeout(() => {
        connect();
      }, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [enabled, tournamentId, wsRef]); // stable deps only — no state

  // Connect on mount and when enabled/tournamentId changes
  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.onmessage = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, wsRef]);

  return { isConnected, reconnectAttempt: displayAttempt };
}

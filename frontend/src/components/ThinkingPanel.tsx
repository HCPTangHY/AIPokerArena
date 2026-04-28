import { useRef, useEffect } from 'react';
import type { ChatMessage } from '../types/game';
import type { ActiveThinking } from '../context/GameContext';

interface Props {
  thinkingMessages: ChatMessage[];
  activeThinking: ActiveThinking | null;
}

function formatStep(index: number) {
  return String(index + 1).padStart(2, '0');
}

export function ThinkingPanel({ thinkingMessages, activeThinking }: Props) {
  const listRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);

  useEffect(() => {
    if (shouldAutoScrollRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [thinkingMessages, activeThinking]);

  const handleScroll = () => {
    const node = listRef.current;
    if (!node) return;
    const dist = node.scrollHeight - node.scrollTop - node.clientHeight;
    shouldAutoScrollRef.current = dist < 32;
  };

  return (
    <div className="thinking-panel">
      <div className="panel-title-row">
        <div>
          <h2>AI 思考过程</h2>
          <span>{activeThinking ? activeThinking.player_name : '实时推理流'}</span>
        </div>
        <span className={activeThinking ? 'thinking-state is-live' : 'thinking-state'}>{activeThinking ? '正在思考' : '待机'}</span>
      </div>

      <div ref={listRef} className="thinking-list" onScroll={handleScroll}>
        {thinkingMessages.length === 0 && !activeThinking && (
          <p className="muted-copy">AI 思考内容将在这里显示...</p>
        )}

        {thinkingMessages.slice(-8).map((message, index) => (
          <article key={`${message.player_name}-${message.timestamp}-${index}`} className="thinking-item">
            <span className="thinking-index">{formatStep(index)}</span>
            <div>
              <strong>{message.player_name}</strong>
              <p>{message.message}</p>
            </div>
          </article>
        ))}

        {activeThinking && (
          <article className="thinking-item is-active">
            <span className="thinking-index">AI</span>
            <div>
              <strong>{activeThinking.player_name}</strong>
              <p>{activeThinking.text}</p>
            </div>
          </article>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}

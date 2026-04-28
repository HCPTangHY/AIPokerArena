import { useRef, useEffect, useState, type KeyboardEvent } from 'react';
import type { ChatMessage } from '../types/game';

interface Props {
  messages: ChatMessage[];
  onSend?: (message: string) => void;
}

function formatMessageTime(timestamp: number) {
  const ms = timestamp > 10_000_000_000 ? timestamp : timestamp * 1000;
  return new Date(ms).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function ChatPanel({ messages, onSend }: Props) {
  const listRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const [input, setInput] = useState('');

  useEffect(() => {
    if (shouldAutoScrollRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const handleScroll = () => {
    const node = listRef.current;
    if (!node) return;

    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 32;
  };

  const handleSend = () => {
    const text = input.trim();
    if (!text || !onSend) return;
    onSend(text);
    setInput('');
  };

  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-panel">
      <div className="panel-title-row">
        <div>
          <h2>观众聊天</h2>
          <span>{messages.length.toLocaleString('en-US')} 条消息</span>
        </div>
        <span className="panel-select">热门聊天</span>
      </div>

      <div ref={listRef} className="chat-message-list" onScroll={handleScroll}>
        {messages.length === 0 && (
          <p className="muted-copy">发送消息和其他观众聊天...</p>
        )}
        {messages.map((message, index) => (
          <article
            key={`${message.player_id}-${message.timestamp}-${index}`}
            className={`chat-message ${message.is_spectator ? 'is-spectator' : ''}`}
          >
            <div className="chat-avatar" aria-hidden="true">
              {message.player_name.slice(0, 1).toUpperCase()}
            </div>
            <div className="chat-message-body">
              <div className="chat-message-head">
                <strong>{message.player_name}</strong>
                <time>{formatMessageTime(message.timestamp)}</time>
              </div>
              <p>{message.message}</p>
            </div>
          </article>
        ))}
        <div ref={bottomRef} />
      </div>

      {onSend && (
        <div className="chat-input-area">
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息..."
          />
          <button type="button" onClick={handleSend}>发送</button>
        </div>
      )}
    </div>
  );
}

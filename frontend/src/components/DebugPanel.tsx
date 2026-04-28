/* eslint-disable react-hooks/set-state-in-effect */
import { useRef, useEffect, useState } from 'react';
import type { DebugPrompt } from '../types/game';

interface Props {
  prompts: DebugPrompt[];
}

export function DebugPanel({ prompts }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<DebugPrompt | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [prompts]);

  // Show latest prompt by default
  useEffect(() => {
    if (prompts.length > 0) {
      setSelected(prompts[prompts.length - 1]);
    }
  }, [prompts]);

  if (selected) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <span style={styles.title}>Debug: {selected.player_name}</span>
          <span style={styles.count}>{prompts.length} 条提示词</span>
          <button onClick={() => setSelected(null)} style={styles.closeBtn}>✕</button>
        </div>
        <div style={styles.body} ref={bottomRef}>
          <details open>
            <summary style={styles.sectionTitle}>系统提示词</summary>
            <pre style={styles.pre}>{selected.system_prompt}</pre>
          </details>
          <details open>
            <summary style={styles.sectionTitle}>用户消息</summary>
            <pre style={styles.pre}>{selected.user_message}</pre>
          </details>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.title}>调试控制台</span>
        <span style={styles.count}>{prompts.length}</span>
      </div>
      <div style={styles.list}>
        {prompts.length === 0 && (
          <p style={styles.empty}>等待 AI 提示词...</p>
        )}
        {prompts.map((p, i) => (
          <div
            key={i}
            onClick={() => setSelected(p)}
            style={styles.item}
          >
            <span style={styles.playerName}>{p.player_name}</span>
            <span style={styles.time}>
              {new Date(p.timestamp * 1000).toLocaleTimeString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: '#0d1117',
    borderLeft: '1px solid #30363d',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 12px',
    borderBottom: '1px solid #30363d',
    background: '#161b22',
  },
  title: {
    fontSize: 12,
    fontWeight: 700,
    color: '#f78166',
    flex: 1,
  },
  count: {
    fontSize: 10,
    color: '#484f58',
    fontFamily: 'monospace',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#484f58',
    cursor: 'pointer',
    fontSize: 14,
    padding: '0 4px',
  },
  body: {
    flex: 1,
    overflow: 'auto',
    padding: 8,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: 600,
    color: '#58a6ff',
    cursor: 'pointer',
    marginBottom: 4,
  },
  pre: {
    fontSize: 11,
    fontFamily: '"Cascadia Code", "Fira Code", monospace',
    color: '#c9d1d9',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    background: '#0d1117',
    padding: '8px',
    borderRadius: 4,
    border: '1px solid #21262d',
    margin: 0,
    maxHeight: 300,
    overflow: 'auto',
  },
  list: {
    flex: 1,
    overflow: 'auto',
    padding: 4,
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  empty: {
    color: '#484f58',
    fontSize: 11,
    textAlign: 'center',
    padding: '16px 0',
    fontStyle: 'italic',
  },
  item: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '5px 8px',
    borderRadius: 4,
    cursor: 'pointer',
    background: 'transparent',
    transition: 'background 0.1s',
  },
  playerName: {
    fontSize: 11,
    color: '#c9d1d9',
    fontFamily: 'monospace',
  },
  time: {
    fontSize: 10,
    color: '#484f58',
    fontFamily: 'monospace',
  },
};

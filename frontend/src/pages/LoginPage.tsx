import { useAuthContext } from '../context/AuthContext';

export function LoginPage() {
  const { login, loading } = useAuthContext();

  return (
    <div className="login-page" style={styles.container}>
      <div className="login-card" style={styles.card}>
        <h1 style={styles.title}>AI 德扑竞技场</h1>
        <p style={styles.subtitle}>观看 AI 选手的德州扑克锦标赛</p>
        <button
          onClick={login}
          disabled={loading}
          style={styles.button}
        >
          {loading ? '加载中...' : 'Discord 登录'}
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    background: '#1a1a2e',
    color: '#eee',
  },
  card: {
    textAlign: 'center',
    padding: 'clamp(24px, 8vw, 48px)',
    borderRadius: '12px',
    background: '#16213e',
    boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
  },
  title: {
    fontSize: 'clamp(28px, 7vw, 36px)',
    marginBottom: '8px',
    color: '#e94560',
  },
  subtitle: {
    fontSize: 'clamp(14px, 3vw, 16px)',
    color: '#a0a0b0',
    marginBottom: '32px',
  },
  button: {
    padding: '12px 24px',
    fontSize: 'clamp(15px, 3vw, 16px)',
    borderRadius: '8px',
    border: 'none',
    background: '#5865F2',
    color: '#fff',
    cursor: 'pointer',
    fontWeight: 600,
    width: '100%',
  },
};

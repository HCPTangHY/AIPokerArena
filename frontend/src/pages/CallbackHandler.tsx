import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export function CallbackHandler() {
  const navigate = useNavigate();

  useEffect(() => {
    const gamePrefix = window.location.pathname.split('/').filter(Boolean)[0];
    const loginPath = gamePrefix === 'poker' || gamePrefix === 'werewolf'
      ? `/${gamePrefix}/login`
      : '/login';
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    const next = params.get('next') || '/';

    if (!token) {
      navigate(loginPath);
      return;
    }

    localStorage.setItem('token', token);
    navigate(next.startsWith('/') && !next.startsWith('//') ? next : '/');
  }, [navigate]);

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#1a1a2e', color: '#eee' }}>
      <p>登录中...</p>
    </div>
  );
}

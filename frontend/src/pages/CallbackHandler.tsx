import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export function CallbackHandler() {
  const navigate = useNavigate();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');

    if (!token) {
      navigate('/login');
      return;
    }

    localStorage.setItem('token', token);
    navigate('/');
  }, [navigate]);

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#1a1a2e', color: '#eee' }}>
      <p>登录中...</p>
    </div>
  );
}

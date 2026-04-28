/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useCallback, useEffect } from 'react';
import { api } from '../utils/api';

interface User {
  id: string;
  username: string;
  global_name: string;
  avatar: string | null;
  is_admin: boolean;
}

function decodeJWT(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split('.')[1];
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      // Try /me first, fall back to decoding JWT
      api.getMe()
        .then((data) => {
          const u = data.user as Record<string, unknown>;
          setUser({
            id: u.sub as string || u.id as string,
            username: u.username as string,
            global_name: u.global_name as string,
            avatar: u.avatar as string || null,
            is_admin: (u.is_admin as boolean) || false,
          });
        })
        .catch(() => {
          // Fallback: decode JWT locally
          const payload = decodeJWT(token);
          if (payload) {
            setUser({
              id: (payload.sub as string) || '',
              username: (payload.username as string) || '',
              global_name: (payload.global_name as string) || '',
              avatar: (payload.avatar as string) || null,
              is_admin: (payload.is_admin as boolean) || false,
            });
          } else {
            localStorage.removeItem('token');
          }
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async () => {
    const { url } = await api.getLoginUrl();
    window.location.href = url;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    setUser(null);
  }, []);

  return { user, loading, login, logout, isAuthenticated: !!user, isAdmin: user?.is_admin || false };
}

/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, type ReactNode } from 'react';
import { useAuth } from '../hooks/useAuth';

interface AuthContextValue {
  user: {
    id: string;
    username: string;
    global_name: string;
    avatar: string | null;
    is_admin: boolean;
  } | null;
  loading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();

  return (
    <AuthContext.Provider
      value={{
        user: auth.user,
        loading: auth.loading,
        isAuthenticated: auth.isAuthenticated,
        isAdmin: auth.isAdmin,
        login: auth.login,
        logout: auth.logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuthContext() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuthContext must be used within AuthProvider');
  return ctx;
}

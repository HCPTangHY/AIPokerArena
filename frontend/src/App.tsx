import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuthContext } from './context/AuthContext';
import { GameProvider } from './context/GameContext';
import { LoginPage } from './pages/LoginPage';
import { SpectatorPage } from './pages/SpectatorPage';
import { ConfigPage } from './pages/ConfigPage';
import { CallbackHandler } from './pages/CallbackHandler';

const routerBasename = window.location.pathname.startsWith('/poker') ? '/poker' : '/';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuthContext();

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#1a1a2e', color: '#eee' }}>Loading...</div>;
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function AppRoutes() {
  const { isAuthenticated } = useAuthContext();

  return (
    <Routes>
      <Route path="/login" element={
        isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />
      } />
      <Route path="/auth/callback" element={<CallbackHandler />} />
      <Route path="/" element={
        <ProtectedRoute>
          <GameProvider>
            <SpectatorPage />
          </GameProvider>
        </ProtectedRoute>
      } />
      <Route path="/config" element={
        <ProtectedRoute>
          <ConfigPage />
        </ProtectedRoute>
      } />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter basename={routerBasename}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

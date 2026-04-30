import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuthContext } from './context/AuthContext';
import { GameProvider } from './context/GameContext';
import { WerewolfProvider } from './context/WerewolfContext';
import { LoginPage } from './pages/LoginPage';
import { SpectatorPage } from './pages/SpectatorPage';
import { WerewolfPage } from './pages/WerewolfPage';
import { ConfigPage } from './pages/ConfigPage';
import { CallbackHandler } from './pages/CallbackHandler';

const routerBasename = '/';

function getGamePrefix(pathname: string) {
  const firstSegment = pathname.split('/').filter(Boolean)[0];
  return firstSegment === 'poker' || firstSegment === 'werewolf' ? `/${firstSegment}` : '';
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuthContext();
  const location = useLocation();

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#1a1a2e', color: '#eee' }}>Loading...</div>;
  }
  if (!isAuthenticated) {
    const next = `${location.pathname}${location.search}${location.hash}`;
    const prefix = getGamePrefix(location.pathname);
    return <Navigate to={`${prefix}/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <>{children}</>;
}

function LoginRoute() {
  const { isAuthenticated } = useAuthContext();
  const location = useLocation();
  const prefix = getGamePrefix(location.pathname);
  return isAuthenticated ? <Navigate to={prefix || '/'} replace /> : <LoginPage />;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/poker/login" element={<LoginRoute />} />
      <Route path="/werewolf/login" element={<LoginRoute />} />
      <Route path="/auth/callback" element={<CallbackHandler />} />
      <Route path="/poker/auth/callback" element={<CallbackHandler />} />
      <Route path="/werewolf/auth/callback" element={<CallbackHandler />} />
      <Route path="/poker" element={
        <ProtectedRoute>
          <GameProvider>
            <SpectatorPage />
          </GameProvider>
        </ProtectedRoute>
      } />
      <Route path="/werewolf" element={
        <ProtectedRoute>
          <WerewolfProvider>
            <WerewolfPage />
          </WerewolfProvider>
        </ProtectedRoute>
      } />
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

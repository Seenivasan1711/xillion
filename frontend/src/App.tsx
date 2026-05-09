import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Dashboard from './pages/Dashboard'
import Strategies from './pages/Strategies'
import Backtest from './pages/Backtest'
import Trades from './pages/Trades'
import Logs from './pages/Logs'
import Settings from './pages/Settings'
import Login from './pages/Login'
import Setup from './pages/Setup'
import { wsClient } from './lib/ws'

function AppRoutes() {
  const { user } = useAuth()

  useEffect(() => {
    if (user) wsClient.connect()
  }, [user])

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/setup" element={<Setup />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="strategies" element={<Strategies />} />
        <Route path="trades" element={<Trades />} />
        <Route path="backtest" element={<Backtest />} />
        <Route path="logs" element={<Logs />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}

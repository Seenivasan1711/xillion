import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, BarChart2, Cpu, LogOut, User, Zap } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { wsClient } from '../lib/ws'
import { api } from '../lib/api'
import KillSwitchModal from './KillSwitchModal'

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [showKillModal, setShowKillModal] = useState(false)
  const [killActive, setKillActive] = useState(false)

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      isActive ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
    }`

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  // Poll risk status + listen for WS kill_switch events
  useEffect(() => {
    const loadStatus = async () => {
      try {
        const s = await api.risk.status()
        setKillActive(s.kill_switch_active)
      } catch {
        // ignore — might not be authenticated yet
      }
    }
    loadStatus()
    const t = setInterval(loadStatus, 30_000)

    const unsub = wsClient.subscribe((event) => {
      if (event.type === 'kill_switch') {
        setKillActive(Boolean(event.active))
      }
    })

    return () => {
      clearInterval(t)
      unsub()
    }
  }, [])

  const handleKillFired = () => {
    setShowKillModal(false)
    setKillActive(true)
  }

  const handleResetKill = async () => {
    if (!confirm('Reset kill switch? This allows strategies to run again.')) return
    try {
      await api.risk.resetKillSwitch()
      setKillActive(false)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to reset')
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Kill switch banner */}
      {killActive && (
        <div className="bg-red-900 border-b border-red-700 px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-2 text-red-200 text-sm">
            <AlertTriangle size={16} />
            <span className="font-bold">KILL SWITCH ACTIVE</span>
            <span className="text-red-300">— all strategies halted, no new orders allowed</span>
          </div>
          <button onClick={handleResetKill} className="text-xs text-red-300 hover:text-red-100 underline">
            Reset
          </button>
        </div>
      )}

      <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 font-bold text-lg">
            <Zap size={20} className="text-brand-500" />
            <span>Xillion</span>
          </Link>

          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={navClass}>
              <Activity size={16} />
              Dashboard
            </NavLink>
            <NavLink to="/strategies" className={navClass}>
              <Cpu size={16} />
              Strategies
            </NavLink>
            <NavLink to="/backtest" className={navClass}>
              <BarChart2 size={16} />
              Backtest
            </NavLink>
          </nav>

          <div className="flex items-center gap-3">
            {user && (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <User size={12} />
                {user.username}
              </span>
            )}
            <button
              onClick={() => setShowKillModal(true)}
              className={`text-xs font-bold tracking-wider px-3 py-1.5 rounded-md transition-colors ${
                killActive
                  ? 'bg-red-800 text-red-200 cursor-not-allowed'
                  : 'bg-red-600 hover:bg-red-700 text-white'
              }`}
              disabled={killActive}
            >
              {killActive ? 'KILLED' : 'KILL SWITCH'}
            </button>
            <button
              onClick={handleLogout}
              className="p-2 text-gray-500 hover:text-gray-300 transition-colors"
              title="Sign out"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        <Outlet />
      </main>

      {showKillModal && (
        <KillSwitchModal onClose={() => setShowKillModal(false)} onFired={handleKillFired} />
      )}
    </div>
  )
}

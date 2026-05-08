import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Activity, BarChart2, Cpu, LogOut, User, Zap } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      isActive
        ? 'bg-gray-800 text-white'
        : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
    }`

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex flex-col">
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
            <KillSwitch />
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
    </div>
  )
}

function KillSwitch() {
  const handleKill = () => {
    if (window.confirm('KILL SWITCH: Stop all strategies and cancel all open orders?')) {
      // Phase 5: wire to /api/kill-switch endpoint
      alert('Kill switch not yet implemented (Phase 5)')
    }
  }
  return (
    <button onClick={handleKill} className="btn-danger text-xs font-bold tracking-wider">
      KILL SWITCH
    </button>
  )
}

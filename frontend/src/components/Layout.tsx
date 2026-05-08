import { Link, NavLink, Outlet } from 'react-router-dom'
import { Activity, BarChart2, Cpu, Zap } from 'lucide-react'

export default function Layout() {
  const navClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      isActive
        ? 'bg-gray-800 text-white'
        : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
    }`

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top bar */}
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

          <KillSwitch />
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
      alert('Kill switch endpoint not yet implemented (Phase 5)')
    }
  }
  return (
    <button onClick={handleKill} className="btn-danger text-xs font-bold tracking-wider">
      KILL SWITCH
    </button>
  )
}

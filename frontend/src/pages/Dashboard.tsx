import { useEffect, useState } from 'react'
import { Activity, CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'

interface HealthData {
  status: string
  version: string
  timestamp: string
}

interface Runner {
  instance_id: string
  status: string
  last_error: string | null
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthData | null>(null)
  const [runners, setRunners] = useState<Runner[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      const [h, r] = await Promise.all([api.health(), api.strategies.runners()])
      setHealth(h)
      setRunners(r.runners)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 10_000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <button onClick={refresh} disabled={loading} className="btn-primary flex items-center gap-2">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="card border-red-800 bg-red-950/30 text-red-300 text-sm">{error}</div>
      )}

      {/* System Health */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <Activity size={16} className="text-gray-400" />
            <span className="text-sm text-gray-400 uppercase tracking-wider">System</span>
          </div>
          {health ? (
            <div className="flex items-center gap-2">
              <CheckCircle size={18} className="text-green-400" />
              <span className="font-medium">Online</span>
              <span className="text-xs text-gray-500 ml-auto">v{health.version}</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-gray-500">
              <XCircle size={18} />
              <span>{loading ? 'Checking…' : 'Offline'}</span>
            </div>
          )}
        </div>

        <div className="card">
          <div className="text-sm text-gray-400 uppercase tracking-wider mb-2">Running</div>
          <div className="text-3xl font-bold text-green-400">
            {runners.filter((r) => r.status === 'running').length}
          </div>
          <div className="text-xs text-gray-500">strategy instances</div>
        </div>

        <div className="card">
          <div className="text-sm text-gray-400 uppercase tracking-wider mb-2">Last Updated</div>
          <div className="text-sm font-mono text-gray-300">
            {health
              ? new Date(health.timestamp).toLocaleTimeString()
              : loading
              ? '…'
              : '—'}
          </div>
        </div>
      </div>

      {/* Running instances */}
      <div className="card">
        <h2 className="font-semibold mb-4 flex items-center gap-2">
          <Activity size={16} className="text-gray-400" />
          Active Strategy Instances
        </h2>
        {runners.length === 0 ? (
          <div className="text-gray-500 text-sm py-4 text-center">
            No strategies running.{' '}
            <a href="/strategies" className="text-brand-500 hover:underline">
              Load a strategy
            </a>{' '}
            to get started.
          </div>
        ) : (
          <div className="space-y-2">
            {runners.map((r) => (
              <div key={r.instance_id} className="flex items-center gap-3 py-2 border-b border-gray-800 last:border-0">
                <span
                  className={
                    r.status === 'running'
                      ? 'badge-running'
                      : r.status === 'error'
                      ? 'badge-error'
                      : 'badge-idle'
                  }
                >
                  {r.status}
                </span>
                <span className="font-mono text-xs text-gray-400">{r.instance_id}</span>
                {r.last_error && (
                  <span className="text-xs text-red-400 ml-auto">{r.last_error}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

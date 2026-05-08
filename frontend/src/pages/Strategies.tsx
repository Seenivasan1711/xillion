import { useEffect, useState } from 'react'
import { RefreshCw, Cpu, Clock, Tag } from 'lucide-react'
import { api, StrategyClass } from '../lib/api'

export default function Strategies() {
  const [strategies, setStrategies] = useState<StrategyClass[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.strategies.classes()
      setStrategies(res.strategies)
      setErrors(res.errors)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const reload = async () => {
    setLoading(true)
    try {
      await api.strategies.reload()
      await load()
    } catch (e) {
      console.error(e)
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Cpu size={22} />
          Strategies
        </h1>
        <button onClick={reload} disabled={loading} className="btn-primary flex items-center gap-2">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Reload
        </button>
      </div>

      {Object.keys(errors).length > 0 && (
        <div className="card border-yellow-800 bg-yellow-950/20">
          <h3 className="text-yellow-400 text-sm font-medium mb-2">Load Errors</h3>
          {Object.entries(errors).map(([key, msg]) => (
            <div key={key} className="text-xs text-yellow-300 font-mono">
              {key}: {msg}
            </div>
          ))}
        </div>
      )}

      {strategies.length === 0 && !loading ? (
        <div className="card text-center py-12 text-gray-500">
          <Cpu size={40} className="mx-auto mb-3 opacity-30" />
          <p>No strategies found.</p>
          <p className="text-sm mt-1">
            Drop a <code className="text-gray-400">.py</code> file in the{' '}
            <code className="text-gray-400">strategies/</code> folder and click Reload.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {strategies.map((s) => (
            <StrategyCard key={s.name} strategy={s} />
          ))}
        </div>
      )}
    </div>
  )
}

function StrategyCard({ strategy: s }: { strategy: StrategyClass }) {
  return (
    <div className="card hover:border-gray-700 transition-colors flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-semibold">{s.name}</h3>
          <p className="text-xs text-gray-500">{s.description || 'No description'}</p>
        </div>
        <span className="text-xs text-gray-600 font-mono">v{s.version}</span>
      </div>

      <div className="flex items-center gap-3 text-xs text-gray-400">
        <span className="flex items-center gap-1">
          <Clock size={12} />
          {s.timeframe}
        </span>
        {s.author && (
          <span className="flex items-center gap-1">
            <Tag size={12} />
            {s.author}
          </span>
        )}
        <span className="ml-auto font-mono text-gray-600">{s.params_schema.length} params</span>
      </div>

      {s.params_schema.length > 0 && (
        <div className="border-t border-gray-800 pt-2">
          <div className="text-xs text-gray-500 mb-1">Parameters</div>
          <div className="flex flex-wrap gap-1">
            {s.params_schema.map((p) => (
              <span key={p.name} className="text-xs bg-gray-800 text-gray-300 px-2 py-0.5 rounded">
                {p.name}={String(p.default)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

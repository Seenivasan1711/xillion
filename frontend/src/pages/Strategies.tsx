import { useEffect, useState } from 'react'
import { Clock, Cpu, Pause, Play, Plus, RefreshCw, Tag, Trash2, X } from 'lucide-react'
import { api, type CreateInstanceRequest, type ParamSpec, type StrategyClass, type StrategyInstance } from '../lib/api'

export default function Strategies() {
  const [strategies, setStrategies] = useState<StrategyClass[]>([])
  const [instances, setInstances] = useState<StrategyInstance[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'classes' | 'instances'>('instances')
  const [newInstanceFor, setNewInstanceFor] = useState<StrategyClass | null>(null)

  const loadAll = async () => {
    setLoading(true)
    try {
      const [sc, inst] = await Promise.all([
        api.strategies.classes(),
        api.instances.list(),
      ])
      setStrategies(sc.strategies)
      setErrors(sc.errors)
      setInstances(inst.instances)
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
      await loadAll()
    } catch (e) {
      console.error(e)
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
    const t = setInterval(loadAll, 10_000)
    return () => clearInterval(t)
  }, [])

  const handleStart = async (id: string) => {
    try {
      const res = await api.instances.start(id)
      if (res.warning) alert(`Started, but: ${res.warning}`)
      await loadAll()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Start failed')
    }
  }

  const handleStop = async (id: string) => {
    try {
      await api.instances.stop(id)
      await loadAll()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Stop failed')
    }
  }

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete instance "${name}"?`)) return
    try {
      await api.instances.delete(id)
      await loadAll()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Delete failed')
    }
  }

  const handleInstanceCreated = async () => {
    setNewInstanceFor(null)
    await loadAll()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Cpu size={22} />
          Strategies
        </h1>
        <button onClick={reload} disabled={loading} className="btn-primary flex items-center gap-2">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Reload plugins
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-800 gap-4">
        {(['instances', 'classes'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`pb-2 text-sm font-medium capitalize transition-colors ${
              activeTab === tab
                ? 'text-white border-b-2 border-brand-500'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {tab === 'instances' ? `Instances (${instances.length})` : `Classes (${strategies.length})`}
          </button>
        ))}
      </div>

      {/* Plugin load errors */}
      {Object.keys(errors).length > 0 && (
        <div className="card border-yellow-800 bg-yellow-950/20">
          <h3 className="text-yellow-400 text-sm font-medium mb-2">Plugin Load Errors</h3>
          {Object.entries(errors).map(([k, v]) => (
            <div key={k} className="text-xs text-yellow-300 font-mono">{k}: {v}</div>
          ))}
        </div>
      )}

      {/* Instances tab */}
      {activeTab === 'instances' && (
        <div className="space-y-4">
          {instances.length === 0 ? (
            <div className="card text-center py-12 text-gray-500">
              <Cpu size={40} className="mx-auto mb-3 opacity-30" />
              <p>No instances yet.</p>
              <p className="text-sm mt-1">
                Go to <button onClick={() => setActiveTab('classes')} className="text-brand-500 hover:underline">Classes</button> tab and click "New Instance".
              </p>
            </div>
          ) : (
            instances.map((inst) => (
              <InstanceCard
                key={inst.id}
                instance={inst}
                onStart={() => handleStart(inst.id)}
                onStop={() => handleStop(inst.id)}
                onDelete={() => handleDelete(inst.id, inst.name)}
              />
            ))
          )}
        </div>
      )}

      {/* Classes tab */}
      {activeTab === 'classes' && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {strategies.length === 0 && !loading ? (
            <div className="col-span-full card text-center py-12 text-gray-500">
              <Cpu size={40} className="mx-auto mb-3 opacity-30" />
              <p>No strategies found.</p>
              <p className="text-sm mt-1">
                Drop a <code className="text-gray-400">.py</code> file in{' '}
                <code className="text-gray-400">strategies/</code> and click Reload.
              </p>
            </div>
          ) : (
            strategies.map((s) => (
              <StrategyCard
                key={s.name}
                strategy={s}
                onNewInstance={() => setNewInstanceFor(s)}
              />
            ))
          )}
        </div>
      )}

      {/* New Instance Modal */}
      {newInstanceFor && (
        <NewInstanceModal
          strategy={newInstanceFor}
          onClose={() => setNewInstanceFor(null)}
          onCreated={handleInstanceCreated}
        />
      )}
    </div>
  )
}

// ── Instance card ──────────────────────────────────────────────────────────────

function InstanceCard({
  instance: inst,
  onStart,
  onStop,
  onDelete,
}: {
  instance: StrategyInstance
  onStart: () => void
  onStop: () => void
  onDelete: () => void
}) {
  const isRunning = inst.status === 'running'
  const isError = inst.status === 'error'

  return (
    <div className={`card flex flex-col gap-3 ${isError ? 'border-red-800' : ''}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold truncate">{inst.name}</h3>
          <p className="text-xs text-gray-500 truncate">
            {inst.strategy_class_name} · {inst.timeframe} · {inst.instruments.join(', ')}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span
            className={`text-xs px-2 py-0.5 rounded-full ${
              inst.mode === 'live'
                ? 'bg-emerald-900 text-emerald-300'
                : 'bg-sky-900 text-sky-300'
            }`}
          >
            {inst.mode}
          </span>
          <span
            className={
              isRunning ? 'badge-running' : isError ? 'badge-error' : 'badge-idle'
            }
          >
            {inst.status}
          </span>
        </div>
      </div>

      {inst.last_error && (
        <p className="text-xs text-red-400 bg-red-950/30 rounded p-2 truncate">{inst.last_error}</p>
      )}

      <div className="flex items-center gap-2 text-xs text-gray-500">
        <span>₹{inst.capital_allocation.toLocaleString()}</span>
        <span className="text-gray-700">·</span>
        <span>{Object.keys(inst.params).length} params</span>
        {inst.last_started_at && (
          <>
            <span className="text-gray-700">·</span>
            <span>started {new Date(inst.last_started_at).toLocaleTimeString()}</span>
          </>
        )}
      </div>

      <div className="flex gap-2 border-t border-gray-800 pt-3">
        {isRunning ? (
          <button onClick={onStop} className="btn-primary flex items-center gap-1 text-xs py-1.5">
            <Pause size={12} />
            Stop
          </button>
        ) : (
          <button onClick={onStart} className="btn-primary flex items-center gap-1 text-xs py-1.5">
            <Play size={12} />
            Start
          </button>
        )}
        {!isRunning && (
          <button
            onClick={onDelete}
            className="p-1.5 text-gray-600 hover:text-red-400 transition-colors ml-auto"
            title="Delete instance"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </div>
  )
}

// ── Strategy class card ────────────────────────────────────────────────────────

function StrategyCard({
  strategy: s,
  onNewInstance,
}: {
  strategy: StrategyClass
  onNewInstance: () => void
}) {
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

      <button onClick={onNewInstance} className="btn-primary flex items-center justify-center gap-1 text-xs py-1.5 mt-auto">
        <Plus size={12} />
        New Instance
      </button>
    </div>
  )
}

// ── New Instance Modal ─────────────────────────────────────────────────────────

function NewInstanceModal({
  strategy,
  onClose,
  onCreated,
}: {
  strategy: StrategyClass
  onClose: () => void
  onCreated: () => void
}) {
  const [name, setName] = useState(`${strategy.name} — Paper`)
  const [mode, setMode] = useState<'paper' | 'live'>('paper')
  const [instruments, setInstruments] = useState('NIFTY')
  const [timeframe, setTimeframe] = useState(strategy.timeframe)
  const [capital, setCapital] = useState('100000')
  const [params, setParams] = useState<Record<string, unknown>>(
    Object.fromEntries(strategy.params_schema.map((p) => [p.name, p.default]))
  )
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const body: CreateInstanceRequest = {
        name,
        strategy_class_name: strategy.name,
        mode,
        instruments: instruments.split(',').map((s) => s.trim()).filter(Boolean),
        timeframe,
        params,
        capital_allocation: parseFloat(capital),
        risk_limits: {},
      }
      await api.instances.create(body)
      onCreated()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create instance')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <h2 className="font-semibold">New Instance — {strategy.name}</h2>
          <button onClick={onClose} className="p-1 text-gray-500 hover:text-gray-300">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Instance name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} className="input w-full" required />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Mode</label>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as 'paper' | 'live')}
              className="input w-full"
            >
              <option value="paper">Paper (simulated fills, real ticks)</option>
              <option value="live">Live (real orders — requires Zerodha connected)</option>
            </select>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Instruments (comma-separated)</label>
            <input
              value={instruments}
              onChange={(e) => setInstruments(e.target.value)}
              className="input w-full font-mono"
              placeholder="NIFTY, RELIANCE"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Timeframe</label>
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className="input w-full">
                {['1m', '5m', '15m', '30m', '1h', '1d'].map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Capital (₹)</label>
              <input
                type="number"
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
                className="input w-full"
                min={1000}
              />
            </div>
          </div>

          {strategy.params_schema.length > 0 && (
            <div>
              <label className="block text-sm text-gray-400 mb-2">Parameters</label>
              <div className="space-y-2">
                {strategy.params_schema.map((p) => (
                  <ParamInput key={p.name} spec={p} value={params[p.name]} onChange={(v) => setParams({ ...params, [p.name]: v })} />
                ))}
              </div>
            </div>
          )}

          {error && <p className="text-sm text-red-400">{error}</p>}

          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose} className="flex-1 px-4 py-2 rounded-md text-sm border border-gray-700 text-gray-400 hover:text-gray-200">
              Cancel
            </button>
            <button type="submit" disabled={loading} className="flex-1 btn-primary">
              {loading ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ParamInput({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpec
  value: unknown
  onChange: (v: unknown) => void
}) {
  const id = `param-${spec.name}`
  return (
    <div className="flex items-center gap-3">
      <label htmlFor={id} className="text-xs text-gray-400 w-24 flex-shrink-0">
        {spec.name}
        {spec.description && (
          <span className="block text-gray-600 text-[10px]">{spec.description}</span>
        )}
      </label>
      {spec.type === 'bool' ? (
        <input
          id={id}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="accent-brand-500"
        />
      ) : spec.choices ? (
        <select
          id={id}
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          className="input flex-1 text-xs py-1"
        >
          {spec.choices.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      ) : (
        <input
          id={id}
          type={spec.type === 'int' || spec.type === 'float' ? 'number' : 'text'}
          value={String(value ?? '')}
          onChange={(e) =>
            onChange(spec.type === 'int' ? parseInt(e.target.value) : spec.type === 'float' ? parseFloat(e.target.value) : e.target.value)
          }
          min={spec.min}
          max={spec.max}
          step={spec.type === 'float' ? 0.01 : 1}
          className="input flex-1 text-xs py-1 font-mono"
        />
      )}
    </div>
  )
}

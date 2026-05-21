import { useEffect, useState } from 'react'
import { Plus, RefreshCw, Pause, Play, Trash2, X } from 'lucide-react'
import { api, type CreateInstanceRequest, type ParamSpec, type StrategyClass, type StrategyInstance } from '../lib/api'
import { Badge, SegmentedControl, fmtINR } from '../components/ui'

// Re-use lucide Gear as Settings icon
import { Settings as GearIcon } from 'lucide-react'

export default function Strategies() {
  const [strategies, setStrategies] = useState<StrategyClass[]>([])
  const [instances, setInstances] = useState<StrategyInstance[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'instances' | 'classes' | 'archived'>('instances')
  const [newInstanceFor, setNewInstanceFor] = useState<StrategyClass | null>(null)

  const loadAll = async () => {
    setLoading(true)
    try {
      const [sc, inst] = await Promise.all([api.strategies.classes(), api.instances.list()])
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
    try { await api.strategies.reload(); await loadAll() }
    catch (e) { console.error(e); setLoading(false) }
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
    } catch (e) { alert(e instanceof Error ? e.message : 'Start failed') }
  }

  const handleStop = async (id: string) => {
    try { await api.instances.stop(id); await loadAll() }
    catch (e) { alert(e instanceof Error ? e.message : 'Stop failed') }
  }

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete instance "${name}"?`)) return
    try { await api.instances.delete(id); await loadAll() }
    catch (e) { alert(e instanceof Error ? e.message : 'Delete failed') }
  }

  return (
    <div className="stack">
      <div className="h-page">
        <div>
          <h1>Strategies</h1>
          <div className="sub">Discoverable plugins from <code>strategies/</code>. Drop a Python file, click reload.</div>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={reload} disabled={loading}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Reload plugins
          </button>
          <button className="btn primary" onClick={() => strategies[0] && setNewInstanceFor(strategies[0])}>
            <Plus size={13} /> New instance
          </button>
        </div>
      </div>

      {/* Plugin errors */}
      {Object.keys(errors).length > 0 && (
        <div className="card card-pad" style={{ borderColor: 'color-mix(in srgb, var(--warn) 30%, transparent)', background: 'var(--warn-dim)' }}>
          <div style={{ fontSize: 12, color: 'var(--warn)', marginBottom: 6 }}>Plugin load errors</div>
          {Object.entries(errors).map(([k, v]) => (
            <div key={k} className="faint" style={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}>{k}: {v}</div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="tabs">
        <div className={`tab ${tab === 'instances' ? 'active' : ''}`} onClick={() => setTab('instances')}>
          Instances <span className="count">{instances.length}</span>
        </div>
        <div className={`tab ${tab === 'classes' ? 'active' : ''}`} onClick={() => setTab('classes')}>
          Classes <span className="count">{strategies.length}</span>
        </div>
        <div className={`tab ${tab === 'archived' ? 'active' : ''}`} onClick={() => setTab('archived')}>
          Archived <span className="count">0</span>
        </div>
      </div>

      {/* Instances tab */}
      {tab === 'instances' && (
        instances.length === 0 ? (
          <div className="card card-pad" style={{ textAlign: 'center', padding: 40 }}>
            <div style={{ fontSize: 13, color: 'var(--text-faint)' }}>No instances yet</div>
            <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 6 }}>
              Go to{' '}
              <button onClick={() => setTab('classes')} style={{ background: 'none', border: 0, color: 'var(--text)', cursor: 'pointer', textDecoration: 'underline' }}>
                Classes
              </button>{' '}
              tab and click "New Instance"
            </div>
          </div>
        ) : (
          <div className="grid-2">
            {instances.map(inst => (
              <InstanceCard
                key={inst.id}
                inst={inst}
                onStart={() => handleStart(inst.id)}
                onStop={() => handleStop(inst.id)}
                onDelete={() => handleDelete(inst.id, inst.name)}
                onConfigure={() => {
                  const cls = strategies.find(s => s.name === inst.strategy_class_name)
                  if (cls) setNewInstanceFor(cls)
                }}
              />
            ))}
          </div>
        )
      )}

      {/* Classes tab */}
      {tab === 'classes' && (
        strategies.length === 0 && !loading ? (
          <div className="card card-pad" style={{ textAlign: 'center', padding: 40 }}>
            <div style={{ fontSize: 13, color: 'var(--text-faint)' }}>No strategies found</div>
            <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 6 }}>
              Drop a <code>.py</code> file in <code>strategies/</code> and click Reload
            </div>
          </div>
        ) : (
          <div className="grid-3">
            {strategies.map(s => (
              <div key={s.name} className="card card-pad">
                <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontWeight: 500, fontSize: 14 }}>{s.name}</span>
                  <span className="faint" style={{ fontSize: 10 }}>v{s.version}</span>
                </div>
                <p className="dim" style={{ fontSize: 11.5, margin: '0 0 14px', lineHeight: 1.55 }}>
                  {s.description || 'No description'}
                </p>
                <div className="row" style={{ gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
                  <Badge>{s.timeframe}</Badge>
                  <Badge>{s.params_schema.length} params</Badge>
                  {s.author && <Badge>{s.author}</Badge>}
                </div>
                <button className="btn ghost sm" onClick={() => setNewInstanceFor(s)}>
                  <Plus size={11} /> New instance
                </button>
              </div>
            ))}
          </div>
        )
      )}

      {/* Archived tab */}
      {tab === 'archived' && (
        <div className="card card-pad" style={{ textAlign: 'center', padding: 40 }}>
          <div style={{ fontSize: 13, color: 'var(--text-faint)' }}>No archived instances</div>
        </div>
      )}

      {newInstanceFor && (
        <NewInstanceModal
          strategy={newInstanceFor}
          onClose={() => setNewInstanceFor(null)}
          onCreated={() => { setNewInstanceFor(null); loadAll() }}
        />
      )}
    </div>
  )
}

// ── Instance card ──────────────────────────────────────────────────────────

function InstanceCard({
  inst,
  onStart,
  onStop,
  onDelete,
  onConfigure,
}: {
  inst: StrategyInstance
  onStart: () => void
  onStop: () => void
  onDelete: () => void
  onConfigure: () => void
}) {
  const running = inst.status === 'running'
  const errored = inst.status === 'error'

  return (
    <div className="card">
      <div className="card-pad">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 500, fontSize: 14, marginBottom: 4 }}>{inst.name}</div>
            <div className="faint" style={{ fontSize: 11 }}>
              {inst.strategy_class_name} · {inst.timeframe} · {inst.instruments.join(', ')}
            </div>
          </div>
          <div className="row" style={{ gap: 6, flexShrink: 0 }}>
            <Badge tone={inst.mode === 'live' ? 'pos' : undefined}>{inst.mode}</Badge>
            <Badge
              tone={running ? 'pos' : errored ? 'neg' : undefined}
              dot={running}
            >
              {inst.status}
            </Badge>
          </div>
        </div>

        {inst.last_error && (
          <div style={{
            fontSize: 11, color: 'var(--neg)', background: 'var(--neg-dim)',
            padding: '8px 10px', borderRadius: 7, marginBottom: 12,
            border: '1px solid color-mix(in srgb, var(--neg) 30%, transparent)',
          }}>
            {inst.last_error}
          </div>
        )}

        {/* Capital / Trades / P&L stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 14 }}>
          <div>
            <div className="faint" style={{ fontSize: 9.5, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 3 }}>Capital</div>
            <div className="mono-num" style={{ fontSize: 13 }}>{fmtINR(inst.capital_allocation)}</div>
          </div>
          <div>
            <div className="faint" style={{ fontSize: 9.5, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 3 }}>Trades</div>
            <div className="mono-num" style={{ fontSize: 13 }}>{inst.trade_count ?? '—'}</div>
          </div>
          <div>
            <div className="faint" style={{ fontSize: 9.5, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 3 }}>P&amp;L</div>
            <div
              className={`mono-num ${inst.pnl != null && inst.pnl > 0 ? 'pos' : inst.pnl != null && inst.pnl < 0 ? 'neg' : 'faint'}`}
              style={{ fontSize: 13 }}
            >
              {inst.pnl != null ? fmtINR(inst.pnl, { signed: true }) : '—'}
            </div>
          </div>
        </div>
      </div>

      <div className="row" style={{ borderTop: '1px solid var(--border)', padding: '10px 18px', gap: 8 }}>
        {running
          ? <button className="btn sm" onClick={onStop}><Pause size={11} /> Stop</button>
          : <button className="btn sm primary" onClick={onStart}><Play size={11} /> Start</button>}
        <button className="btn ghost sm" onClick={onConfigure}><GearIcon size={11} /> Configure</button>
        <div style={{ flex: 1 }} />
        {!running && (
          <button
            className="icon-btn"
            onClick={onDelete}
            title="Delete"
            style={{ width: 28, height: 28 }}
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>
    </div>
  )
}

// ── New Instance Modal ─────────────────────────────────────────────────────

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
    Object.fromEntries(strategy.params_schema.map(p => [p.name, p.default]))
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
        instruments: instruments.split(',').map(s => s.trim()).filter(Boolean),
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
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        backdropFilter: 'blur(4px)', zIndex: 100,
        display: 'grid', placeItems: 'center', padding: 20,
      }}
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-elev)', border: '1px solid var(--border-strong)',
          borderRadius: 14, width: '100%', maxWidth: 520,
          maxHeight: '90vh', overflow: 'auto',
          boxShadow: '0 40px 100px -20px rgba(0,0,0,0.6)',
        }}
      >
        <div className="card-head">
          <div>
            <div className="title" style={{ color: 'var(--text-dim)' }}>NEW INSTANCE</div>
            <div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{strategy.name}</div>
          </div>
          <button className="icon-btn" onClick={onClose}><X size={14} /></button>
        </div>

        <form onSubmit={handleSubmit} style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="field">
            <label>Instance name</label>
            <input className="input" value={name} onChange={e => setName(e.target.value)} required />
          </div>

          <div className="field">
            <label>Mode</label>
            <SegmentedControl
              options={[{ value: 'paper', label: 'Paper' }, { value: 'live', label: 'Live' }]}
              value={mode}
              onChange={v => setMode(v as 'paper' | 'live')}
            />
          </div>

          <div className="field">
            <label>Instruments (comma-separated)</label>
            <input className="input" value={instruments} onChange={e => setInstruments(e.target.value)} placeholder="NIFTY, RELIANCE" />
          </div>

          <div className="grid-2">
            <div className="field">
              <label>Timeframe</label>
              <select className="input" value={timeframe} onChange={e => setTimeframe(e.target.value)}>
                {['1m', '5m', '15m', '30m', '1h', '1d'].map(tf => <option key={tf} value={tf}>{tf}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Capital (₹)</label>
              <input className="input" type="number" value={capital} onChange={e => setCapital(e.target.value)} min={1000} />
            </div>
          </div>

          {strategy.params_schema.length > 0 && (
            <>
              <hr className="hr" />
              <div className="field">
                <label>Parameters</label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {strategy.params_schema.map(p => (
                    <ParamInput
                      key={p.name}
                      spec={p}
                      value={params[p.name]}
                      onChange={v => setParams({ ...params, [p.name]: v })}
                    />
                  ))}
                </div>
              </div>
            </>
          )}

          {error && <p style={{ fontSize: 11.5, color: 'var(--neg)', margin: 0 }}>{error}</p>}

          <div className="row" style={{ marginTop: 6 }}>
            <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
            <div style={{ flex: 1 }} />
            <button type="submit" className="btn primary" disabled={loading}>
              {loading ? 'Creating…' : 'Create instance'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ParamInput({ spec, value, onChange }: { spec: ParamSpec; value: unknown; onChange: (v: unknown) => void }) {
  return (
    <div className="row" style={{ gap: 10 }}>
      <span className="dim" style={{ fontSize: 11.5, width: 110, flexShrink: 0 }}>
        {spec.name}
      </span>
      {spec.type === 'bool' ? (
        <input type="checkbox" checked={Boolean(value)} onChange={e => onChange(e.target.checked)} />
      ) : spec.choices ? (
        <select className="input" style={{ flex: 1, fontSize: 11.5 }} value={String(value)} onChange={e => onChange(e.target.value)}>
          {spec.choices.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      ) : (
        <input
          className="input"
          style={{ flex: 1, fontSize: 11.5 }}
          type={spec.type === 'int' || spec.type === 'float' ? 'number' : 'text'}
          value={String(value ?? '')}
          onChange={e => onChange(
            spec.type === 'int' ? parseInt(e.target.value)
            : spec.type === 'float' ? parseFloat(e.target.value)
            : e.target.value
          )}
          min={spec.min}
          max={spec.max}
          step={spec.type === 'float' ? 0.01 : 1}
        />
      )}
    </div>
  )
}

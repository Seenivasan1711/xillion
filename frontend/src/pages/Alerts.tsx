import { useEffect, useState } from 'react'
import { Bell, CheckCircle, RefreshCw, Search } from 'lucide-react'
import { api, type SignalLogEntry } from '../lib/api'
import { Badge, fmtTime } from '../components/ui'

export default function Alerts() {
  const [signals, setSignals] = useState<SignalLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.signals.list({ limit: 200 })
      setSignals(res.signals)
    } catch {
      // keep existing list on error
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [])

  // An ENTER is still open if no EXIT in the current window references it.
  const closedParentIds = new Set(signals.map(s => s.parent_signal_id).filter((id): id is number => id != null))

  const filtered = signals.filter(s => {
    if (!filter) return true
    const f = filter.toLowerCase()
    return (
      s.underlying_symbol.toLowerCase().includes(f) ||
      (s.strategy_instance_name ?? '').toLowerCase().includes(f) ||
      (s.tag ?? '').toLowerCase().includes(f)
    )
  })

  const openCount = signals.filter(s => s.signal_type === 'ENTER' && !closedParentIds.has(s.id)).length

  const typeTone = (t: SignalLogEntry['signal_type']) =>
    t === 'ENTER' ? 'warn' : t === 'EXIT' ? 'pos' : undefined

  return (
    <div className="stack">
      <div className="h-page">
        <div>
          <h1>Alerts</h1>
          <div className="sub">Signal history — entries, their target/stop-loss, and the exits that close them</div>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={load} disabled={loading}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid-4">
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Signals</div>
          <div className="hero-num sm">{signals.length}</div>
        </div>
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Open entries</div>
          <div className="hero-num sm">{openCount}</div>
        </div>
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Notified</div>
          <div className="hero-num sm">{signals.filter(s => s.notified).length}</div>
        </div>
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Symbols</div>
          <div className="hero-num sm">{new Set(signals.map(s => s.underlying_symbol)).size}</div>
        </div>
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        <div className="card-head">
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            background: 'var(--surface-2)', border: '1px solid var(--border)',
            borderRadius: 8, padding: '0 10px', height: 28,
          }}>
            <Search size={12} style={{ color: 'var(--text-faint)', flexShrink: 0 }} />
            <input
              placeholder="filter symbol, strategy, or tag…"
              value={filter}
              onChange={e => setFilter(e.target.value)}
              style={{
                background: 'transparent', border: 0, outline: 'none',
                fontFamily: 'var(--font-mono)', fontSize: 11.5,
                color: 'var(--text)', width: 220,
              }}
            />
          </div>
          <Badge tone="pos" dot>polling</Badge>
        </div>

        {loading && signals.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-faint)' }}>Loading signals…</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-faint)' }}>
            <Bell size={20} style={{ color: 'var(--text-faint)', marginBottom: 8 }} />
            <div>{signals.length === 0 ? 'No signals yet — run a strategy in alert mode to see them here' : 'No signals match your filter'}</div>
          </div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Time</th>
                <th>Strategy</th>
                <th>Symbol</th>
                <th>Type</th>
                <th>Side</th>
                <th className="num">Price</th>
                <th className="num">Target</th>
                <th className="num">Stop-loss</th>
                <th>Linked</th>
                <th>Sent</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(s => {
                const isOpenEntry = s.signal_type === 'ENTER' && !closedParentIds.has(s.id)
                return (
                  <tr key={s.id}>
                    <td className="faint mono-num" style={{ fontSize: 11 }}>{fmtTime(s.ts)}</td>
                    <td className="dim" style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {s.strategy_instance_name ?? s.strategy_instance_id}
                    </td>
                    <td style={{ fontWeight: 500 }}>{s.underlying_symbol}</td>
                    <td>
                      <Badge tone={typeTone(s.signal_type)}>
                        {s.signal_type}{isOpenEntry ? ' · open' : ''}
                      </Badge>
                    </td>
                    <td>
                      {s.side && (
                        <span style={{ color: s.side === 'BUY' ? 'var(--pos)' : 'var(--neg)', fontWeight: 500, fontSize: 11 }}>
                          {s.side}
                        </span>
                      )}
                    </td>
                    <td className="num mono-num">{s.price != null ? `₹${s.price.toFixed(2)}` : '—'}</td>
                    <td className="num mono-num pos">{s.target_price != null ? `₹${s.target_price.toFixed(2)}` : '—'}</td>
                    <td className="num mono-num neg">{s.stop_loss_price != null ? `₹${s.stop_loss_price.toFixed(2)}` : '—'}</td>
                    <td className="faint" style={{ fontSize: 10.5 }}>
                      {s.parent_signal_id != null ? `closes #${s.parent_signal_id}` : (s.tag ?? '—')}
                    </td>
                    <td>
                      {s.notified
                        ? <CheckCircle size={13} style={{ color: 'var(--pos)' }} />
                        : <span className="faint" style={{ fontSize: 11 }}>—</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

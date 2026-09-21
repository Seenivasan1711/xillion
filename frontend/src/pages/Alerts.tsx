import { Fragment, useEffect, useState } from 'react'
import { Bell, CheckCircle, ChevronDown, ChevronUp, RefreshCw, Search } from 'lucide-react'
import { api, type SignalLogEntry } from '../lib/api'
import { Badge, fmtTime, SkeletonRows } from '../components/ui'

// XAUUSD (and any other non-INR symbol later) quotes in $, not ₹ -- this
// page originally only ever showed NIFTY/options signals, all ₹.
function fmtPrice(symbol: string, price: number | null): string {
  if (price == null) return '—'
  const ccy = symbol.toUpperCase().includes('XAU') || symbol.toUpperCase().includes('USD') ? '$' : '₹'
  return `${ccy}${price.toFixed(2)}`
}

const ACTION_TONE: Record<string, 'pos' | 'neg' | undefined> = { TAKEN: 'pos', SKIPPED: undefined }
const OUTCOME_TONE: Record<string, 'pos' | 'neg' | 'warn' | undefined> = {
  WIN: 'pos', LOSS: 'neg', BREAKEVEN: 'warn',
}

function SignalRow({ s, expanded, onToggle, onSaved }: {
  s: SignalLogEntry
  expanded: boolean
  onToggle: () => void
  onSaved: () => void
}) {
  const [busy, setBusy] = useState(false)

  const act = async (action: 'TAKEN' | 'SKIPPED') => {
    setBusy(true)
    try {
      await api.signals.setAction(s.id, action)
      onSaved()
    } finally {
      setBusy(false)
    }
  }

  const recordOutcome = async (outcome: 'WIN' | 'LOSS' | 'BREAKEVEN') => {
    setBusy(true)
    try {
      await api.signals.setOutcome(s.id, outcome)
      onSaved()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="row" style={{ gap: 10, padding: '10px 16px', flexWrap: 'wrap', alignItems: 'center' }}>
      <button
        className="btn ghost sm" onClick={onToggle}
        style={{ display: 'flex', alignItems: 'center', gap: 4 }}
      >
        {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />} reasoning
      </button>

      {s.user_action == null ? (
        <>
          <button className="btn sm" onClick={() => act('TAKEN')} disabled={busy}>I took this</button>
          <button className="btn ghost sm" onClick={() => act('SKIPPED')} disabled={busy}>Skipped</button>
        </>
      ) : (
        <Badge tone={ACTION_TONE[s.user_action]}>{s.user_action}</Badge>
      )}

      {s.user_action === 'TAKEN' && (
        s.outcome == null ? (
          <div className="row" style={{ gap: 6 }}>
            <span className="faint" style={{ fontSize: 11 }}>How'd it go?</span>
            <button className="btn ghost sm" onClick={() => recordOutcome('WIN')} disabled={busy}>Win</button>
            <button className="btn ghost sm" onClick={() => recordOutcome('LOSS')} disabled={busy}>Loss</button>
            <button className="btn ghost sm" onClick={() => recordOutcome('BREAKEVEN')} disabled={busy}>Breakeven</button>
          </div>
        ) : (
          <Badge tone={OUTCOME_TONE[s.outcome]}>{s.outcome}</Badge>
        )
      )}

      {expanded && (
        <div style={{ flexBasis: '100%', fontSize: 12, whiteSpace: 'pre-wrap', color: 'var(--text-dim)', paddingTop: 4 }}>
          {s.message}
        </div>
      )}
    </div>
  )
}

export default function Alerts() {
  const [signals, setSignals] = useState<SignalLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

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
          <div style={{ padding: '16px 18px' }}><SkeletonRows rows={6} cols={5} /></div>
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
                  <Fragment key={s.id}>
                    <tr>
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
                      <td className="num mono-num">{fmtPrice(s.underlying_symbol, s.price)}</td>
                      <td className="num mono-num pos">{fmtPrice(s.underlying_symbol, s.target_price)}</td>
                      <td className="num mono-num neg">{fmtPrice(s.underlying_symbol, s.stop_loss_price)}</td>
                      <td className="faint" style={{ fontSize: 10.5 }}>
                        {s.parent_signal_id != null ? `closes #${s.parent_signal_id}` : (s.tag ?? '—')}
                      </td>
                      <td>
                        {s.notified
                          ? <CheckCircle size={13} style={{ color: 'var(--pos)' }} />
                          : <span className="faint" style={{ fontSize: 11 }}>—</span>}
                      </td>
                    </tr>
                    {s.signal_type === 'ENTER' && (
                      <tr>
                        <td colSpan={9} style={{ background: 'var(--surface-2)', padding: 0 }}>
                          <SignalRow
                            s={s}
                            expanded={expandedId === s.id}
                            onToggle={() => setExpandedId(expandedId === s.id ? null : s.id)}
                            onSaved={load}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

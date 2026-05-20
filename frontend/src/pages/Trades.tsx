import { useEffect, useRef, useState } from 'react'
import { Download, RefreshCw, Search } from 'lucide-react'
import { api, MatchedTrade } from '../lib/api'
import { wsClient } from '../lib/ws'
import { Badge, SegmentedControl, fmtINR, fmtTime } from '../components/ui'

export default function Trades() {
  const [trades, setTrades] = useState<MatchedTrade[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [direction, setDirection] = useState('all')
  const wsIdRef = useRef(0)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.trades.list()
      setTrades(res.trades)
    } catch {
      // keep existing list on error
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()

    const unsub = wsClient.subscribe((event) => {
      if (event.type !== 'trade_closed') return
      const t: MatchedTrade = {
        id: `ws-${++wsIdRef.current}`,
        symbol: (event.symbol as string) || '',
        instance_id: (event.instance_id as string) || '',
        instance_name: (event.instance_name as string) || 'Unknown',
        side: (event.side as 'LONG' | 'SHORT') || 'LONG',
        quantity: Number(event.quantity) || 0,
        entry_price: Number(event.entry_price) || 0,
        exit_price: Number(event.exit_price) || 0,
        entry_ts: (event.entry_ts as string) || new Date().toISOString(),
        exit_ts: (event.exit_ts as string) || new Date().toISOString(),
        pnl: Number(event.pnl) || 0,
        mode: (event.mode as 'paper' | 'live') || 'paper',
      }
      setTrades(prev => [t, ...prev])
    })
    return unsub
  }, [])

  const filtered = trades.filter(t => {
    if (direction !== 'all' && t.side !== direction) return false
    if (filter) {
      const f = filter.toLowerCase()
      if (!t.symbol.toLowerCase().includes(f) && !t.instance_name.toLowerCase().includes(f)) return false
    }
    return true
  })

  const totalPnl = filtered.reduce((s, t) => s + t.pnl, 0)
  const wins = filtered.filter(t => t.pnl > 0).length
  const winRate = filtered.length > 0 ? Math.round((wins / filtered.length) * 100) : 0
  const avgPnl = filtered.length > 0 ? totalPnl / filtered.length : 0

  const exportCsv = () => {
    const header = 'Exit Time,Strategy,Symbol,Direction,Qty,Entry Price,Exit Price,P&L,Mode'
    const rows = filtered.map(t => [
      t.exit_ts, t.instance_name, t.symbol, t.side,
      t.quantity, t.entry_price, t.exit_price, t.pnl, t.mode,
    ].join(','))
    const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `xillion-trades-${Date.now()}.csv`
    a.click()
  }

  return (
    <div className="stack">
      <div className="h-page">
        <div>
          <h1>Trades</h1>
          <div className="sub">Closed round-trip trades — entry / exit matched</div>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={load} disabled={loading}>
            <RefreshCw size={13} /> Refresh
          </button>
          <button className="btn ghost" onClick={exportCsv} disabled={trades.length === 0}>
            <Download size={13} /> Export CSV
          </button>
        </div>
      </div>

      {/* Stat strip */}
      <div className="grid-4">
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Total trades</div>
          <div className="hero-num sm">{filtered.length}</div>
        </div>
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Total P&L</div>
          <div className={`hero-num sm ${totalPnl >= 0 ? 'pos' : 'neg'}`}>{fmtINR(totalPnl, { signed: true })}</div>
        </div>
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Avg P&L / trade</div>
          <div className={`hero-num sm ${avgPnl >= 0 ? 'pos' : 'neg'}`}>{fmtINR(avgPnl, { signed: true })}</div>
        </div>
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Win rate</div>
          <div className="hero-num sm">
            {winRate}<span className="faint" style={{ fontSize: 18 }}>%</span>
          </div>
          <div className="prog" style={{ marginTop: 10 }}>
            <span style={{ width: `${winRate}%` }} />
          </div>
        </div>
      </div>

      {/* Table with embedded filter */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div className="card-head">
          <div className="row" style={{ gap: 10 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--surface-2)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '0 10px', height: 28,
            }}>
              <Search size={12} style={{ color: 'var(--text-faint)', flexShrink: 0 }} />
              <input
                placeholder="filter symbol or strategy…"
                value={filter}
                onChange={e => setFilter(e.target.value)}
                style={{
                  background: 'transparent', border: 0, outline: 'none',
                  fontFamily: 'var(--font-mono)', fontSize: 11.5,
                  color: 'var(--text)', width: 180,
                }}
              />
            </div>
            <SegmentedControl
              options={[{ value: 'all', label: 'All' }, { value: 'LONG', label: 'Long' }, { value: 'SHORT', label: 'Short' }]}
              value={direction}
              onChange={setDirection}
            />
          </div>
          <Badge tone="pos" dot>live</Badge>
        </div>

        {loading ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-faint)' }}>Loading trades…</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-faint)' }}>
            {trades.length === 0
              ? 'No closed trades yet — run a strategy to see matched round-trips here'
              : 'No trades match your filter'}
          </div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Exit Time</th>
                <th>Strategy</th>
                <th>Symbol</th>
                <th>Direction</th>
                <th className="num">Qty</th>
                <th className="num">Entry</th>
                <th className="num">Exit</th>
                <th className="num">P&amp;L</th>
                <th>Mode</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(t => (
                <tr key={t.id}>
                  <td className="faint mono-num" style={{ fontSize: 11 }}>{fmtTime(t.exit_ts)}</td>
                  <td className="dim" style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.instance_name}</td>
                  <td style={{ fontWeight: 500 }}>{t.symbol}</td>
                  <td>
                    <span style={{ color: t.side === 'LONG' ? 'var(--pos)' : 'var(--neg)', fontWeight: 500, fontSize: 11 }}>
                      {t.side === 'LONG' ? '▲' : '▼'} {t.side}
                    </span>
                  </td>
                  <td className="num mono-num">{t.quantity}</td>
                  <td className="num mono-num">₹{t.entry_price.toFixed(2)}</td>
                  <td className="num mono-num">₹{t.exit_price.toFixed(2)}</td>
                  <td className={`num mono-num ${t.pnl >= 0 ? 'pos' : 'neg'}`}>
                    {fmtINR(t.pnl, { signed: true })}
                  </td>
                  <td><Badge tone={t.mode === 'live' ? 'pos' : undefined}>{t.mode}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

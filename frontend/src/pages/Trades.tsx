import { useEffect, useRef, useState } from 'react'
import { Download, Trash2, Search } from 'lucide-react'
import { wsClient } from '../lib/ws'
import { Badge, SegmentedControl, fmtINR, fmtTime } from '../components/ui'

interface Trade {
  id: number
  ts: string
  instance_id: string
  instance_name: string
  symbol: string
  side: 'BUY' | 'SELL'
  qty: number
  price: number
  pnl: number | null
  mode: 'paper' | 'live'
  order_id: string
}

export default function Trades() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [filter, setFilter] = useState('')
  const [side, setSide] = useState('all')
  const idRef = useRef(0)

  useEffect(() => {
    const unsub = wsClient.subscribe((event) => {
      if (event.type !== 'trade') return
      const t: Trade = {
        id: ++idRef.current,
        ts: (event.ts as string) || new Date().toISOString(),
        instance_id: (event.instance_id as string) || '',
        instance_name: (event.instance_name as string) || 'Unknown',
        symbol: (event.symbol as string) || '',
        side: (event.side as 'BUY' | 'SELL') || 'BUY',
        qty: Number(event.qty) || 0,
        price: Number(event.price) || 0,
        pnl: event.pnl != null ? Number(event.pnl) : null,
        mode: (event.mode as 'paper' | 'live') || 'paper',
        order_id: (event.order_id as string) || '',
      }
      setTrades(prev => [t, ...prev.slice(0, 499)])
    })
    return unsub
  }, [])

  const filtered = trades.filter(t => {
    if (side !== 'all' && t.side !== side) return false
    if (filter) {
      const f = filter.toLowerCase()
      if (!t.symbol.toLowerCase().includes(f) && !t.instance_name.toLowerCase().includes(f)) return false
    }
    return true
  })

  const total = filtered.reduce((s, t) => s + (t.pnl ?? 0), 0)
  const buys = filtered.filter(t => t.side === 'BUY').length
  const sells = filtered.length - buys
  const wins = filtered.filter(t => (t.pnl ?? 0) > 0).length
  const winRate = filtered.length > 0 ? Math.round((wins / filtered.length) * 100) : 0

  const exportCsv = () => {
    const header = 'Time,Instance,Symbol,Side,Qty,Price,PnL,Mode,OrderID'
    const rows = filtered.map(t => [t.ts, t.instance_name, t.symbol, t.side, t.qty, t.price, t.pnl ?? '', t.mode, t.order_id].join(','))
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
          <div className="sub">Real-time order stream — paper + live combined</div>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={exportCsv} disabled={trades.length === 0}>
            <Download size={13} /> Export CSV
          </button>
          <button className="btn ghost" onClick={() => setTrades([])} disabled={trades.length === 0}>
            <Trash2 size={13} /> Clear feed
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
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Session P&L</div>
          <div className={`hero-num sm ${total >= 0 ? 'pos' : 'neg'}`}>{fmtINR(total, { signed: true })}</div>
        </div>
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Buy / Sell</div>
          <div className="hero-num sm">
            <span className="pos">{buys}</span>
            <span className="faint"> / </span>
            <span className="neg">{sells}</span>
          </div>
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
            {/* Search input */}
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
              options={[{ value: 'all', label: 'All' }, { value: 'BUY', label: 'BUY' }, { value: 'SELL', label: 'SELL' }]}
              value={side}
              onChange={setSide}
            />
          </div>
          <Badge tone="pos" dot>streaming</Badge>
        </div>

        {filtered.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-faint)' }}>
            {trades.length === 0
              ? 'No trades yet — trades appear here as strategies execute orders'
              : 'No trades match your filter'}
          </div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Time</th>
                <th>Strategy</th>
                <th>Symbol</th>
                <th>Side</th>
                <th className="num">Qty</th>
                <th className="num">Price</th>
                <th className="num">P&amp;L</th>
                <th>Mode</th>
                <th>Order ID</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(t => (
                <tr key={t.id}>
                  <td className="faint mono-num" style={{ fontSize: 11 }}>{fmtTime(t.ts)}</td>
                  <td className="dim" style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.instance_name}</td>
                  <td style={{ fontWeight: 500 }}>{t.symbol}</td>
                  <td>
                    <span style={{ color: t.side === 'BUY' ? 'var(--pos)' : 'var(--neg)', fontWeight: 500, fontSize: 11 }}>
                      {t.side === 'BUY' ? '▲' : '▼'} {t.side}
                    </span>
                  </td>
                  <td className="num mono-num">{t.qty}</td>
                  <td className="num mono-num">₹{t.price.toFixed(2)}</td>
                  <td className={`num mono-num ${t.pnl == null ? 'faint' : t.pnl >= 0 ? 'pos' : 'neg'}`}>
                    {t.pnl == null ? '—' : fmtINR(t.pnl, { signed: true })}
                  </td>
                  <td><Badge tone={t.mode === 'live' ? 'pos' : undefined}>{t.mode}</Badge></td>
                  <td className="faint mono-num" style={{ fontSize: 10.5 }}>{t.order_id || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

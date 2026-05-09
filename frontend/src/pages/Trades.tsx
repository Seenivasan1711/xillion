import { useEffect, useRef, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, Download, TrendingUp } from 'lucide-react'
import { wsClient } from '../lib/ws'

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
      setTrades((prev) => [t, ...prev.slice(0, 499)])
    })
    return unsub
  }, [])

  const filtered = filter
    ? trades.filter(
        (t) =>
          t.symbol.toLowerCase().includes(filter.toLowerCase()) ||
          t.instance_name.toLowerCase().includes(filter.toLowerCase())
      )
    : trades

  const totalPnl = filtered.reduce((sum, t) => sum + (t.pnl ?? 0), 0)

  const exportCsv = () => {
    const header = 'Time,Instance,Symbol,Side,Qty,Price,PnL,Mode,OrderID'
    const rows = filtered.map((t) =>
      [
        t.ts,
        t.instance_name,
        t.symbol,
        t.side,
        t.qty,
        t.price,
        t.pnl ?? '',
        t.mode,
        t.order_id,
      ].join(',')
    )
    const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `xillion-trades-${Date.now()}.csv`
    a.click()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <TrendingUp size={22} />
          Trades
        </h1>
        <div className="flex items-center gap-2">
          {trades.length > 0 && (
            <button onClick={exportCsv} className="p-2 text-gray-500 hover:text-gray-300" title="Export CSV">
              <Download size={16} />
            </button>
          )}
          {trades.length > 0 && (
            <button onClick={() => setTrades([])} className="text-xs text-gray-500 hover:text-gray-300">
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Summary */}
      {trades.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="card text-center">
            <div className="text-2xl font-bold">{filtered.length}</div>
            <div className="text-xs text-gray-500 mt-1">Trades</div>
          </div>
          <div className="card text-center">
            <div className={`text-2xl font-bold ${totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {totalPnl >= 0 ? '+' : ''}₹{totalPnl.toFixed(2)}
            </div>
            <div className="text-xs text-gray-500 mt-1">Session P&amp;L</div>
          </div>
          <div className="card text-center">
            <div className="text-2xl font-bold">
              {filtered.filter((t) => t.side === 'BUY').length} /{' '}
              {filtered.filter((t) => t.side === 'SELL').length}
            </div>
            <div className="text-xs text-gray-500 mt-1">Buy / Sell</div>
          </div>
        </div>
      )}

      {/* Filter */}
      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter by symbol or strategy…"
        className="input w-full max-w-xs text-sm py-1.5"
      />

      {/* Table */}
      <div className="card overflow-x-auto p-0">
        {filtered.length === 0 ? (
          <div className="py-16 text-center text-gray-600">
            {trades.length === 0
              ? 'No trades yet — trades appear here as strategies execute orders'
              : 'No trades match your filter'}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-500 text-xs">
                <th className="text-left px-4 py-2">Time</th>
                <th className="text-left px-4 py-2">Strategy</th>
                <th className="text-left px-4 py-2">Symbol</th>
                <th className="text-left px-4 py-2">Side</th>
                <th className="text-right px-4 py-2">Qty</th>
                <th className="text-right px-4 py-2">Price</th>
                <th className="text-right px-4 py-2">P&amp;L</th>
                <th className="text-left px-4 py-2">Mode</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => (
                <tr key={t.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="px-4 py-2 text-gray-500 font-mono text-xs tabular-nums">
                    {new Date(t.ts).toLocaleTimeString()}
                  </td>
                  <td className="px-4 py-2 text-gray-300 max-w-[120px] truncate">{t.instance_name}</td>
                  <td className="px-4 py-2 font-medium">{t.symbol}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`inline-flex items-center gap-1 text-xs font-bold ${
                        t.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {t.side === 'BUY' ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                      {t.side}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{t.qty}</td>
                  <td className="px-4 py-2 text-right tabular-nums font-mono">₹{t.price.toFixed(2)}</td>
                  <td className="px-4 py-2 text-right tabular-nums font-mono">
                    {t.pnl != null ? (
                      <span className={t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                        {t.pnl >= 0 ? '+' : ''}₹{t.pnl.toFixed(2)}
                      </span>
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        t.mode === 'live'
                          ? 'bg-emerald-900/40 text-emerald-400'
                          : 'bg-gray-800 text-gray-500'
                      }`}
                    >
                      {t.mode}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

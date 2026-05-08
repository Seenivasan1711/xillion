import { useEffect, useState } from 'react'
import { BarChart2, Play, AlertCircle } from 'lucide-react'
import { api, StrategyClass, BacktestResponse } from '../lib/api'

export default function Backtest() {
  const [strategies, setStrategies] = useState<StrategyClass[]>([])
  const [selectedStrategy, setSelectedStrategy] = useState('')
  const [capital, setCapital] = useState('100000')
  const [slippage, setSlippage] = useState('5')
  const [paramsJson, setParamsJson] = useState('{}')
  const [barsJson, setBarsJson] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BacktestResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.strategies.classes().then((r) => {
      setStrategies(r.strategies)
      if (r.strategies.length > 0) setSelectedStrategy(r.strategies[0].name)
    })
  }, [])

  const run = async () => {
    setError(null)
    setResult(null)
    setRunning(true)
    try {
      const bars = barsJson ? JSON.parse(barsJson) : undefined
      const params = JSON.parse(paramsJson)
      const strategy = strategies.find((s) => s.name === selectedStrategy)
      const instruments = strategy ? (strategy.instruments.length ? strategy.instruments : ['NIFTY']) : ['NIFTY']

      const res = await api.backtest.run({
        strategy_name: selectedStrategy,
        instruments,
        initial_capital: parseFloat(capital),
        slippage_bps: parseInt(slippage),
        params,
        bars,
      })
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setRunning(false)
    }
  }

  const strategy = strategies.find((s) => s.name === selectedStrategy)

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <BarChart2 size={22} />
        Backtest
      </h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Config panel */}
        <div className="lg:col-span-1 space-y-4">
          <div className="card space-y-4">
            <h2 className="font-semibold text-sm text-gray-400 uppercase tracking-wider">Configuration</h2>

            <label className="block">
              <span className="text-sm text-gray-400">Strategy</span>
              <select
                value={selectedStrategy}
                onChange={(e) => {
                  setSelectedStrategy(e.target.value)
                  const s = strategies.find((x) => x.name === e.target.value)
                  if (s) {
                    const defaults = Object.fromEntries(s.params_schema.map((p) => [p.name, p.default]))
                    setParamsJson(JSON.stringify(defaults, null, 2))
                  }
                }}
                className="mt-1 w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white"
              >
                {strategies.map((s) => (
                  <option key={s.name} value={s.name}>{s.name}</option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-sm text-gray-400">Initial Capital (₹)</span>
              <input
                type="number"
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
                className="mt-1 w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white"
              />
            </label>

            <label className="block">
              <span className="text-sm text-gray-400">Slippage (bps)</span>
              <input
                type="number"
                value={slippage}
                onChange={(e) => setSlippage(e.target.value)}
                className="mt-1 w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white"
              />
            </label>

            <label className="block">
              <span className="text-sm text-gray-400">Parameters (JSON)</span>
              <textarea
                rows={4}
                value={paramsJson}
                onChange={(e) => setParamsJson(e.target.value)}
                className="mt-1 w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-xs font-mono text-white resize-none"
              />
            </label>

            <label className="block">
              <span className="text-sm text-gray-400">
                Bars (JSON array) —{' '}
                <span className="text-xs text-gray-500">or leave empty & use /api/backtest/upload-csv</span>
              </span>
              <textarea
                rows={4}
                value={barsJson}
                onChange={(e) => setBarsJson(e.target.value)}
                placeholder='[{"symbol":"NIFTY","ts":"2024-01-15T09:15:00","open":21000,"high":21050,"low":20990,"close":21030,"volume":1000}]'
                className="mt-1 w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-xs font-mono text-white resize-none placeholder-gray-600"
              />
            </label>

            <button
              onClick={run}
              disabled={running || !selectedStrategy || !barsJson}
              className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Play size={14} className={running ? 'animate-pulse' : ''} />
              {running ? 'Running…' : 'Run Backtest'}
            </button>
          </div>
        </div>

        {/* Results panel */}
        <div className="lg:col-span-2">
          {error && (
            <div className="card border-red-800 bg-red-950/30 flex items-start gap-2">
              <AlertCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
              <p className="text-sm text-red-300">{error}</p>
            </div>
          )}

          {result && (
            <div className="space-y-4">
              <div className="card">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-semibold">Results — {result.strategy_name}</h2>
                  <span
                    className={result.status === 'done' ? 'badge-running' : 'badge-error'}
                  >
                    {result.status}
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {[
                    ['Total Return', `${result.metrics.total_return_pct ?? 0}%`],
                    ['Total P&L', `₹${(result.metrics.total_pnl ?? 0).toLocaleString()}`],
                    ['Sharpe', result.metrics.sharpe_ratio ?? 0],
                    ['Sortino', result.metrics.sortino_ratio ?? 0],
                    ['Max DD', `${result.metrics.max_drawdown_pct ?? 0}%`],
                    ['Win Rate', `${result.metrics.win_rate_pct ?? 0}%`],
                    ['Trades', result.trade_count],
                    ['Profit Factor', result.metrics.profit_factor ?? '∞'],
                    ['Expectancy', `₹${(result.metrics.expectancy ?? 0).toLocaleString()}`],
                  ].map(([label, value]) => (
                    <div key={label as string} className="bg-gray-800/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">{label}</div>
                      <div className="font-semibold text-sm">{String(value)}</div>
                    </div>
                  ))}
                </div>
              </div>

              {result.equity_curve.length > 0 && (
                <div className="card">
                  <h3 className="text-sm font-medium text-gray-400 mb-3">Equity Curve</h3>
                  <EquityCurveSpark data={result.equity_curve} />
                </div>
              )}
            </div>
          )}

          {!result && !error && !running && (
            <div className="card text-center py-16 text-gray-500">
              <BarChart2 size={48} className="mx-auto mb-3 opacity-20" />
              <p>Configure a backtest and click Run.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function EquityCurveSpark({ data }: { data: number[] }) {
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const w = 600
  const h = 120
  const pad = 4

  const points = data
    .map((v, i) => {
      const x = pad + (i / (data.length - 1)) * (w - pad * 2)
      const y = h - pad - ((v - min) / range) * (h - pad * 2)
      return `${x},${y}`
    })
    .join(' ')

  const color = data[data.length - 1] >= data[0] ? '#22c55e' : '#ef4444'

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" preserveAspectRatio="none">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

import { useEffect, useRef, useState } from 'react'
import { Play, Upload } from 'lucide-react'
import { api, type BacktestResponse, type BacktestTrade, type StrategyClass, type DataProviderClass } from '../lib/api'
import { Sparkline, Badge, SegmentedControl, fmtINR } from '../components/ui'

function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

export default function Backtest() {
  const [strategies, setStrategies] = useState<StrategyClass[]>([])
  const [selectedStrategy, setSelectedStrategy] = useState('')
  const [capital, setCapital] = useState('100000')
  const [slippage, setSlippage] = useState('5')
  const [timeframe, setTimeframe] = useState('5m')
  const [paramsJson, setParamsJson] = useState('{}')
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BacktestResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Historical bars source
  const [source, setSource] = useState<'csv' | 'provider'>('csv')
  const [providers, setProviders] = useState<DataProviderClass[]>([])
  const [selectedProvider, setSelectedProvider] = useState('')
  const [symbol, setSymbol] = useState('')
  const [exchange, setExchange] = useState('NFO')
  const [instrumentType, setInstrumentType] = useState('option')
  const [fromDate, setFromDate] = useState(isoDaysAgo(60))
  const [toDate, setToDate] = useState(isoDaysAgo(0))

  useEffect(() => {
    api.strategies.classes().then(r => {
      setStrategies(r.strategies)
      if (r.strategies.length > 0) {
        setSelectedStrategy(r.strategies[0].name)
        const defaults = Object.fromEntries(r.strategies[0].params_schema.map(p => [p.name, p.default]))
        setParamsJson(JSON.stringify(defaults, null, 2))
        if (r.strategies[0].timeframe) setTimeframe(r.strategies[0].timeframe)
      }
    })
    api.dataProviders.classes().then(r => {
      setProviders(r.providers)
      if (r.providers.length > 0) setSelectedProvider(r.providers[0].name)
    }).catch(() => {})
  }, [])

  const run = async () => {
    setError(null)
    setResult(null)
    setRunning(true)
    const t0 = Date.now()
    try {
      const params = JSON.parse(paramsJson)
      let res: BacktestResponse
      if (source === 'csv') {
        if (!csvFile) throw new Error('Please choose a CSV file')
        res = await api.backtest.runCsv(csvFile, {
          strategy_name: selectedStrategy,
          instruments: [],
          timeframe,
          initial_capital: parseFloat(capital),
          slippage_bps: parseInt(slippage),
          params,
        })
      } else {
        if (!selectedProvider) throw new Error('Please choose a data provider')
        if (!symbol.trim()) throw new Error('Please enter a symbol')
        res = await api.backtest.runProvider({
          strategy_name: selectedStrategy,
          provider_name: selectedProvider,
          symbol: symbol.trim(),
          exchange,
          instrument_type: instrumentType,
          timeframe,
          from_date: fromDate,
          to_date: toDate,
          initial_capital: parseFloat(capital),
          slippage_bps: parseInt(slippage),
          params,
        })
      }
      // Inject elapsed_seconds if backend didn't return it
      if (!res.elapsed_seconds) (res as BacktestResponse).elapsed_seconds = (Date.now() - t0) / 1000
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setRunning(false)
    }
  }

  const selectedProviderCaps = providers.find(p => p.name === selectedProvider)?.capabilities
  const canRun = source === 'csv' ? !!csvFile : !!selectedProvider && !!symbol.trim()

  const dateRange = result
    ? `${new Date(result.from_ts).toLocaleDateString('en-IN')} → ${new Date(result.to_ts).toLocaleDateString('en-IN')}`
    : null

  return (
    <div className="stack">
      <div className="h-page">
        <div>
          <h1>Backtest</h1>
          <div className="sub">Replay a strategy against historical bars — slippage, fees, equity, metrics.</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 14, alignItems: 'start' }}>
        {/* ── Config panel ── */}
        <div className="card">
          <div className="card-head">
            <span className="title">Configuration</span>
          </div>
          <div className="card-pad stack" style={{ gap: 14 }}>
            <div className="field">
              <label>Strategy</label>
              <select
                className="input"
                value={selectedStrategy}
                onChange={e => {
                  setSelectedStrategy(e.target.value)
                  const s = strategies.find(x => x.name === e.target.value)
                  if (s) {
                    setParamsJson(JSON.stringify(Object.fromEntries(s.params_schema.map(p => [p.name, p.default])), null, 2))
                    if (s.timeframe) setTimeframe(s.timeframe)
                  }
                }}
              >
                {strategies.map(s => <option key={s.name} value={s.name}>{s.name}</option>)}
              </select>
            </div>

            <div className="grid-2">
              <div className="field">
                <label>Capital</label>
                <input className="input" value={capital} onChange={e => setCapital(e.target.value)} />
              </div>
              <div className="field">
                <label>Slippage (bps)</label>
                <input className="input" value={slippage} onChange={e => setSlippage(e.target.value)} />
              </div>
            </div>

            <div className="field">
              <label>Timeframe</label>
              <select className="input" value={timeframe} onChange={e => setTimeframe(e.target.value)}>
                {['1m', '5m', '15m', '1h', '1d'].map(tf => <option key={tf} value={tf}>{tf}</option>)}
              </select>
            </div>

            <div className="field">
              <label>Parameters (JSON)</label>
              <textarea
                className="input"
                value={paramsJson}
                onChange={e => setParamsJson(e.target.value)}
                rows={5}
              />
            </div>

            <div className="field">
              <label>Source</label>
              <SegmentedControl
                options={[{ value: 'csv', label: 'Upload CSV' }, { value: 'provider', label: 'Fetch from provider' }]}
                value={source}
                onChange={v => setSource(v as 'csv' | 'provider')}
              />
            </div>

            {source === 'csv' ? (
              <div className="field">
                <label>Historical bars</label>
                <input ref={fileInputRef} type="file" accept=".csv,text/csv" onChange={e => setCsvFile(e.target.files?.[0] ?? null)} className="hidden" style={{ display: 'none' }} />
                <div className="drop" onClick={() => fileInputRef.current?.click()}>
                  <Upload size={20} />
                  <div style={{ marginTop: 6, fontSize: 12 }}>
                    {csvFile ? csvFile.name : 'Click to choose CSV'}
                  </div>
                  {csvFile && (
                    <div className="faint" style={{ fontSize: 10.5, marginTop: 4 }}>
                      {(csvFile.size / 1024).toFixed(0)} KB
                    </div>
                  )}
                </div>
                <div className="faint" style={{ fontSize: 10.5, marginTop: 4 }}>
                  columns: symbol, ts, open, high, low, close, volume
                </div>
              </div>
            ) : (
              <div className="stack" style={{ gap: 14 }}>
                <div className="field">
                  <label>Provider</label>
                  <select className="input" value={selectedProvider} onChange={e => setSelectedProvider(e.target.value)}>
                    {providers.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
                  </select>
                  {selectedProviderCaps && !providers.find(p => p.name === selectedProvider)?.configured && (
                    <div className="faint" style={{ fontSize: 10.5, marginTop: 4, color: 'var(--warn)' }}>
                      Not configured — set it up under Settings → Data Providers first.
                    </div>
                  )}
                </div>
                <div className="field">
                  <label>Symbol {instrumentType !== 'equity' && '(full tradingsymbol, e.g. NIFTY26AUGFUT)'}</label>
                  <input className="input" value={symbol} onChange={e => setSymbol(e.target.value)} placeholder="NIFTY26AUGFUT" />
                </div>
                <div className="grid-2">
                  <div className="field">
                    <label>Exchange</label>
                    <input className="input" value={exchange} onChange={e => setExchange(e.target.value)} />
                  </div>
                  <div className="field">
                    <label>Instrument type</label>
                    <select className="input" value={instrumentType} onChange={e => setInstrumentType(e.target.value)}>
                      {['equity', 'future', 'option'].map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                </div>
                <div className="grid-2">
                  <div className="field">
                    <label>From</label>
                    <input type="date" className="input" value={fromDate} onChange={e => setFromDate(e.target.value)} />
                  </div>
                  <div className="field">
                    <label>To</label>
                    <input type="date" className="input" value={toDate} onChange={e => setToDate(e.target.value)} />
                  </div>
                </div>
              </div>
            )}

            <button className="btn primary" onClick={run} disabled={running || !selectedStrategy || !canRun}>
              <Play size={12} />
              {running ? 'Running…' : 'Run backtest'}
            </button>
          </div>
        </div>

        {/* ── Results panel ── */}
        <div className="stack">
          {error && (
            <div className="card card-pad" style={{ borderColor: 'color-mix(in srgb, var(--neg) 30%, transparent)', background: 'var(--neg-dim)' }}>
              <div style={{ fontSize: 12, color: 'var(--neg)' }}>{error}</div>
            </div>
          )}

          {!result && !error && !running && (
            <div className="card card-pad" style={{ textAlign: 'center', padding: 60 }}>
              <div style={{ color: 'var(--text-faint)', fontSize: 13 }}>Configure a backtest and click Run.</div>
            </div>
          )}

          {running && (
            <div className="card card-pad" style={{ textAlign: 'center', padding: 40 }}>
              <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>Running backtest…</div>
              <div className="prog" style={{ marginTop: 16 }}><span style={{ width: '60%', animation: 'none' }} /></div>
            </div>
          )}

          {result && (
            <>
              {/* Results header + metrics */}
              <div className="card" style={{ overflow: 'hidden' }}>
                <div className="card-head">
                  <div>
                    <div className="title">Results · <span className="accent">{result.strategy_name}</span></div>
                    <div className="dim" style={{ fontSize: 11, marginTop: 4 }}>
                      {timeframe}
                      {dateRange && ` · ${dateRange}`}
                      {result.bars_loaded && ` · ${result.bars_loaded.toLocaleString()} bars`}
                    </div>
                  </div>
                  <Badge tone="pos">
                    done{result.elapsed_seconds ? ` · ${result.elapsed_seconds.toFixed(1)}s` : ''}
                  </Badge>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)' }}>
                  {[
                    ['Total return', `${result.metrics.total_return_pct?.toFixed(1) ?? 0}%`, (result.metrics.total_return_pct ?? 0) >= 0 ? 'pos' : 'neg'],
                    ['Total P&L', fmtINR(result.metrics.total_pnl ?? 0, { signed: true }), (result.metrics.total_pnl ?? 0) >= 0 ? 'pos' : 'neg'],
                    ['Sharpe', String(result.metrics.sharpe_ratio?.toFixed(2) ?? '—'), null],
                    ['Sortino', String(result.metrics.sortino_ratio?.toFixed(2) ?? '—'), null],
                    ['Max DD', `${result.metrics.max_drawdown_pct?.toFixed(1) ?? 0}%`, 'neg'],
                    ['Win rate', `${result.metrics.win_rate_pct?.toFixed(0) ?? 0}%`, null],
                    ['Trades', String(result.trade_count), null],
                    ['Profit factor', String(result.metrics.profit_factor?.toFixed(2) ?? '∞'), null],
                    ['Expectancy', fmtINR(result.metrics.expectancy ?? 0), null],
                    ['Avg holding', result.metrics.avg_holding_bars != null ? `${result.metrics.avg_holding_bars.toFixed(1)} bars` : '—', null],
                  ].map(([l, v, t]) => (
                    <div key={l as string} style={{
                      padding: '14px 16px',
                      borderRight: '1px solid var(--border)',
                      borderTop: '1px solid var(--border)',
                    }}>
                      <div className="faint" style={{ fontSize: 9.5, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>{l}</div>
                      <div className={`mono-num ${t || ''}`} style={{ fontSize: 16 }}>{v}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Equity curve */}
              {result.equity_curve.length > 0 && (
                <div className="card" style={{ overflow: 'hidden' }}>
                  <div className="card-head">
                    <span className="title">Equity curve</span>
                  </div>
                  <div style={{ padding: '10px 18px 18px' }}>
                    <Sparkline data={result.equity_curve} height={200} />
                  </div>
                </div>
              )}

              {/* Trade log */}
              {result.trades && result.trades.length > 0 && (
                <div className="card" style={{ overflow: 'hidden' }}>
                  <div className="card-head">
                    <span className="title">Trade log · <span className="accent">last {Math.min(result.trades.length, 6)}</span></span>
                  </div>
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Side</th>
                        <th className="num">Entry</th>
                        <th className="num">Exit</th>
                        <th className="num">Bars</th>
                        <th className="num">P&amp;L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.trades.slice(0, 6).map((t: BacktestTrade, i: number) => (
                        <tr key={i}>
                          <td className="faint mono-num" style={{ fontSize: 11 }}>
                            {new Date(t.ts).toLocaleDateString('en-IN')}
                          </td>
                          <td>
                            <span style={{ color: t.side === 'BUY' ? 'var(--pos)' : 'var(--neg)', fontSize: 11, fontWeight: 500 }}>
                              {t.side}
                            </span>
                          </td>
                          <td className="num mono-num">₹{t.entry_price.toFixed(2)}</td>
                          <td className="num mono-num">₹{t.exit_price.toFixed(2)}</td>
                          <td className="num mono-num">{t.bars_held}</td>
                          <td className={`num mono-num ${t.pnl >= 0 ? 'pos' : 'neg'}`}>
                            {fmtINR(t.pnl, { signed: true })}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { Plus, RefreshCw, Pause, Play } from 'lucide-react'
import { api, type BrokerStatus, type PortfolioSummary, type StrategyInstance } from '../lib/api'
import { wsClient } from '../lib/ws'
import { Sparkline, Gauge, Badge, fmtINR, fmtPct, fmtTime } from '../components/ui'

interface LiveTick {
  symbol: string
  ltp: number
  chgPct?: number
  vol?: number
  ts: string
}

const RANGE_DAYS: Record<string, number> = { '1W': 5, '1M': 20, '3M': 65, '1Y': 252 }

export default function Dashboard() {
  const [instances, setInstances] = useState<StrategyInstance[]>([])
  const [brokers, setBrokers] = useState<BrokerStatus[]>([])
  const [riskStatus, setRiskStatus] = useState<{
    kill_switch_active: boolean
    account_daily_loss: string
    ops_limit: number
  } | null>(null)
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null)
  const [ticks, setTicks] = useState<Record<string, LiveTick>>({})
  const [loading, setLoading] = useState(true)
  const [timeRange, setTimeRange] = useState('3M')

  const now = new Date()
  const hour = now.getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const sessionOpen = hour >= 9 && hour < 15
  const marketHours = sessionOpen
    ? `session is open · ${14 - hour}h ${60 - now.getMinutes()}m remaining`
    : 'market closed'

  const refresh = async () => {
    setLoading(true)
    try {
      const [instRes, healthRes, riskRes, portfolioRes] = await Promise.all([
        api.instances.list().catch(() => ({ instances: [] as StrategyInstance[] })),
        api.health().catch(() => null),
        api.risk.status().catch(() => null),
        api.portfolio.summary().catch(() => null),
      ])
      setInstances(instRes.instances)
      if (healthRes?.brokers) setBrokers(healthRes.brokers)
      if (riskRes) setRiskStatus(riskRes)
      if (portfolioRes) setPortfolio(portfolioRes)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 15_000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    const unsub = wsClient.subscribe((event) => {
      if (event.type === 'tick') {
        const e = event as unknown as LiveTick & { type: string }
        setTicks(prev => ({ ...prev, [e.symbol]: { ...e, ltp: Number(e.ltp) } }))
      }
    })
    return unsub
  }, [])

  const running = instances.filter(i => i.status === 'running')
  const errored = instances.filter(i => i.status === 'error')
  const tickList = Object.values(ticks).slice(0, 8)

  const pnlToday = portfolio?.pnl_today ?? 0
  const pnlPct = portfolio?.pnl_today_pct ?? 0
  const equityTotal = portfolio?.equity_total ?? 0
  const drawdownPct = portfolio?.drawdown_pct ?? 0
  const capitalUsedPct = portfolio?.capital_used_pct ?? 0
  const lossBudgetPct = portfolio?.loss_budget_pct ?? 0
  const openTrades = portfolio?.open_trades ?? running.length
  const closedTradesToday = portfolio?.closed_trades_today ?? 0
  const winRate = portfolio?.win_rate ?? 0
  const avgTradePnl = portfolio?.avg_trade_pnl ?? 0

  const intradayCurve = useMemo(
    () => (portfolio?.intraday_curve ?? []).map(p => p.value),
    [portfolio]
  )

  const equityCurve = useMemo(() => {
    const hist = portfolio?.historical_equity ?? []
    const days = RANGE_DAYS[timeRange] ?? 65
    const sliced = hist.slice(-days)
    if (sliced.length === 0) return [equityTotal || 100000]
    return sliced.map(p => p.value)
  }, [portfolio, timeRange, equityTotal])

  const opsLimit = riskStatus?.ops_limit ?? 10

  const handleStart = async (id: string) => {
    await api.instances.start(id).catch(() => null)
    refresh()
  }
  const handleStop = async (id: string) => {
    await api.instances.stop(id).catch(() => null)
    refresh()
  }

  return (
    <div className="stack" style={{ gap: 20 }}>
      {/* Page header */}
      <div className="h-page">
        <div>
          <h1>
            {greeting}
            {' '}<span className="faint">— {now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })} IST</span>
          </h1>
          <div className="sub">
            {now.toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'long', year: 'numeric' })}
            {' · '}{marketHours}
          </div>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={refresh} disabled={loading}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
          <button className="btn primary">
            <Plus size={13} /> New strategy
          </button>
        </div>
      </div>

      {/* ── Hero: P&L + Equity curve ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 14 }}>
        {/* P&L hero card */}
        <div className="card" style={{ position: 'relative' }}>
          <div className="halo" />
          <div style={{ position: 'relative', padding: '22px 24px 8px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 8 }}>
                  P&L · today
                </div>
                <div className={`hero-num ${pnlToday >= 0 ? 'pos' : 'neg'}`}>
                  <span className="pre">{pnlToday >= 0 ? '+₹' : '−₹'}</span>
                  {Math.abs(Math.round(pnlToday)).toLocaleString('en-IN')}
                </div>
                <div className="row" style={{ marginTop: 8, gap: 10 }}>
                  <Badge tone={pnlToday >= 0 ? 'pos' : 'neg'}>
                    {fmtPct(pnlPct, { signed: true })}
                  </Badge>
                  <span className="dim" style={{ fontSize: 11 }}>vs yesterday close</span>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 8 }}>
                  Equity
                </div>
                <div className="hero-num sm">
                  {fmtINR(equityTotal)}
                </div>
                <div className="dim" style={{ fontSize: 11, marginTop: 6 }}>
                  across {brokers.length || 1} broker
                </div>
              </div>
            </div>
          </div>
          <Sparkline data={intradayCurve.length > 1 ? intradayCurve : equityCurve.slice(-48)} height={120} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', borderTop: '1px solid var(--border)' }}>
            {[
              ['Open trades', String(openTrades), null],
              ['Closed', String(closedTradesToday), null],
              ['Win rate', winRate > 0 ? fmtPct(winRate) : '—', 'pos'],
              ['Avg trade', avgTradePnl !== 0 ? fmtINR(avgTradePnl, { signed: true }) : '—', avgTradePnl > 0 ? 'pos' : avgTradePnl < 0 ? 'neg' : null],
            ].map(([l, v, t]) => (
              <div key={l as string} style={{ padding: '14px 18px', borderRight: '1px solid var(--border)' }}>
                <div style={{ fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-faint)', marginBottom: 4 }}>
                  {l}
                </div>
                <div className={`mono-num ${t || ''}`} style={{ fontSize: 18 }}>{v}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Equity curve */}
        <div className="card" style={{ overflow: 'hidden' }}>
          <div className="card-head">
            <span className="title">Equity · <span className="accent">{equityCurve.length} sessions</span></span>
            <div className="seg">
              {['1W', '1M', '3M', '1Y'].map(r => (
                <button key={r} className={timeRange === r ? 'on' : ''} onClick={() => setTimeRange(r)}>{r}</button>
              ))}
            </div>
          </div>
          <div style={{ padding: '14px 20px 4px' }}>
            <div className="hero-num sm">{fmtINR(equityCurve[equityCurve.length - 1])}</div>
            <div className="dim" style={{ fontSize: 11, marginTop: 2 }}>
              {equityCurve.length > 1 ? (
                <>
                  <span className={(equityCurve[equityCurve.length - 1] - equityCurve[0]) >= 0 ? 'pos' : 'neg'}>
                    {fmtINR(equityCurve[equityCurve.length - 1] - equityCurve[0], { signed: true })}
                  </span>
                  {'  '}
                  <span>({fmtPct(((equityCurve[equityCurve.length - 1] - equityCurve[0]) / equityCurve[0]) * 100, { signed: true })})</span>
                </>
              ) : (
                <span className="faint">no history yet</span>
              )}
            </div>
          </div>
          <Sparkline data={equityCurve} height={120} />
        </div>
      </div>

      {/* ── Stat strip ── */}
      <div className="grid-4">
        {/* Strategies */}
        <div className="card card-pad">
          <div className="row" style={{ gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim)' }}>Strategies</span>
          </div>
          <div className="hero-num sm">
            {running.length}<span className="faint" style={{ fontSize: 18 }}> / {instances.length}</span>
          </div>
          <div className="row" style={{ marginTop: 8, gap: 6 }}>
            <Badge tone="pos" dot>{running.length} running</Badge>
            {errored.length > 0 && <Badge tone="neg">{errored.length} error</Badge>}
          </div>
        </div>

        {/* Brokers */}
        <div className="card card-pad">
          <div className="row" style={{ gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim)' }}>Brokers</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
            {brokers.length > 0 ? brokers.map(b => (
              <div key={b.name} className="row" style={{ justifyContent: 'space-between' }}>
                <span style={{ fontSize: 12 }}>{b.broker_name} · primary</span>
                <Badge tone={b.status === 'connected' ? 'pos' : 'neg'} dot={b.status === 'connected'}>
                  {b.status}
                </Badge>
              </div>
            )) : (
              <div className="dim" style={{ fontSize: 12 }}>No brokers configured</div>
            )}
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span style={{ fontSize: 12 }}>Paper engine</span>
              <Badge tone="pos">ready</Badge>
            </div>
          </div>
        </div>

        {/* Drawdown */}
        <div className="card card-pad">
          <div className="row" style={{ gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim)' }}>Drawdown</span>
          </div>
          <div className={`hero-num sm ${drawdownPct > 0 ? 'neg' : 'faint'}`}>
            {drawdownPct > 0 ? `−${fmtPct(drawdownPct)}` : '—'}
          </div>
          <div className="prog" style={{ marginTop: 10 }}>
            <span style={{ width: `${Math.min(100, drawdownPct)}%` }} />
          </div>
          <div className="dim" style={{ fontSize: 11, marginTop: 6 }}>
            Max session limit: {riskStatus?.account_daily_loss ?? '—'}
          </div>
        </div>

        {/* Today */}
        <div className="card card-pad">
          <div className="row" style={{ gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim)' }}>Today</span>
          </div>
          <div className="hero-num sm">
            {closedTradesToday} <span className="faint" style={{ fontSize: 18 }}>orders</span>
          </div>
          <div className="dim" style={{ fontSize: 11, marginTop: 6 }}>
            {closedTradesToday > 0 ? 'from running strategies' : 'no trades yet today'}
          </div>
        </div>
      </div>

      {/* ── Risk budget + Live ticks ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: 14 }}>
        {/* Risk budget */}
        <div className="card">
          <div className="card-head">
            <span className="title">Risk budget</span>
            <span className="dim" style={{ fontSize: 11 }}>session</span>
          </div>
          <div className="card-pad">
            <div className="row" style={{ justifyContent: 'space-around', padding: '6px 0 14px' }}>
              <Gauge value={capitalUsedPct} label="Capital used" sub={capitalUsedPct > 0 ? `${fmtPct(capitalUsedPct)} deployed` : '—'} />
              <Gauge value={lossBudgetPct} label="Loss budget" sub={lossBudgetPct > 0 ? `${fmtPct(lossBudgetPct)} used` : '—'} tone="warn" />
            </div>
            <hr className="hr" />
            <div className="stack" style={{ gap: 10 }}>
              {[
                ['Daily loss cap', riskStatus?.account_daily_loss ? `₹${riskStatus.account_daily_loss}` : '—', 'ok'],
                ['Per-trade risk', '1.0%', 'ok'],
                ['Max positions', `${running.length} / 10`, 'ok'],
                ['OPS limit', `— / ${opsLimit}s`, opsLimit > 8 ? 'warn' : 'ok'],
              ].map(([l, v, t]) => (
                <div key={l as string} className="row" style={{ justifyContent: 'space-between' }}>
                  <span className="dim" style={{ fontSize: 11.5 }}>{l}</span>
                  <span className={`mono-num ${t === 'warn' ? 'warn-c' : ''}`} style={{ fontSize: 12 }}>{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Live ticks */}
        <div className="card" style={{ overflow: 'hidden' }}>
          <div className="card-head">
            <span className="title">Live ticks · <span className="accent">{tickList.length} symbols</span></span>
            <Badge tone="pos" dot>streaming</Badge>
          </div>
          {tickList.length > 0 ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)' }}>
              {tickList.map((t, i) => {
                const positive = (t.chgPct ?? 0) >= 0
                return (
                  <div key={t.symbol} style={{
                    padding: '14px 16px',
                    borderRight: (i + 1) % 4 === 0 ? '0' : '1px solid var(--border)',
                    borderBottom: i < tickList.length - 4 ? '1px solid var(--border)' : '0',
                  }}>
                    <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
                      <span className="dim" style={{ fontSize: 10.5, letterSpacing: '0.06em' }}>{t.symbol}</span>
                      {t.chgPct != null && (
                        <span className={positive ? 'pos' : 'neg'} style={{ fontSize: 11 }}>
                          {positive ? '▲' : '▼'} {fmtPct(Math.abs(t.chgPct))}
                        </span>
                      )}
                    </div>
                    <div className="mono-num" style={{ fontSize: 17 }}>
                      ₹{t.ltp.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                    </div>
                    {t.vol != null && (
                      <div className="faint" style={{ fontSize: 10.5, marginTop: 3 }}>
                        vol {t.vol.toLocaleString('en-IN')}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ) : (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-faint)' }}>
              <div style={{ fontSize: 13 }}>Waiting for tick stream…</div>
              <div style={{ fontSize: 11, marginTop: 6 }}>Start a strategy with Zerodha connected to see live ticks</div>
            </div>
          )}
        </div>
      </div>

      {/* ── Active strategies table ── */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div className="card-head">
          <span className="title">Active strategies</span>
          <button className="btn ghost sm">View all</button>
        </div>
        {instances.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-faint)' }}>
            <div style={{ fontSize: 13 }}>No strategy instances yet</div>
            <div style={{ fontSize: 11, marginTop: 6 }}>Create an instance in the Strategies page to get started</div>
          </div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Instance</th>
                <th>Mode</th>
                <th>Status</th>
                <th className="num">Capital</th>
                <th className="num">Trades</th>
                <th className="num">P&amp;L</th>
                <th>Since</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {instances.map(inst => (
                <tr key={inst.id}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{inst.name}</div>
                    <div className="faint" style={{ fontSize: 10.5, marginTop: 2 }}>
                      {inst.strategy_class_name} · {inst.timeframe} · {inst.instruments.join(', ')}
                    </div>
                  </td>
                  <td>
                    <Badge tone={inst.mode === 'live' ? 'pos' : undefined}>{inst.mode}</Badge>
                  </td>
                  <td>
                    <Badge
                      tone={inst.status === 'running' ? 'pos' : inst.status === 'error' ? 'neg' : undefined}
                      dot={inst.status === 'running'}
                    >
                      {inst.status}
                    </Badge>
                  </td>
                  <td className="num mono-num">{fmtINR(inst.capital_allocation)}</td>
                  <td className="num mono-num">{inst.trade_count ?? '—'}</td>
                  <td className={`num mono-num ${(inst.pnl ?? 0) > 0 ? 'pos' : (inst.pnl ?? 0) < 0 ? 'neg' : 'faint'}`}>
                    {inst.pnl != null ? fmtINR(inst.pnl, { signed: true }) : '—'}
                  </td>
                  <td className="dim mono-num" style={{ fontSize: 11 }}>
                    {inst.last_started_at ? fmtTime(inst.last_started_at) : '—'}
                  </td>
                  <td className="num">
                    {inst.status === 'running' ? (
                      <button className="btn ghost sm" onClick={() => handleStop(inst.id)}>
                        <Pause size={11} /> Stop
                      </button>
                    ) : (
                      <button className="btn ghost sm" onClick={() => handleStart(inst.id)}>
                        <Play size={11} /> Start
                      </button>
                    )}
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

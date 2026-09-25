import { useEffect, useRef, useState } from 'react'
import { Plus, RefreshCw, Trash2, Upload } from 'lucide-react'
import { api, MyTrade, MyTradeImportResult, MyTradeInput, MyTradeStats } from '../lib/api'
import { Badge, fmtMoney, fmtTime, SkeletonRows } from '../components/ui'

// My Trades (2026-09-26): Rakesh's OWN trades -- imported from an MT5
// History report or entered by hand -- tagged by setup, so real fills can
// answer whether his discretionary setups have an edge. Strategy signals
// and backtests stay on the Journal page.

const label: React.CSSProperties = {
  fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6,
}

function fmtR(r: number | null | undefined): string {
  return r == null ? '—' : `${r >= 0 ? '+' : ''}${r.toFixed(2)}R`
}

function ImportCard({ onDone }: { onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<MyTradeImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (dryRun: boolean) => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.myTrades.importReport(file, dryRun)
      setPreview(res)
      if (!dryRun) onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-pad stack" style={{ gap: 10 }}>
      <div style={{ fontWeight: 600 }}>Import from MT5</div>
      <div className="faint" style={{ fontSize: 11.5 }}>
        MT5 → <b>History</b> tab → right-click → Period: <b>All history</b> → right-click → <b>Report → HTML</b>.
        Re-importing an overlapping report is safe: known trades are refreshed, your tags are kept.
      </div>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <input
          ref={fileRef} type="file" accept=".html,.htm"
          onChange={e => { setFile(e.target.files?.[0] ?? null); setPreview(null) }}
          style={{ fontSize: 11.5 }}
        />
        <button className="btn ghost" disabled={!file || busy} onClick={() => run(true)}>Preview</button>
        <button className="btn" disabled={!file || busy || !preview?.dry_run} onClick={() => run(false)}>
          <Upload size={13} /> Import
        </button>
      </div>
      {error && <div className="neg" style={{ fontSize: 11.5 }}>{error}</div>}
      {preview && (
        <div style={{ fontSize: 11.5 }}>
          <div>
            Account <b>{preview.account}</b>{preview.server ? ` on ${preview.server}` : ''}
            {preview.is_demo && <Badge tone="neg">demo account</Badge>}
          </div>
          {preview.dry_run ? 'Preview: ' : 'Imported: '}
          {preview.parsed} positions found — <b>{preview.added}</b> new, {preview.updated} already known
          {preview.parsed === 0 && (
            <div className="faint">No closed trades in this report — check you exported the right account and Period: All history.</div>
          )}
          {preview.warnings.length > 0 && (
            <div className="faint">{preview.warnings.length} rows skipped: {preview.warnings.slice(0, 3).join('; ')}</div>
          )}
        </div>
      )}
    </div>
  )
}

const EMPTY: MyTradeInput = {
  symbol: 'XAUUSD', side: 'BUY', volume_lots: 0.01, open_time: '', open_price: 0,
}

function ManualForm({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [f, setF] = useState<MyTradeInput>(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const num = (v: string) => (v === '' ? null : Number(v))
  const set = (k: keyof MyTradeInput, v: unknown) => setF(prev => ({ ...prev, [k]: v }))

  const save = async () => {
    setError(null)
    try {
      await api.myTrades.create({
        ...f,
        open_time: new Date(f.open_time).toISOString(),
        close_time: f.close_time ? new Date(f.close_time).toISOString() : null,
      })
      setF(EMPTY)
      setOpen(false)
      onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  if (!open) {
    return (
      <button className="btn ghost" onClick={() => setOpen(true)}>
        <Plus size={13} /> Add trade manually
      </button>
    )
  }
  const field = (text: string, el: React.ReactNode) => (
    <label className="stack" style={{ gap: 3, fontSize: 11 }}><span className="faint">{text}</span>{el}</label>
  )
  return (
    <div className="card card-pad stack" style={{ gap: 10 }}>
      <div style={{ fontWeight: 600 }}>Add a trade</div>
      <div className="grid-4" style={{ gap: 10 }}>
        {field('Symbol', <input className="input" value={f.symbol} onChange={e => set('symbol', e.target.value.toUpperCase())} />)}
        {field('Side', (
          <select className="input" value={f.side} onChange={e => set('side', e.target.value)}>
            <option value="BUY">BUY</option><option value="SELL">SELL</option>
          </select>
        ))}
        {field('Lots', <input className="input" type="number" step="0.01" value={f.volume_lots} onChange={e => set('volume_lots', Number(e.target.value))} />)}
        {field('Setup', <input className="input" placeholder="e.g. PDH sweep" value={f.setup_tag ?? ''} onChange={e => set('setup_tag', e.target.value)} />)}
        {field('Open time (local)', <input className="input" type="datetime-local" value={f.open_time} onChange={e => set('open_time', e.target.value)} />)}
        {field('Open price', <input className="input" type="number" step="0.01" onChange={e => set('open_price', Number(e.target.value))} />)}
        {field('Stop loss', <input className="input" type="number" step="0.01" onChange={e => set('stop_loss', num(e.target.value))} />)}
        {field('Take profit', <input className="input" type="number" step="0.01" onChange={e => set('take_profit', num(e.target.value))} />)}
        {field('Close time (local)', <input className="input" type="datetime-local" onChange={e => set('close_time', e.target.value || null)} />)}
        {field('Close price', <input className="input" type="number" step="0.01" onChange={e => set('close_price', num(e.target.value))} />)}
        {field('Profit (gross $)', <input className="input" type="number" step="0.01" onChange={e => set('profit', num(e.target.value))} />)}
        {field('Commission + swap ($)', <input className="input" type="number" step="0.01" onChange={e => set('commission', Number(e.target.value) || 0)} />)}
      </div>
      {field('Why did you take it?', <input className="input" onChange={e => set('reason', e.target.value)} />)}
      <label className="row" style={{ gap: 6, fontSize: 11.5 }}>
        <input type="checkbox" onChange={e => set('followed_plan', e.target.checked)} /> I followed my plan
      </label>
      {error && <div className="neg" style={{ fontSize: 11.5 }}>{error}</div>}
      <div className="row" style={{ gap: 8 }}>
        <button className="btn" disabled={!f.open_time || !f.open_price} onClick={save}>Save</button>
        <button className="btn ghost" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </div>
  )
}

function TagCell({ t, onSaved }: { t: MyTrade; onSaved: (t: MyTrade) => void }) {
  const [setup, setSetup] = useState(t.setup_tag ?? '')
  const save = async (patch: Parameters<typeof api.myTrades.tag>[1]) => onSaved(await api.myTrades.tag(t.id, patch))
  return (
    <div className="row" style={{ gap: 6 }}>
      <input
        className="input" style={{ fontSize: 11, width: 130 }} placeholder="setup…" value={setup}
        onChange={e => setSetup(e.target.value)}
        onBlur={() => { if (setup !== (t.setup_tag ?? '')) save({ setup_tag: setup }) }}
      />
      <select
        className="input" style={{ fontSize: 11, width: 92 }}
        value={t.followed_plan == null ? '' : t.followed_plan ? 'yes' : 'no'}
        onChange={e => save({ followed_plan: e.target.value === '' ? null : e.target.value === 'yes' })}
        title="Did you follow your plan?"
      >
        <option value="">plan?</option><option value="yes">followed</option><option value="no">broke it</option>
      </select>
    </div>
  )
}

export default function MyTrades() {
  const [trades, setTrades] = useState<MyTrade[]>([])
  const [stats, setStats] = useState<MyTradeStats | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [t, s] = await Promise.all([api.myTrades.list(), api.myTrades.stats()])
      setTrades(t)
      setStats(s)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const replace = (u: MyTrade) => {
    setTrades(prev => prev.map(x => (x.id === u.id ? u : x)))
    api.myTrades.stats().then(setStats)
  }
  const o = stats?.overall

  return (
    <div className="stack">
      <div className="h-page">
        <div>
          <h1>My Trades</h1>
          <div className="sub">Your own trades — imported from MT5 or added by hand — tagged by setup</div>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={load} disabled={loading}><RefreshCw size={13} /> Refresh</button>
        </div>
      </div>

      <div className="grid-4">
        <div className="card card-pad"><div className="faint" style={label}>Trades</div><div className="hero-num sm">{o?.n ?? '—'}</div></div>
        <div className="card card-pad">
          <div className="faint" style={label}>Net P&L</div>
          <div className={`hero-num sm ${(o?.net_pnl ?? 0) >= 0 ? 'pos' : 'neg'}`}>{o ? fmtMoney(o.net_pnl, '$', { signed: true }) : '—'}</div>
        </div>
        <div className="card card-pad"><div className="faint" style={label}>Win rate</div><div className="hero-num sm">{o?.win_rate ?? '—'}{o?.win_rate != null && <span className="faint" style={{ fontSize: 18 }}>%</span>}</div></div>
        <div className="card card-pad">
          <div className="faint" style={label}>Avg R ({o?.n_with_r ?? 0} with a stop)</div>
          <div className="hero-num sm">{fmtR(o?.avg_r)}</div>
        </div>
      </div>

      <div className="grid-2" style={{ gap: 14, alignItems: 'start' }}>
        <ImportCard onDone={load} />
        <div className="stack" style={{ gap: 10 }}>
          <ManualForm onDone={load} />
          {stats && Object.keys(stats.by_setup).length > 0 && (
            <div className="card" style={{ overflow: 'hidden' }}>
              <div className="card-head"><div style={{ fontWeight: 600 }}>By setup</div>
                <span className="faint" style={{ fontSize: 11 }}>small samples lie — wait for 30+ trades per setup</span>
              </div>
              <table className="tbl">
                <thead><tr><th>Setup</th><th className="num">n</th><th className="num">Win%</th><th className="num">PF</th><th className="num">Avg R</th><th className="num">Net</th></tr></thead>
                <tbody>
                  {Object.entries(stats.by_setup).map(([k, g]) => (
                    <tr key={k}>
                      <td>{k}</td><td className="num mono-num">{g.n}</td>
                      <td className="num mono-num">{g.win_rate ?? '—'}</td>
                      <td className="num mono-num">{g.profit_factor ?? '—'}</td>
                      <td className="num mono-num">{fmtR(g.avg_r)}</td>
                      <td className={`num mono-num ${g.net_pnl >= 0 ? 'pos' : 'neg'}`}>{fmtMoney(g.net_pnl, '$', { signed: true })}</td>
                    </tr>
                  ))}
                  <tr className="faint">
                    <td>followed plan / broke it</td>
                    <td className="num mono-num">{stats.followed_plan.yes.n} / {stats.followed_plan.no.n}</td>
                    <td colSpan={3}></td>
                    <td className="num mono-num">
                      {fmtMoney(stats.followed_plan.yes.net_pnl, '$', { signed: true })} / {fmtMoney(stats.followed_plan.no.net_pnl, '$', { signed: true })}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '16px 18px' }}><SkeletonRows rows={6} cols={8} /></div>
        ) : trades.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-faint)' }}>
            No trades yet — import your MT5 history report or add one by hand
          </div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Opened</th><th>Symbol</th><th>Side</th><th className="num">Lots</th>
                <th className="num">Entry</th><th className="num">Exit</th><th className="num">Net</th>
                <th className="num">R</th><th>Setup / plan</th><th>Source</th><th></th>
              </tr>
            </thead>
            <tbody>
              {trades.map(t => (
                <tr key={t.id}>
                  <td className="faint mono-num" style={{ fontSize: 11 }}>{fmtTime(t.open_time)}</td>
                  <td style={{ fontWeight: 500 }}>{t.symbol}</td>
                  <td><span style={{ color: t.side === 'BUY' ? 'var(--pos)' : 'var(--neg)', fontWeight: 500, fontSize: 11 }}>{t.side === 'BUY' ? '▲' : '▼'} {t.side}</span></td>
                  <td className="num mono-num">{t.volume_lots}</td>
                  <td className="num mono-num">{t.open_price.toFixed(2)}</td>
                  <td className="num mono-num">{t.close_price?.toFixed(2) ?? '—'}</td>
                  <td className={`num mono-num ${(t.net_pnl ?? 0) >= 0 ? 'pos' : 'neg'}`}>{t.net_pnl == null ? 'open' : fmtMoney(t.net_pnl, '$', { signed: true })}</td>
                  <td className="num mono-num" title={t.source === 'mt5_import' ? 'uses the S/L at close — a trailed stop understates your original risk' : undefined}>{fmtR(t.r_multiple)}</td>
                  <td><TagCell t={t} onSaved={replace} /></td>
                  <td><Badge tone={t.source === 'manual' ? undefined : 'pos'}>{t.source === 'manual' ? 'manual' : 'MT5'}</Badge></td>
                  <td>
                    {t.source === 'manual' && (
                      <button className="btn ghost" title="Delete" onClick={async () => { await api.myTrades.remove(t.id); load() }}>
                        <Trash2 size={12} />
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

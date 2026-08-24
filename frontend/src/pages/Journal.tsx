import { Fragment, useEffect, useState } from 'react'
import { BookOpen, Download, RefreshCw } from 'lucide-react'
import { api, type JournalEntryRow, type StrategyClass } from '../lib/api'
import { Badge, fmtINR, fmtTime } from '../components/ui'

const FAILURE_MODES = [
  'stopped_out', 'target_missed', 'late_entry', 'slippage',
  'no_fill', 'gap', 'regime_change', 'data_gap', 'system_error',
]

const OUTCOME_TONE: Record<string, 'pos' | 'neg' | 'warn' | undefined> = {
  win: 'pos', target_hit: 'pos', stopped_out: 'neg', loss: 'neg',
  unclassified: 'warn', still_open: undefined,
}

function NoteEditor({ entry, onSaved }: { entry: JournalEntryRow; onSaved: () => void }) {
  const [failureMode, setFailureMode] = useState(entry.manual_failure_mode ?? '')
  const [changeMade, setChangeMade] = useState(entry.change_made ?? '')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      await api.journal.setNote({
        source: entry.source, source_id: entry.source_id,
        failure_mode: failureMode || undefined, change_made: changeMade || undefined,
      })
      onSaved()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="row" style={{ gap: 8, padding: '8px 0', flexWrap: 'wrap' }}>
      <select className="input" style={{ fontSize: 11, width: 150 }} value={failureMode} onChange={e => setFailureMode(e.target.value)}>
        <option value="">— failure mode —</option>
        {FAILURE_MODES.map(m => <option key={m} value={m}>{m}</option>)}
      </select>
      <input
        className="input" style={{ fontSize: 11, flex: 1, minWidth: 160 }}
        placeholder="what did you change in response?"
        value={changeMade} onChange={e => setChangeMade(e.target.value)}
      />
      <button className="btn ghost sm" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
    </div>
  )
}

export default function Journal() {
  const [strategies, setStrategies] = useState<StrategyClass[]>([])
  const [strategyFilter, setStrategyFilter] = useState('')
  const [entries, setEntries] = useState<JournalEntryRow[]>([])
  const [loading, setLoading] = useState(true)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [exportMsg, setExportMsg] = useState('')
  const [exporting, setExporting] = useState(false)

  const load = () => {
    setLoading(true)
    api.journal.list({ strategy_name: strategyFilter || undefined, limit: 200 })
      .then(r => setEntries(r.entries))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    api.strategies.classes().then(r => setStrategies(r.strategies)).catch(() => {})
  }, [])

  useEffect(() => { load() }, [strategyFilter])

  const runExport = async () => {
    if (!strategyFilter) return
    setExporting(true)
    setExportMsg('')
    try {
      const res = await api.journal.export(strategyFilter)
      setExportMsg(`Exported ${res.entry_count} entries → ${res.path}`)
    } catch (e) {
      setExportMsg(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const failureCount = entries.filter(e => ['stopped_out', 'loss', 'unclassified'].includes(e.outcome)).length
  const winCount = entries.filter(e => ['win', 'target_hit'].includes(e.outcome)).length

  return (
    <div className="stack">
      <div className="h-page">
        <div>
          <h1>Journal</h1>
          <div className="sub">Every signal linked to its outcome — auto-tagged where the data actually supports it</div>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={load} disabled={loading}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid-4">
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Entries</div>
          <div className="hero-num sm">{entries.length}</div>
        </div>
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Wins</div>
          <div className="hero-num sm pos">{winCount}</div>
        </div>
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Failures</div>
          <div className="hero-num sm neg">{failureCount}</div>
        </div>
        <div className="card card-pad">
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 6 }}>Win rate</div>
          <div className="hero-num sm">
            {entries.length > 0 ? Math.round((winCount / entries.length) * 100) : 0}<span className="faint" style={{ fontSize: 18 }}>%</span>
          </div>
        </div>
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        <div className="card-head">
          <div className="row" style={{ gap: 10 }}>
            <select className="input" style={{ fontSize: 11.5, width: 220 }} value={strategyFilter} onChange={e => setStrategyFilter(e.target.value)}>
              <option value="">All strategies</option>
              {strategies.map(s => <option key={s.name} value={s.name}>{s.name}</option>)}
            </select>
          </div>
          <button className="btn ghost sm" onClick={runExport} disabled={!strategyFilter || exporting}>
            <Download size={12} /> {exporting ? 'Exporting…' : 'Export to docs/strategies'}
          </button>
        </div>

        {exportMsg && (
          <div className="card-pad" style={{ fontSize: 11.5, color: exportMsg.startsWith('Exported') ? 'var(--pos)' : 'var(--neg)' }}>
            {exportMsg}
          </div>
        )}

        {loading && entries.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-faint)' }}>Loading journal…</div>
        ) : entries.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-faint)' }}>
            <BookOpen size={20} style={{ color: 'var(--text-faint)', marginBottom: 8 }} />
            <div>No journal entries yet — run a backtest or an alert-mode instance to see them here.</div>
          </div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Date</th><th>Source</th><th>Symbol</th><th>Side</th>
                <th className="num">Entry</th><th className="num">Exit</th><th className="num">P&amp;L</th>
                <th>Outcome</th><th></th>
              </tr>
            </thead>
            <tbody>
              {entries.map(e => {
                const key = `${e.source}:${e.source_id}`
                const editable = ['stopped_out', 'loss', 'unclassified'].includes(e.outcome)
                return (
                  <Fragment key={key}>
                    <tr style={editable ? { cursor: 'pointer' } : undefined} onClick={() => editable && setEditingKey(editingKey === key ? null : key)}>
                      <td className="faint mono-num" style={{ fontSize: 10.5 }}>{e.exit_ts ? fmtTime(e.exit_ts) : e.entry_ts ? fmtTime(e.entry_ts) : '—'}</td>
                      <td className="faint" style={{ fontSize: 10.5 }}>{e.source === 'signal_log' ? 'alert' : 'backtest'}</td>
                      <td style={{ fontWeight: 500 }}>{e.symbol}</td>
                      <td>{e.side && <span style={{ color: e.side === 'BUY' || e.side === 'LONG' ? 'var(--pos)' : 'var(--neg)', fontSize: 11 }}>{e.side}</span>}</td>
                      <td className="num mono-num">{e.entry_price != null ? `₹${e.entry_price.toFixed(2)}` : '—'}</td>
                      <td className="num mono-num">{e.exit_price != null ? `₹${e.exit_price.toFixed(2)}` : '—'}</td>
                      <td className={`num mono-num ${(e.pnl ?? 0) >= 0 ? 'pos' : 'neg'}`}>{e.pnl != null ? fmtINR(e.pnl, { signed: true }) : '—'}</td>
                      <td>
                        <Badge tone={OUTCOME_TONE[e.outcome]}>{e.manual_failure_mode || e.outcome}</Badge>
                      </td>
                      <td className="faint" style={{ fontSize: 10 }}>{editable ? (editingKey === key ? '▲' : '▼ tag') : ''}</td>
                    </tr>
                    {editingKey === key && (
                      <tr>
                        <td colSpan={9} style={{ background: 'var(--surface-2)', padding: '0 16px' }}>
                          <NoteEditor entry={e} onSaved={() => { setEditingKey(null); load() }} />
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

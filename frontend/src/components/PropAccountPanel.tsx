import { useEffect, useState } from 'react'
import { Settings2 } from 'lucide-react'
import { api, PropConfig, PropStatus } from '../lib/api'
import { Badge, fmtMoney } from './ui'

// FundingPips limits from CLOSED trades (2026-09-30). The firm measures the
// daily limit on equity incl. open trades; this panel can't see those yet,
// and says so on screen rather than implying it's live.

const TONE = { ok: 'pos', warn: undefined, breach: 'neg' } as const
const BAR = { ok: 'var(--pos)', warn: 'var(--warn, #d9a441)', breach: 'var(--neg)' } as const

function Settings({ cfg, accounts, onSaved, onCancel }: {
  cfg: PropConfig
  accounts: { account: string; trades: number }[]
  onSaved: () => void
  onCancel: () => void
}) {
  const [f, setF] = useState<PropConfig>(cfg)
  const [error, setError] = useState<string | null>(null)
  const set = (k: keyof PropConfig, v: unknown) => setF(prev => ({ ...prev, [k]: v }))
  const field = (text: string, el: React.ReactNode) => (
    <label className="stack" style={{ gap: 3, fontSize: 11 }}><span className="faint">{text}</span>{el}</label>
  )
  const save = async () => {
    setError(null)
    try {
      await api.propAccount.saveConfig(f)
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  return (
    <div className="stack" style={{ gap: 10, marginTop: 10 }}>
      <div className="grid-4" style={{ gap: 10 }}>
        {field('Account', (
          <select className="input" value={f.account} onChange={e => set('account', e.target.value)}>
            <option value="">auto (most trades)</option>
            {accounts.map(a => <option key={a.account} value={a.account}>{a.account} ({a.trades})</option>)}
          </select>
        ))}
        {field('Phase', (
          <select className="input" value={f.phase} onChange={e => set('phase', e.target.value)}>
            <option value="phase1">Phase 1 (10% target)</option>
            <option value="phase2">Phase 2 (6% target)</option>
            <option value="master">Master (funded)</option>
          </select>
        ))}
        {field('Start balance ($)', <input className="input" type="number" value={f.start_balance} onChange={e => set('start_balance', Number(e.target.value))} />)}
        {field('Phase started (server day)', <input className="input" type="date" value={f.start_date} onChange={e => set('start_date', e.target.value)} />)}
        {field('Your daily stop ($)', <input className="input" type="number" value={f.personal_daily_stop_usd} onChange={e => set('personal_daily_stop_usd', Number(e.target.value))} />)}
        {field('Firm daily loss (%)', <input className="input" type="number" step="0.1" value={f.daily_loss_pct} onChange={e => set('daily_loss_pct', Number(e.target.value))} />)}
        {field('Firm max loss (%)', <input className="input" type="number" step="0.1" value={f.max_loss_pct} onChange={e => set('max_loss_pct', Number(e.target.value))} />)}
        {field('Warn at (% of a limit)', <input className="input" type="number" value={f.warn_at_pct} onChange={e => set('warn_at_pct', Number(e.target.value))} />)}
      </div>
      {error && <div className="neg" style={{ fontSize: 11.5 }}>{error}</div>}
      <div className="row" style={{ gap: 8 }}>
        <button className="btn" onClick={save}>Save</button>
        <button className="btn ghost" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}

export default function PropAccountPanel({ refreshKey }: { refreshKey: number }) {
  const [st, setSt] = useState<PropStatus | null>(null)
  const [editing, setEditing] = useState(false)
  const [accounts, setAccounts] = useState<{ account: string; trades: number }[]>([])

  const load = () => {
    api.propAccount.status().then(setSt).catch(() => setSt(null))
    api.propAccount.accounts().then(setAccounts).catch(() => setAccounts([]))
  }
  useEffect(load, [refreshKey])

  if (!st) return null
  const c = st.config
  return (
    <div className="card card-pad">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div className="row" style={{ gap: 8 }}>
          <div style={{ fontWeight: 600 }}>{c.firm} {c.program} · {c.phase === 'master' ? 'Master' : c.phase === 'phase1' ? 'Phase 1' : 'Phase 2'}</div>
          <Badge tone={TONE[st.level]} dot>{st.level === 'ok' ? 'within limits' : st.level === 'warn' ? 'near a limit' : 'LIMIT BREACHED'}</Badge>
          <span className="faint" style={{ fontSize: 11 }}>account {c.account || '—'} · server day {st.server_day}</span>
        </div>
        <button className="btn ghost" onClick={() => setEditing(e => !e)}><Settings2 size={13} /> Settings</button>
      </div>

      <div className="grid-4" style={{ marginTop: 12 }}>
        {st.limits.map(l => (
          <div key={l.name}>
            <div className="faint" style={{ fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4 }}>{l.name}</div>
            <div className="mono-num" style={{ fontSize: 13 }}>
              {fmtMoney(l.used_usd, '$')} <span className="faint">/ {fmtMoney(l.limit_usd, '$')}</span>
            </div>
            <div className="prog" style={{ marginTop: 6 }}>
              <span style={{ width: `${Math.min(100, l.used_pct)}%`, background: BAR[l.level] }} />
            </div>
          </div>
        ))}
        <div>
          <div className="faint" style={{ fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4 }}>
            {st.target_usd ? `Target ${c.profit_target_pct}%` : 'Balance'}
          </div>
          <div className="mono-num" style={{ fontSize: 13 }}>
            {fmtMoney(st.balance, '$')}{' '}
            <span className={st.total_pnl >= 0 ? 'pos' : 'neg'}>({fmtMoney(st.total_pnl, '$', { signed: true })})</span>
          </div>
          {st.target_usd != null && (
            <div className="prog" style={{ marginTop: 6 }}>
              <span style={{ width: `${Math.max(0, Math.min(100, st.target_progress_pct ?? 0))}%` }} />
            </div>
          )}
        </div>
      </div>

      <div className="faint" style={{ fontSize: 11, marginTop: 10 }}>
        Today {fmtMoney(st.today_pnl, '$', { signed: true })} · {st.trading_days} trading days, {st.profitable_days} profitable (≥{c.min_profitable_day_pct}%) ·
        resets {new Date(st.next_reset_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} your time ·
        <b> {st.basis}</b> — the firm counts open trades too
      </div>

      {editing && (
        <Settings cfg={c} accounts={accounts} onCancel={() => setEditing(false)} onSaved={() => { setEditing(false); load() }} />
      )}
    </div>
  )
}

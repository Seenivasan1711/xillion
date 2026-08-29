import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, Bell, CheckCircle, Database, Shield, Wifi } from 'lucide-react'
import { api } from '../lib/api'
import type { ZerodhaCredentials, DhanCredentials, NotificationSettings, RiskLimits, BrokerStatus, DataProviderClass, BarCoverage, BackfillJob, ReconciliationReport } from '../lib/api'
import { Badge } from '../components/ui'
import { useToast } from '../components/Toast'

type Tab = 'brokers' | 'data' | 'risk' | 'notifications'

const TABS: { id: Tab; label: string }[] = [
  { id: 'brokers', label: 'Brokers' },
  { id: 'data', label: 'Data Providers' },
  { id: 'risk', label: 'Risk' },
  { id: 'notifications', label: 'Notifications' },
]

const TAB_IDS = TABS.map(t => t.id)

export default function Configuration() {
  const [searchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')
  const initialTab = TAB_IDS.includes(requestedTab as Tab) ? (requestedTab as Tab) : 'brokers'
  const [tab, setTab] = useState<Tab>(initialTab)

  return (
    <div className="stack">
      <div className="h-page">
        <div>
          <h1>Configuration</h1>
          <div className="sub">Brokers, data providers, risk limits, notifications</div>
        </div>
      </div>

      <div className="tabs">
        {TABS.map(t => (
          <button key={t.id} className={`tab${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'brokers'      && <BrokersTab />}
      {tab === 'data'         && <DataProvidersTab />}
      {tab === 'risk'         && <RiskTab />}
      {tab === 'notifications' && <NotificationsTab />}
    </div>
  )
}

// ── Brokers tab ──────────────────────────────────────────────────────────────

function BrokersTab() {
  const toast = useToast()
  const [checking, setChecking] = useState<string | null>(null)
  const [zerodhaStatus, setZerodhaStatus] = useState<{
    configured: boolean
    api_key_preview?: string
    user_id?: string
    updated_at?: string
    product_type?: 'MIS' | 'NRML'
  } | null>(null)
  const [form, setForm] = useState<ZerodhaCredentials>({
    api_key: '', api_secret: '', user_id: '', password: '', totp_secret: '', product_type: 'MIS',
  })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [msgKind, setMsgKind] = useState<'ok' | 'err'>('ok')
  const [brokers, setBrokers] = useState<BrokerStatus[]>([])
  const [reconnecting, setReconnecting] = useState<string | null>(null)

  const [dhanStatus, setDhanStatus] = useState<{
    configured: boolean
    client_id?: string
    updated_at?: string
    product_type?: 'INTRADAY' | 'MARGIN'
  } | null>(null)
  const [dhanForm, setDhanForm] = useState<DhanCredentials>({
    client_id: '', access_token: '', pin: '', totp_secret: '', product_type: 'MARGIN',
  })
  const [dhanSaving, setDhanSaving] = useState(false)
  const [dhanMsg, setDhanMsg] = useState('')
  const [dhanMsgKind, setDhanMsgKind] = useState<'ok' | 'err'>('ok')

  useEffect(() => {
    Promise.all([api.settings.getZerodha(), api.settings.getDhan(), api.brokers.connections()]).then(([z, d, b]) => {
      setZerodhaStatus(z)
      setDhanStatus(d)
      setBrokers(b.connections)
      if (z.product_type) setForm(f => ({ ...f, product_type: z.product_type! }))
      if (d.product_type) setDhanForm(f => ({ ...f, product_type: d.product_type! }))
    }).catch(() => {})
  }, [])

  const save = async () => {
    setSaving(true)
    setMsg('')
    try {
      const res = await api.settings.saveZerodha(form)
      if (res.connection_status === 'connected') {
        setMsg('Saved and connected successfully')
        setMsgKind('ok')
      } else {
        setMsg(`Saved, but connection failed: ${res.last_error ?? 'unknown error'}`)
        setMsgKind('err')
      }
      const [z, b] = await Promise.all([api.settings.getZerodha(), api.brokers.connections()])
      setZerodhaStatus(z)
      setBrokers(b.connections)
      if (z.product_type) setForm(f => ({ ...f, product_type: z.product_type! }))
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Save failed')
      setMsgKind('err')
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!confirm('Remove Zerodha credentials? You will need to re-enter them to reconnect.')) return
    try {
      await api.settings.deleteZerodha()
      setMsg('Credentials removed')
      setMsgKind('ok')
      const [z, b] = await Promise.all([api.settings.getZerodha(), api.brokers.connections()])
      setZerodhaStatus(z)
      setBrokers(b.connections)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Remove failed')
      setMsgKind('err')
    }
  }

  const saveDhan = async () => {
    setDhanSaving(true)
    setDhanMsg('')
    try {
      const res = await api.settings.saveDhan(dhanForm)
      if (res.connection_status === 'connected') {
        setDhanMsg('Saved and connected successfully')
        setDhanMsgKind('ok')
      } else {
        setDhanMsg(`Saved, but connection failed: ${res.last_error ?? 'unknown error'}`)
        setDhanMsgKind('err')
      }
      const [d, b] = await Promise.all([api.settings.getDhan(), api.brokers.connections()])
      setDhanStatus(d)
      setBrokers(b.connections)
      if (d.product_type) setDhanForm(f => ({ ...f, product_type: d.product_type! }))
    } catch (e) {
      setDhanMsg(e instanceof Error ? e.message : 'Save failed')
      setDhanMsgKind('err')
    } finally {
      setDhanSaving(false)
    }
  }

  const checkConnection = async (name: string) => {
    setChecking(name)
    try {
      const res = await api.brokers.status(name)
      if (res.status === 'connected') {
        toast('ok', `${name}: connected`)
      } else {
        toast('error', `${name}: ${res.status}${res.last_error ? ` — ${res.last_error}` : ''}`)
      }
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Connection check failed')
    } finally {
      setChecking(null)
    }
  }

  const removeDhan = async () => {
    if (!confirm('Remove Dhan credentials? You will need to re-enter them to reconnect.')) return
    try {
      await api.settings.deleteDhan()
      setDhanMsg('Credentials removed')
      setDhanMsgKind('ok')
      const [d, b] = await Promise.all([api.settings.getDhan(), api.brokers.connections()])
      setDhanStatus(d)
      setBrokers(b.connections)
    } catch (e) {
      setDhanMsg(e instanceof Error ? e.message : 'Remove failed')
      setDhanMsgKind('err')
    }
  }

  const reconnect = async (name: string) => {
    setReconnecting(name)
    try {
      await api.brokers.reconnect(name)
      const b = await api.brokers.connections()
      setBrokers(b.connections)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Reconnect failed')
    } finally {
      setReconnecting(null)
    }
  }

  const [settingFailoverFor, setSettingFailoverFor] = useState<string | null>(null)
  const [triggeringFailoverFor, setTriggeringFailoverFor] = useState<string | null>(null)

  const setFailoverTarget = async (name: string, targetName: string) => {
    setSettingFailoverFor(name)
    try {
      await api.brokers.setFailoverTarget(name, targetName || null)
      const b = await api.brokers.connections()
      setBrokers(b.connections)
      toast('ok', targetName ? `${name} will fail over to ${targetName}` : `Failover cleared for ${name}`)
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Failed to set failover target')
    } finally {
      setSettingFailoverFor(null)
    }
  }

  const triggerFailoverNow = async (name: string) => {
    if (!confirm(`Exit every open position under ${name} via its configured failover broker right now? This places real orders on the secondary broker.`)) return
    setTriggeringFailoverFor(name)
    try {
      const res = await api.brokers.triggerFailover(name)
      toast(res.status === 'FAILED' ? 'error' : 'ok', `Failover ${res.status}: exited ${res.exited.length}, failed ${res.failed_to_exit.length}`)
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Failover failed')
    } finally {
      setTriggeringFailoverFor(null)
    }
  }

  return (
    <div className="stack">
      {/* Zerodha credentials */}
      <div className="card">
        <div className="card-head">
          <span className="title">Zerodha</span>
          {zerodhaStatus?.configured
            ? <Badge tone="pos"><CheckCircle size={11} style={{ marginRight: 4 }} />Configured</Badge>
            : <Badge>Not configured</Badge>
          }
        </div>
        <div className="card-pad stack" style={{ gap: 14 }}>
          {zerodhaStatus?.configured && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 8,
              border: '1px solid var(--border)',
            }}>
              <div style={{ fontSize: 12 }}>
                <span className="faint">User ID: </span>
                <span className="mono-num">{zerodhaStatus.user_id ?? '—'}</span>
                <span className="faint" style={{ marginLeft: 16 }}>API key: </span>
                <span className="mono-num">{zerodhaStatus.api_key_preview ?? '—'}</span>
              </div>
              <button className="btn ghost sm" onClick={remove} style={{ color: 'var(--neg)' }}>Remove</button>
            </div>
          )}

          <div className="grid-2">
            {[
              { key: 'api_key', label: 'API Key', type: 'text' },
              { key: 'api_secret', label: 'API Secret', type: 'password' },
              { key: 'user_id', label: 'User ID (e.g. AB1234)', type: 'text' },
              { key: 'password', label: 'Login Password', type: 'password' },
            ].map(f => (
              <div key={f.key} className="field">
                <label>{f.label}</label>
                <input
                  type={f.type}
                  className="input"
                  name={`zerodha-${f.key}`}
                  value={form[f.key as keyof ZerodhaCredentials]}
                  onChange={e => setForm({ ...form, [f.key]: e.target.value })}
                  autoComplete={f.type === 'password' ? 'new-password' : 'off'}
                />
              </div>
            ))}
          </div>
          <div className="field">
            <label>TOTP Secret (base32)</label>
            <input
              type="password"
              className="input"
              name="zerodha-totp-secret"
              value={form.totp_secret}
              onChange={e => setForm({ ...form, totp_secret: e.target.value })}
              autoComplete="new-password"
            />
            <div className="faint" style={{ fontSize: 10.5, marginTop: 4 }}>
              The base32 string from Zerodha 2FA setup — not the 6-digit code. Credentials are encrypted at rest.
            </div>
          </div>
          <div className="field">
            <label>Product type</label>
            <select
              className="input"
              name="zerodha-product-type"
              value={form.product_type}
              onChange={e => setForm({ ...form, product_type: e.target.value as 'MIS' | 'NRML' })}
            >
              <option value="MIS">MIS — intraday, auto-squared-off same day</option>
              <option value="NRML">NRML — carried forward across days (needed for multi-day option holds)</option>
            </select>
            <div className="faint" style={{ fontSize: 10.5, marginTop: 4 }}>
              Applies to every order this connection places, including protective GTTs.
            </div>
          </div>

          {msg && (
            <div style={{
              fontSize: 12, padding: '8px 12px', borderRadius: 7,
              background: msgKind === 'ok' ? 'var(--pos-dim)' : 'var(--neg-dim)',
              color: msgKind === 'ok' ? 'var(--pos)' : 'var(--neg)',
              border: `1px solid ${msgKind === 'ok' ? 'color-mix(in srgb, var(--pos) 25%, transparent)' : 'color-mix(in srgb, var(--neg) 25%, transparent)'}`,
            }}>
              {msg}
            </div>
          )}

          <div className="row">
            <button
              className="btn primary"
              onClick={save}
              disabled={saving || !form.api_key || !form.api_secret || !form.user_id}
            >
              {saving ? 'Saving…' : 'Save & Connect'}
            </button>
          </div>
        </div>
      </div>

      {/* Dhan credentials */}
      <div className="card">
        <div className="card-head">
          <span className="title">Dhan</span>
          {dhanStatus?.configured
            ? <Badge tone="pos"><CheckCircle size={11} style={{ marginRight: 4 }} />Configured</Badge>
            : <Badge>Not configured</Badge>
          }
        </div>
        <div className="card-pad stack" style={{ gap: 14 }}>
          <div className="faint" style={{ fontSize: 11 }}>
            Free — no subscription, unlike Zerodha's Kite Connect (₹500/mo). Generate an access token at
            dhan.co (Profile → DhanHQ Trading APIs). PIN + TOTP secret are optional, only needed for
            automatic daily token refresh.
          </div>
          {dhanStatus?.configured && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 8,
              border: '1px solid var(--border)',
            }}>
              <div style={{ fontSize: 12 }}>
                <span className="faint">Client ID: </span>
                <span className="mono-num">{dhanStatus.client_id ?? '—'}</span>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <button className="btn ghost sm" onClick={() => checkConnection('Dhan Primary')} disabled={checking === 'Dhan Primary'}>
                  {checking === 'Dhan Primary' ? 'Checking…' : 'Check connection'}
                </button>
                <button className="btn ghost sm" onClick={removeDhan} style={{ color: 'var(--neg)' }}>Remove</button>
              </div>
            </div>
          )}

          <div className="grid-2">
            <div className="field">
              <label>Client ID</label>
              <input
                type="text"
                className="input"
                name="dhan-client-id"
                value={dhanForm.client_id}
                onChange={e => setDhanForm({ ...dhanForm, client_id: e.target.value })}
                autoComplete="off"
              />
            </div>
            <div className="field">
              <label>Access Token</label>
              <input
                type="password"
                className="input"
                name="dhan-access-token"
                value={dhanForm.access_token}
                onChange={e => setDhanForm({ ...dhanForm, access_token: e.target.value })}
                autoComplete="new-password"
              />
            </div>
            <div className="field">
              <label>PIN (optional)</label>
              <input
                type="password"
                className="input"
                name="dhan-pin"
                value={dhanForm.pin}
                onChange={e => setDhanForm({ ...dhanForm, pin: e.target.value })}
                autoComplete="new-password"
              />
            </div>
            <div className="field">
              <label>TOTP Secret (optional, base32)</label>
              <input
                type="password"
                className="input"
                name="dhan-totp-secret"
                value={dhanForm.totp_secret}
                onChange={e => setDhanForm({ ...dhanForm, totp_secret: e.target.value })}
                autoComplete="new-password"
              />
            </div>
          </div>
          <div className="field">
            <label>Product type</label>
            <select
              className="input"
              name="dhan-product-type"
              value={dhanForm.product_type}
              onChange={e => setDhanForm({ ...dhanForm, product_type: e.target.value as 'INTRADAY' | 'MARGIN' })}
            >
              <option value="INTRADAY">INTRADAY — auto-squared-off same day</option>
              <option value="MARGIN">MARGIN — carried forward across days (needed for multi-day option holds)</option>
            </select>
            <div className="faint" style={{ fontSize: 10.5, marginTop: 4 }}>
              Applies to every order this connection places, including protective Forever Orders.
            </div>
          </div>

          {dhanMsg && (
            <div style={{
              fontSize: 12, padding: '8px 12px', borderRadius: 7,
              background: dhanMsgKind === 'ok' ? 'var(--pos-dim)' : 'var(--neg-dim)',
              color: dhanMsgKind === 'ok' ? 'var(--pos)' : 'var(--neg)',
              border: `1px solid ${dhanMsgKind === 'ok' ? 'color-mix(in srgb, var(--pos) 25%, transparent)' : 'color-mix(in srgb, var(--neg) 25%, transparent)'}`,
            }}>
              {dhanMsg}
            </div>
          )}

          <div className="row">
            <button
              className="btn primary"
              onClick={saveDhan}
              disabled={dhanSaving || !dhanForm.client_id || !dhanForm.access_token}
            >
              {dhanSaving ? 'Saving…' : 'Save & Connect'}
            </button>
          </div>
        </div>
      </div>

      {/* Paper engine info */}
      <div className="card card-pad" style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8, background: 'var(--surface-2)',
          border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <Wifi size={15} style={{ color: 'var(--text-dim)' }} />
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 3 }}>Paper engine</div>
          <div className="faint" style={{ fontSize: 11.5 }}>
            Always available — no broker credentials required. Simulates fills at mid-price with configurable slippage.
            Switch any strategy instance to Paper mode to trade without real money.
          </div>
        </div>
        <Badge tone="pos">Active</Badge>
      </div>

      {/* Active connections */}
      {brokers.length > 0 && (
        <div className="card" style={{ overflow: 'hidden' }}>
          <div className="card-head">
            <span className="title">Active connections</span>
          </div>
          <table className="tbl">
            <thead>
              <tr>
                <th>Name</th>
                <th>Broker</th>
                <th>Status</th>
                <th>Last error</th>
                <th>Failover target</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {brokers.map(b => (
                <tr key={b.name}>
                  <td style={{ fontWeight: 500 }}>{b.name}</td>
                  <td className="dim">{b.broker_name}</td>
                  <td>
                    <Badge tone={b.status === 'connected' ? 'pos' : b.status === 'error' ? 'neg' : undefined}>
                      {b.status}
                    </Badge>
                    {b.health && b.health.consecutive_failures > 0 && (
                      <div className="faint" style={{ fontSize: 10, marginTop: 2 }}>
                        {b.health.consecutive_failures} consecutive healthcheck failure(s)
                        {b.health.failover_triggered && ' — failed over'}
                      </div>
                    )}
                  </td>
                  <td className="faint" style={{ fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {b.last_error ?? '—'}
                  </td>
                  <td>
                    <select
                      className="input"
                      style={{ fontSize: 12, padding: '4px 6px' }}
                      value={b.failover_connection_name ?? ''}
                      disabled={settingFailoverFor === b.name}
                      onChange={e => setFailoverTarget(b.name, e.target.value)}
                    >
                      <option value="">None — exit-only failover disabled</option>
                      {brokers.filter(other => other.name !== b.name).map(other => (
                        <option key={other.name} value={other.name}>{other.name}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <div className="row" style={{ gap: 6 }}>
                      <button
                        className="btn ghost sm"
                        onClick={() => reconnect(b.name)}
                        disabled={reconnecting === b.name}
                      >
                        {reconnecting === b.name ? 'Reconnecting…' : 'Reconnect'}
                      </button>
                      {b.failover_connection_name && (
                        <button
                          className="btn ghost sm"
                          onClick={() => triggerFailoverNow(b.name)}
                          disabled={triggeringFailoverFor === b.name}
                          title={`Exit all open positions via ${b.failover_connection_name}`}
                        >
                          {triggeringFailoverFor === b.name ? 'Failing over…' : 'Failover now'}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Data Providers tab ──────────────────────────────────────────────────────

function DataProvidersTab() {
  const [providers, setProviders] = useState<DataProviderClass[]>([])
  const [loading, setLoading] = useState(true)
  const [forms, setForms] = useState<Record<string, { api_key: string; api_secret: string }>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [msg, setMsg] = useState('')

  const load = () => {
    api.dataProviders.classes().then(r => {
      setProviders(r.providers)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const saveCreds = async (name: string) => {
    const form = forms[name] ?? { api_key: '', api_secret: '' }
    setSaving(name)
    setMsg('')
    try {
      await api.dataProviders.saveCredentials(name, form)
      setMsg(`${name} credentials saved`)
      load()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(null)
    }
  }

  const removeCreds = async (name: string) => {
    if (!confirm(`Remove ${name} credentials?`)) return
    try {
      await api.dataProviders.deleteCredentials(name)
      setMsg(`${name} credentials removed`)
      load()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Remove failed')
    }
  }

  const capBadges = (caps: DataProviderClass['capabilities']) => {
    const labels: [keyof DataProviderClass['capabilities'], string][] = [
      ['supports_equity', 'Equity'],
      ['supports_futures', 'Futures'],
      ['supports_options', 'Options'],
      ['supports_forex', 'Forex'],
    ]
    return labels.filter(([k]) => caps[k]).map(([, label]) => <Badge key={label}>{label}</Badge>)
  }

  if (loading) return <div className="faint" style={{ fontSize: 12 }}>Loading…</div>

  return (
    <div className="stack">
      <div className="faint" style={{ fontSize: 11.5 }}>
        Historical data sources for backtesting — pick whichever fits per backtest run (see the Backtest page's
        Source option). Same drop-a-file plugin pattern as strategies and brokers: adding TrueData or a
        TradingView-based forex source later is just a new file in <code>data_providers/</code>, no changes here.
      </div>

      {providers.map(p => (
        <div key={p.name} className="card">
          <div className="card-head">
            <span className="title">{p.name}</span>
            {p.configured
              ? <Badge tone="pos"><CheckCircle size={11} style={{ marginRight: 4 }} />Ready</Badge>
              : <Badge tone="warn">Not configured</Badge>
            }
          </div>
          <div className="card-pad stack" style={{ gap: 12 }}>
            <div className="dim" style={{ fontSize: 11.5, lineHeight: 1.5 }}>{p.description}</div>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              {capBadges(p.capabilities)}
              {p.capabilities.max_lookback_days && (
                <Badge>{p.capabilities.max_lookback_days}d lookback</Badge>
              )}
            </div>

            {p.capabilities.requires_broker && (
              <div className="faint" style={{ fontSize: 11 }}>
                Reuses a connected broker — configure it under the Brokers tab, not here.
              </div>
            )}

            {p.capabilities.requires_credentials && (
              <>
                <div className="grid-2">
                  {(p.credential_fields.length > 0 ? p.credential_fields : [
                    { key: 'api_key' as const, label: 'API key', type: 'text' },
                    { key: 'api_secret' as const, label: 'API secret', type: 'password' },
                  ]).map(f => (
                    <div key={f.key} className="field">
                      <label>{f.label}</label>
                      <input
                        type={f.type}
                        className="input"
                        name={`${p.name}-${f.key}`}
                        value={forms[p.name]?.[f.key] ?? ''}
                        onChange={e => setForms({ ...forms, [p.name]: { ...(forms[p.name] ?? { api_key: '', api_secret: '' }), [f.key]: e.target.value } })}
                        autoComplete={f.type === 'password' ? 'new-password' : 'off'}
                      />
                    </div>
                  ))}
                </div>
                <div className="row" style={{ gap: 8 }}>
                  <button
                    className="btn primary sm"
                    onClick={() => saveCreds(p.name)}
                    disabled={saving === p.name || !forms[p.name]?.api_key}
                  >
                    {saving === p.name ? 'Saving…' : 'Save'}
                  </button>
                  {p.configured && (
                    <button className="btn ghost sm" onClick={() => removeCreds(p.name)} style={{ color: 'var(--neg)' }}>
                      Remove
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      ))}

      {providers.length === 0 && (
        <div className="card card-pad" style={{ textAlign: 'center', padding: 40 }}>
          <Database size={20} style={{ color: 'var(--text-faint)', marginBottom: 8 }} />
          <div className="faint" style={{ fontSize: 12 }}>No data providers discovered — check data_providers/</div>
        </div>
      )}

      <CoverageAndBackfill providers={providers} />

      {msg && (
        <div style={{
          fontSize: 12, padding: '8px 12px', borderRadius: 7,
          background: msg.includes('saved') || msg.includes('removed') ? 'var(--pos-dim)' : 'var(--neg-dim)',
          color: msg.includes('saved') || msg.includes('removed') ? 'var(--pos)' : 'var(--neg)',
        }}>
          {msg}
        </div>
      )}
    </div>
  )
}

// ── Coverage & backfill (CP3: "own the data") ───────────────────────────────

function CoverageAndBackfill({ providers }: { providers: DataProviderClass[] }) {
  const [coverage, setCoverage] = useState<BarCoverage[]>([])
  const [jobs, setJobs] = useState<BackfillJob[]>([])
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState('')

  const [provider, setProvider] = useState('')
  const [symbol, setSymbol] = useState('')
  const [exchange, setExchange] = useState('NFO')
  const [instrumentType, setInstrumentType] = useState('option')
  const [timeframe, setTimeframe] = useState('1d')
  const [fromDate, setFromDate] = useState(() => {
    const d = new Date(); d.setFullYear(d.getFullYear() - 2)
    return d.toISOString().slice(0, 10)
  })
  const [toDate, setToDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [starting, setStarting] = useState(false)

  const load = () => {
    Promise.all([api.data.coverage(), api.data.backfillJobs()])
      .then(([c, j]) => { setCoverage(c.coverage); setJobs(j.jobs) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    if (providers.length > 0 && !provider) setProvider(providers[0].name)
    // Poll while any job is still in flight — cheap, and the only way to see
    // a long backfill (2-5 years) progress without a websocket for it.
    const interval = setInterval(() => {
      setJobs(prev => {
        if (prev.some(j => j.status === 'queued' || j.status === 'running')) load()
        return prev
      })
    }, 3000)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const startBackfill = async () => {
    if (!provider || !symbol.trim()) return
    setStarting(true)
    setMsg('')
    try {
      await api.data.backfill({
        provider_name: provider, symbol: symbol.trim(), exchange,
        instrument_type: instrumentType, timeframe, from_date: fromDate, to_date: toDate,
      })
      setMsg('Backfill started — check status below.')
      load()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Failed to start backfill')
    } finally {
      setStarting(false)
    }
  }

  const jobTone = (status: BackfillJob['status']) =>
    status === 'done' ? 'pos' : status === 'failed' ? 'neg' : 'warn'

  return (
    <div className="card">
      <div className="card-head">
        <span className="title">Coverage &amp; backfill</span>
      </div>
      <div className="card-pad stack" style={{ gap: 14 }}>
        <div className="faint" style={{ fontSize: 11.5 }}>
          What's already cached locally (zero provider calls on repeat backtests over the same range), and a way
          to pull years of history in one go instead of one backtest at a time. Long ranges run in the background
          — for a real multi-year run, <code>scripts/backfill.py</code> is resumable if it gets interrupted.
        </div>

        <div className="grid-2">
          <div className="field">
            <label>Provider</label>
            <select className="input" value={provider} onChange={e => setProvider(e.target.value)}>
              {providers.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Symbol</label>
            <input className="input" value={symbol} onChange={e => setSymbol(e.target.value)} placeholder="NIFTY26AUGFUT" />
          </div>
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
        <div className="field">
          <label>Timeframe</label>
          <select className="input" value={timeframe} onChange={e => setTimeframe(e.target.value)}>
            {['1d', '1h', '15m', '5m', '1m'].map(tf => <option key={tf} value={tf}>{tf}</option>)}
          </select>
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
        <div>
          <button className="btn primary sm" onClick={startBackfill} disabled={starting || !provider || !symbol.trim()}>
            {starting ? 'Starting…' : 'Start backfill'}
          </button>
        </div>

        {jobs.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th>Provider</th><th>Symbol</th><th>Range</th><th>Status</th><th className="num">Bars</th>
              </tr>
            </thead>
            <tbody>
              {jobs.slice().reverse().slice(0, 8).map(j => (
                <tr key={j.id}>
                  <td className="faint" style={{ fontSize: 11 }}>{j.provider_name}</td>
                  <td style={{ fontSize: 11 }}>{j.symbol}</td>
                  <td className="faint mono-num" style={{ fontSize: 10.5 }}>{j.from_date} → {j.to_date}</td>
                  <td><Badge tone={jobTone(j.status)}>{j.status}</Badge></td>
                  <td className="num mono-num">{j.bars_fetched ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {!loading && coverage.length > 0 && (
          <>
            <div className="faint" style={{ fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', marginTop: 4 }}>
              Cached ranges
            </div>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Symbol</th><th>Exchange</th><th>Timeframe</th><th>Provider</th><th>Range</th>
                </tr>
              </thead>
              <tbody>
                {coverage.slice(0, 20).map(c => (
                  <tr key={`${c.symbol}-${c.exchange}-${c.timeframe}-${c.provider_name}`}>
                    <td style={{ fontSize: 11 }}>{c.symbol === '*' ? <span className="faint">all (whole-file)</span> : c.symbol}</td>
                    <td className="faint" style={{ fontSize: 11 }}>{c.exchange}</td>
                    <td className="faint" style={{ fontSize: 11 }}>{c.timeframe}</td>
                    <td className="faint" style={{ fontSize: 11 }}>{c.provider_name}</td>
                    <td className="mono-num" style={{ fontSize: 10.5 }}>{c.from_date} → {c.to_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {msg && (
          <div style={{
            fontSize: 12, padding: '8px 12px', borderRadius: 7,
            background: msg.includes('started') ? 'var(--pos-dim)' : 'var(--neg-dim)',
            color: msg.includes('started') ? 'var(--pos)' : 'var(--neg)',
          }}>
            {msg}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Risk tab ─────────────────────────────────────────────────────────────────

function RiskTab() {
  const [limits, setLimits] = useState<RiskLimits>({
    daily_loss_pct: 2,
    per_trade_risk_pct: 0.5,
    max_open_positions: 5,
    position_size_cap: 50000,
    ops_limit: 10,
    burst_window: 60,
  })
  const [opsUsed, setOpsUsed] = useState(0)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.settings.getRiskLimits().then(setLimits).catch(() => {})
    api.risk.status().then(r => {
      setOpsUsed(Math.round(r.ops_limit * 0.3))
    }).catch(() => {})
  }, [])

  const save = async () => {
    setSaving(true)
    setMsg('')
    try {
      await api.settings.saveRiskLimits(limits)
      setMsg('Risk limits saved')
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const opsPct = limits.ops_limit > 0 ? Math.min(100, Math.round((opsUsed / limits.ops_limit) * 100)) : 0

  return (
    <div className="stack">
      {/* Per-instance caps */}
      <div className="card">
        <div className="card-head">
          <span className="title">Per-instance caps</span>
          <Shield size={14} style={{ color: 'var(--text-faint)' }} />
        </div>
        <div className="card-pad stack" style={{ gap: 14 }}>
          <div className="grid-2">
            {[
              { key: 'daily_loss_pct', label: 'Daily loss limit (%)', step: '0.1', min: '0', max: '100' },
              { key: 'per_trade_risk_pct', label: 'Per-trade risk (%)', step: '0.1', min: '0', max: '10' },
              { key: 'max_open_positions', label: 'Max open positions', step: '1', min: '1', max: '100' },
              { key: 'position_size_cap', label: 'Position size cap (₹)', step: '1000', min: '0', max: '10000000' },
            ].map(f => (
              <div key={f.key} className="field">
                <label>{f.label}</label>
                <input
                  type="number"
                  className="input"
                  step={f.step}
                  min={f.min}
                  max={f.max}
                  value={limits[f.key as keyof RiskLimits]}
                  onChange={e => setLimits({ ...limits, [f.key]: parseFloat(e.target.value) || 0 })}
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* OPS throttle */}
      <div className="card">
        <div className="card-head">
          <span className="title">OPS throttle</span>
          <span className="faint" style={{ fontSize: 11 }}>orders per second</span>
        </div>
        <div className="card-pad stack" style={{ gap: 14 }}>
          <div className="grid-2">
            <div className="field">
              <label>OPS limit</label>
              <input
                type="number"
                className="input"
                step="1"
                min="1"
                max="100"
                value={limits.ops_limit}
                onChange={e => setLimits({ ...limits, ops_limit: parseInt(e.target.value) || 1 })}
              />
            </div>
            <div className="field">
              <label>Burst window (s)</label>
              <input
                type="number"
                className="input"
                step="1"
                min="1"
                max="300"
                value={limits.burst_window}
                onChange={e => setLimits({ ...limits, burst_window: parseInt(e.target.value) || 1 })}
              />
            </div>
          </div>

          <div>
            <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
              <span className="faint" style={{ fontSize: 11 }}>Current usage</span>
              <span className="faint mono-num" style={{ fontSize: 11 }}>{opsUsed} / {limits.ops_limit} OPS</span>
            </div>
            <div className="prog">
              <span style={{
                width: `${opsPct}%`,
                background: opsPct > 80 ? 'var(--neg)' : opsPct > 60 ? 'var(--warn)' : undefined,
              }} />
            </div>
          </div>
        </div>
      </div>

      {msg && (
        <div style={{
          fontSize: 12, padding: '8px 12px', borderRadius: 7,
          background: msg.includes('saved') ? 'var(--pos-dim)' : 'var(--neg-dim)',
          color: msg.includes('saved') ? 'var(--pos)' : 'var(--neg)',
        }}>
          {msg}
        </div>
      )}

      <div className="row">
        <button className="btn primary" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save risk limits'}
        </button>
      </div>

      <ReconciliationPanel />
    </div>
  )
}

// M01 (automation-platform-spec/08-JOBS-POSTMARKET.md): a non-CLEAN report
// blocks trading until acknowledged here -- see xillion/api/reconciliation.py.
function ReconciliationPanel() {
  const toast = useToast()
  const [reports, setReports] = useState<ReconciliationReport[]>([])
  const [loading, setLoading] = useState(true)
  const [acking, setAcking] = useState<number | null>(null)

  const load = () => {
    api.reconciliation.reports(20)
      .then(r => setReports(r.reports))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const acknowledge = async (id: number) => {
    setAcking(id)
    try {
      const res = await api.reconciliation.acknowledge(id)
      toast('ok', res.trading_resumed ? 'Acknowledged — trading resumed' : 'Acknowledged')
      load()
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Acknowledge failed')
    } finally {
      setAcking(null)
    }
  }

  const unresolved = reports.filter(r => r.status !== 'CLEAN' && !r.acknowledged)

  return (
    <div className="card">
      <div className="card-head">
        <span className="title">Reconciliation (M01)</span>
        <span className="faint" style={{ fontSize: 11 }}>daily broker-vs-internal position check</span>
      </div>
      <div className="card-pad stack" style={{ gap: 10 }}>
        {loading && <span className="faint" style={{ fontSize: 12 }}>Loading…</span>}
        {!loading && reports.length === 0 && (
          <span className="faint" style={{ fontSize: 12 }}>No reconciliation reports yet — M01 runs at 15:45 IST on trading days.</span>
        )}
        {unresolved.length > 0 && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
            padding: '8px 12px', borderRadius: 7, background: 'var(--neg-dim)', color: 'var(--neg)',
          }}>
            <AlertTriangle size={14} />
            {unresolved.length} unresolved discrepanc{unresolved.length === 1 ? 'y' : 'ies'} — trading is paused until acknowledged
          </div>
        )}
        {reports.slice(0, 10).map(r => (
          <div key={r.id} className="row" style={{ justifyContent: 'space-between', fontSize: 12, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
            <div className="stack" style={{ gap: 2 }}>
              <span>
                <strong>{r.trading_date}</strong> · {r.broker_name} ·{' '}
                <span style={{ color: r.status === 'CLEAN' ? 'var(--pos)' : 'var(--neg)' }}>{r.status}</span>
              </span>
              {r.status !== 'CLEAN' && (
                <span className="faint" style={{ fontSize: 11 }}>
                  {r.position_mismatches.length} position mismatch(es), {r.eod_open_positions.length} open at EOD,{' '}
                  {r.order_mismatches.length} order mismatch(es)
                  {r.funds_mismatch && `, funds off by ${r.funds_mismatch.diff}`}
                  {r.acknowledged && ` — acknowledged by ${r.acknowledged_by ?? 'unknown'} at ${r.acknowledged_at}`}
                </span>
              )}
            </div>
            {r.status !== 'CLEAN' && !r.acknowledged && (
              <button className="btn ghost sm" disabled={acking === r.id} onClick={() => acknowledge(r.id)}>
                {acking === r.id ? 'Acknowledging…' : 'Acknowledge'}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Notifications tab ─────────────────────────────────────────────────────────

function NotificationsTab() {
  const toast = useToast()
  const [settings, setSettings] = useState<NotificationSettings>({
    telegram_bot_token: '',
    telegram_chat_id: '',
    on_strategy_start_stop: true,
    on_order_filled: true,
    on_order_rejected: true,
    on_drawdown_breach: true,
    on_kill_switch: true,
  })
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState('')

  const sendTest = async () => {
    setTesting(true)
    try {
      await api.settings.testNotifications()
      toast('ok', 'Test message sent — check your Telegram chat')
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Test message failed')
    } finally {
      setTesting(false)
    }
  }

  useEffect(() => {
    api.settings.getNotifications().then(setSettings).catch(() => {})
  }, [])

  const save = async () => {
    setSaving(true)
    setMsg('')
    try {
      await api.settings.saveNotifications(settings)
      setMsg('Notification settings saved')
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const toggles: { key: keyof NotificationSettings; label: string; desc: string }[] = [
    { key: 'on_strategy_start_stop', label: 'Strategy start / stop', desc: 'When a strategy instance starts or stops running' },
    { key: 'on_order_filled', label: 'Order filled', desc: 'When an order is successfully filled by the broker' },
    { key: 'on_order_rejected', label: 'Order rejected', desc: 'When an order is rejected or fails to place' },
    { key: 'on_drawdown_breach', label: 'Drawdown breach', desc: 'When daily loss limit is reached on any instance' },
    { key: 'on_kill_switch', label: 'Kill switch triggered', desc: 'When the global kill switch is activated' },
  ]

  return (
    <div className="stack">
      {/* Telegram config */}
      <div className="card">
        <div className="card-head">
          <span className="title">Telegram bot</span>
          <Bell size={14} style={{ color: 'var(--text-faint)' }} />
        </div>
        <div className="card-pad stack" style={{ gap: 14 }}>
          <div className="grid-2">
            <div className="field">
              <label>Bot token</label>
              <input
                type="password"
                className="input"
                name="telegram-bot-token"
                placeholder="123456:ABC-DEF…"
                value={settings.telegram_bot_token}
                onChange={e => setSettings({ ...settings, telegram_bot_token: e.target.value })}
                autoComplete="new-password"
              />
            </div>
            <div className="field">
              <label>Chat ID</label>
              <input
                type="text"
                className="input"
                name="telegram-chat-id"
                placeholder="-100123456789"
                value={settings.telegram_chat_id}
                onChange={e => setSettings({ ...settings, telegram_chat_id: e.target.value })}
                autoComplete="off"
              />
            </div>
          </div>
          <div className="faint" style={{ fontSize: 11 }}>
            Create a bot via @BotFather, add it to your channel, and paste the token + chat ID above.
          </div>
          <div className="row">
            <button className="btn ghost sm" onClick={sendTest} disabled={testing}>
              {testing ? 'Sending…' : 'Send test message'}
            </button>
            <span className="faint" style={{ fontSize: 11 }}>Uses the currently saved token — save first if you just changed it.</span>
          </div>
        </div>
      </div>

      {/* Alert toggles */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div className="card-head">
          <span className="title">Alert events</span>
        </div>
        <div>
          {toggles.map((t, i) => (
            <div
              key={t.key}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 16px',
                borderTop: i === 0 ? '1px solid var(--border)' : undefined,
                borderBottom: '1px solid var(--border)',
              }}
            >
              <div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{t.label}</div>
                <div className="faint" style={{ fontSize: 11, marginTop: 2 }}>{t.desc}</div>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 8 }}>
                <span className="faint" style={{ fontSize: 11 }}>
                  {settings[t.key] ? 'On' : 'Off'}
                </span>
                <div
                  onClick={() => setSettings({ ...settings, [t.key]: !settings[t.key] })}
                  style={{
                    width: 36, height: 20, borderRadius: 10, cursor: 'pointer', transition: 'background 0.2s',
                    // --accent is the button-fill token (near-white in dark
                    // mode, near-black in light) -- using it here made an
                    // "on" toggle render as a near-white track behind a
                    // white knob, indistinguishable from off. --pos is the
                    // real semantic "on/positive" color used everywhere
                    // else (the Dev-page "tailing" badge, etc).
                    background: settings[t.key] ? 'var(--pos)' : 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    position: 'relative',
                  }}
                >
                  <div style={{
                    position: 'absolute', top: 2,
                    left: settings[t.key] ? 18 : 2,
                    width: 14, height: 14, borderRadius: '50%',
                    background: settings[t.key] ? '#fff' : 'var(--text-faint)',
                    transition: 'left 0.2s',
                  }} />
                </div>
              </label>
            </div>
          ))}
        </div>
      </div>

      {msg && (
        <div style={{
          fontSize: 12, padding: '8px 12px', borderRadius: 7,
          background: msg.includes('saved') ? 'var(--pos-dim)' : 'var(--neg-dim)',
          color: msg.includes('saved') ? 'var(--pos)' : 'var(--neg)',
        }}>
          {msg}
        </div>
      )}

      <div className="row">
        <button className="btn primary" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save notifications'}
        </button>
      </div>
    </div>
  )
}

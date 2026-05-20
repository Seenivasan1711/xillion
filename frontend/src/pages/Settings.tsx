import { useEffect, useState } from 'react'
import { CheckCircle, QrCode, Shield, Smartphone, Bell, User, AlertTriangle, Wifi } from 'lucide-react'
import { api } from '../lib/api'
import type { ZerodhaCredentials, NotificationSettings, RiskLimits, BrokerStatus } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { Badge } from '../components/ui'

type Tab = 'brokers' | 'risk' | 'notifications' | 'account' | 'danger'

const TABS: { id: Tab; label: string }[] = [
  { id: 'brokers', label: 'Brokers' },
  { id: 'risk', label: 'Risk' },
  { id: 'notifications', label: 'Notifications' },
  { id: 'account', label: 'Account' },
  { id: 'danger', label: 'Danger zone' },
]

export default function Settings() {
  const { user, refresh } = useAuth()
  const [tab, setTab] = useState<Tab>('brokers')

  return (
    <div className="stack">
      <div className="h-page">
        <div>
          <h1>Settings</h1>
          <div className="sub">Credentials, risk controls, notifications, account</div>
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
      {tab === 'risk'         && <RiskTab />}
      {tab === 'notifications' && <NotificationsTab />}
      {tab === 'account'      && <AccountTab user={user} refresh={refresh} />}
      {tab === 'danger'       && <DangerTab />}
    </div>
  )
}

// ── Brokers tab ──────────────────────────────────────────────────────────────

function BrokersTab() {
  const [zerodhaStatus, setZerodhaStatus] = useState<{
    configured: boolean
    api_key_preview?: string
    user_id?: string
    updated_at?: string
  } | null>(null)
  const [form, setForm] = useState<ZerodhaCredentials>({
    api_key: '', api_secret: '', user_id: '', password: '', totp_secret: '',
  })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [msgKind, setMsgKind] = useState<'ok' | 'err'>('ok')
  const [brokers, setBrokers] = useState<BrokerStatus[]>([])
  const [reconnecting, setReconnecting] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.settings.getZerodha(), api.brokers.connections()]).then(([z, b]) => {
      setZerodhaStatus(z)
      setBrokers(b.connections)
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
                  value={form[f.key as keyof ZerodhaCredentials]}
                  onChange={e => setForm({ ...form, [f.key]: e.target.value })}
                  autoComplete="off"
                />
              </div>
            ))}
          </div>
          <div className="field">
            <label>TOTP Secret (base32)</label>
            <input
              type="password"
              className="input"
              value={form.totp_secret}
              onChange={e => setForm({ ...form, totp_secret: e.target.value })}
              autoComplete="off"
            />
            <div className="faint" style={{ fontSize: 10.5, marginTop: 4 }}>
              The base32 string from Zerodha 2FA setup — not the 6-digit code. Credentials are encrypted at rest.
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
                  </td>
                  <td className="faint" style={{ fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {b.last_error ?? '—'}
                  </td>
                  <td>
                    <button
                      className="btn ghost sm"
                      onClick={() => reconnect(b.name)}
                      disabled={reconnecting === b.name}
                    >
                      {reconnecting === b.name ? 'Reconnecting…' : 'Reconnect'}
                    </button>
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
    </div>
  )
}

// ── Notifications tab ─────────────────────────────────────────────────────────

function NotificationsTab() {
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
  const [msg, setMsg] = useState('')

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
                placeholder="123456:ABC-DEF…"
                value={settings.telegram_bot_token}
                onChange={e => setSettings({ ...settings, telegram_bot_token: e.target.value })}
                autoComplete="off"
              />
            </div>
            <div className="field">
              <label>Chat ID</label>
              <input
                type="text"
                className="input"
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
                    background: settings[t.key] ? 'var(--accent)' : 'var(--surface-2)',
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

// ── Account tab ───────────────────────────────────────────────────────────────

interface AccountTabProps {
  user: { id: number; username: string; has_totp: boolean; last_login_at: string | null } | null
  refresh: () => Promise<void>
}

function AccountTab({ user, refresh }: AccountTabProps) {
  const [totpSetupData, setTotpSetupData] = useState<{ secret: string; uri: string } | null>(null)
  const [totpCode, setTotpCode] = useState('')
  const [totpLoading, setTotpLoading] = useState(false)
  const [totpMsg, setTotpMsg] = useState('')

  const startTotpSetup = async () => {
    setTotpMsg('')
    setTotpLoading(true)
    try {
      const data = await api.auth.totpSetup()
      setTotpSetupData(data)
    } catch (e) {
      setTotpMsg(e instanceof Error ? e.message : 'Failed to start TOTP setup')
    } finally {
      setTotpLoading(false)
    }
  }

  const verifyTotp = async () => {
    if (!totpSetupData || totpCode.length !== 6) return
    setTotpLoading(true)
    setTotpMsg('')
    try {
      await api.auth.totpVerify(totpSetupData.secret, totpCode)
      setTotpMsg('2FA enabled successfully')
      setTotpSetupData(null)
      setTotpCode('')
      await refresh()
    } catch (e) {
      setTotpMsg(e instanceof Error ? e.message : 'Verification failed')
    } finally {
      setTotpLoading(false)
    }
  }

  const disableTotp = async () => {
    if (!confirm('Disable 2FA? This reduces account security.')) return
    setTotpLoading(true)
    setTotpMsg('')
    try {
      await api.auth.totpDisable()
      setTotpMsg('2FA disabled')
      await refresh()
    } catch (e) {
      setTotpMsg(e instanceof Error ? e.message : 'Failed to disable 2FA')
    } finally {
      setTotpLoading(false)
    }
  }

  return (
    <div className="stack">
      {/* Profile info */}
      <div className="card">
        <div className="card-head">
          <span className="title">Profile</span>
          <User size={14} style={{ color: 'var(--text-faint)' }} />
        </div>
        <div className="card-pad stack" style={{ gap: 14 }}>
          <div className="grid-2">
            <div className="field">
              <label>Username</label>
              <input
                className="input"
                value={user?.username ?? ''}
                readOnly
                style={{ opacity: 0.6, cursor: 'not-allowed' }}
              />
            </div>
            <div className="field">
              <label>Last login</label>
              <input
                className="input"
                value={user?.last_login_at ? new Date(user.last_login_at).toLocaleString('en-IN') : '—'}
                readOnly
                style={{ opacity: 0.6, cursor: 'not-allowed' }}
              />
            </div>
          </div>
          <div className="faint" style={{ fontSize: 11 }}>
            Username and email changes are managed via environment variables. Contact your administrator.
          </div>
        </div>
      </div>

      {/* 2FA */}
      <div className="card">
        <div className="card-head">
          <span className="title">Two-factor authentication</span>
          {user?.has_totp
            ? <Badge tone="pos"><CheckCircle size={11} style={{ marginRight: 4 }} />Enabled</Badge>
            : <Badge tone="warn">Not configured</Badge>
          }
        </div>
        <div className="card-pad stack" style={{ gap: 14 }}>
          {!totpSetupData && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 8,
              border: '1px solid var(--border)',
            }}>
              <div style={{ fontSize: 12 }}>
                {user?.has_totp
                  ? <span style={{ color: 'var(--pos)' }}>Your account is protected with a TOTP authenticator app.</span>
                  : <span style={{ color: 'var(--warn)' }}>Enable 2FA to secure kill-switch and danger-zone actions.</span>
                }
              </div>
              {user?.has_totp ? (
                <button className="btn ghost sm" onClick={disableTotp} disabled={totpLoading} style={{ color: 'var(--neg)' }}>
                  Disable 2FA
                </button>
              ) : (
                <button className="btn primary sm" onClick={startTotpSetup} disabled={totpLoading}>
                  Enable 2FA
                </button>
              )}
            </div>
          )}

          {totpSetupData && (
            <div className="stack" style={{ gap: 12 }}>
              <div className="faint" style={{ fontSize: 12 }}>
                Scan with Google Authenticator, Authy, or any TOTP app:
              </div>
              <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
                <div style={{
                  background: '#fff', padding: 8, borderRadius: 8,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <QrCode size={80} style={{ color: '#111' }} />
                </div>
                <div style={{ flex: 1 }}>
                  <div className="faint" style={{ fontSize: 11, marginBottom: 6 }}>Manual entry secret:</div>
                  <code style={{
                    display: 'block', fontSize: 11, fontFamily: 'var(--font-mono)',
                    background: 'var(--surface-2)', border: '1px solid var(--border)',
                    padding: '6px 10px', borderRadius: 6, wordBreak: 'break-all',
                    color: 'var(--text)',
                  }}>
                    {totpSetupData.secret}
                  </code>
                </div>
              </div>

              <div className="field">
                <label><Smartphone size={11} style={{ marginRight: 4 }} />6-digit code from your app</label>
                <div className="row" style={{ gap: 8 }}>
                  <input
                    type="text"
                    inputMode="numeric"
                    className="input"
                    value={totpCode}
                    onChange={e => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    placeholder="000000"
                    maxLength={6}
                    autoFocus
                    style={{ width: 120, textAlign: 'center', letterSpacing: '0.25em', fontSize: 18, fontFamily: 'var(--font-mono)' }}
                  />
                  <button className="btn primary" onClick={verifyTotp} disabled={totpLoading || totpCode.length !== 6}>
                    Verify &amp; enable
                  </button>
                  <button className="btn ghost" onClick={() => { setTotpSetupData(null); setTotpCode('') }}>
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}

          {totpMsg && (
            <div style={{
              fontSize: 12, padding: '8px 12px', borderRadius: 7,
              background: totpMsg.includes('success') || totpMsg.includes('disabled') ? 'var(--pos-dim)' : 'var(--neg-dim)',
              color: totpMsg.includes('success') || totpMsg.includes('disabled') ? 'var(--pos)' : 'var(--neg)',
            }}>
              {totpMsg}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Danger zone tab ───────────────────────────────────────────────────────────

function DangerTab() {
  const [resetConfirm, setResetConfirm] = useState('')
  const [wipeConfirm, setWipeConfirm] = useState('')
  const [busy, setBusy] = useState<'reset' | 'wipe' | null>(null)
  const [msg, setMsg] = useState('')
  const [msgKind, setMsgKind] = useState<'ok' | 'err'>('ok')

  const resetData = async () => {
    if (resetConfirm !== 'RESET') return
    setBusy('reset')
    setMsg('')
    try {
      await api.settings.resetData()
      setMsg('All trade and log data has been reset.')
      setMsgKind('ok')
      setResetConfirm('')
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Reset failed')
      setMsgKind('err')
    } finally {
      setBusy(null)
    }
  }

  const wipeAll = async () => {
    if (wipeConfirm !== 'WIPE EVERYTHING') return
    setBusy('wipe')
    setMsg('')
    try {
      await api.settings.wipeAll()
      setMsg('All data wiped. Reloading…')
      setMsgKind('ok')
      setWipeConfirm('')
      setTimeout(() => window.location.reload(), 1500)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Wipe failed')
      setMsgKind('err')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="stack">
      <div style={{
        display: 'flex', gap: 10, alignItems: 'center', padding: '10px 14px',
        background: 'var(--neg-dim)', borderRadius: 8,
        border: '1px solid color-mix(in srgb, var(--neg) 30%, transparent)',
        fontSize: 12, color: 'var(--neg)',
      }}>
        <AlertTriangle size={14} style={{ flexShrink: 0 }} />
        These actions are irreversible. Proceed only if you know what you're doing.
      </div>

      {/* Reset data */}
      <div className="card">
        <div className="card-head">
          <span className="title">Reset all data</span>
        </div>
        <div className="card-pad stack" style={{ gap: 12 }}>
          <div style={{ fontSize: 12 }}>
            Clears all trade history, log records, and strategy run data. Broker credentials and settings are preserved.
          </div>
          <div className="field">
            <label>Type <strong>RESET</strong> to confirm</label>
            <input
              className="input"
              value={resetConfirm}
              onChange={e => setResetConfirm(e.target.value)}
              placeholder="RESET"
              style={{ maxWidth: 240, fontFamily: 'var(--font-mono)' }}
            />
          </div>
          <button
            className="btn"
            onClick={resetData}
            disabled={resetConfirm !== 'RESET' || busy !== null}
            style={{
              background: resetConfirm === 'RESET' ? 'color-mix(in srgb, var(--neg) 15%, transparent)' : undefined,
              color: resetConfirm === 'RESET' ? 'var(--neg)' : undefined,
              border: '1px solid color-mix(in srgb, var(--neg) 40%, transparent)',
            }}
          >
            {busy === 'reset' ? 'Resetting…' : 'Reset all data'}
          </button>
        </div>
      </div>

      {/* Wipe everything */}
      <div className="card" style={{ borderColor: 'color-mix(in srgb, var(--neg) 35%, transparent)' }}>
        <div className="card-head">
          <span className="title" style={{ color: 'var(--neg)' }}>Wipe everything</span>
        </div>
        <div className="card-pad stack" style={{ gap: 12 }}>
          <div style={{ fontSize: 12 }}>
            Deletes all data including users, credentials, strategies, and configuration. The application will restart
            in setup mode. This cannot be undone.
          </div>
          <div className="field">
            <label>Type <strong>WIPE EVERYTHING</strong> to confirm</label>
            <input
              className="input"
              value={wipeConfirm}
              onChange={e => setWipeConfirm(e.target.value)}
              placeholder="WIPE EVERYTHING"
              style={{ maxWidth: 300, fontFamily: 'var(--font-mono)' }}
            />
          </div>
          <button
            className="btn"
            onClick={wipeAll}
            disabled={wipeConfirm !== 'WIPE EVERYTHING' || busy !== null}
            style={{
              background: wipeConfirm === 'WIPE EVERYTHING' ? 'var(--neg)' : undefined,
              color: wipeConfirm === 'WIPE EVERYTHING' ? '#fff' : undefined,
              border: '1px solid color-mix(in srgb, var(--neg) 60%, transparent)',
            }}
          >
            {busy === 'wipe' ? 'Wiping…' : 'Wipe everything'}
          </button>
        </div>
      </div>

      {msg && (
        <div style={{
          fontSize: 12, padding: '8px 12px', borderRadius: 7,
          background: msgKind === 'ok' ? 'var(--pos-dim)' : 'var(--neg-dim)',
          color: msgKind === 'ok' ? 'var(--pos)' : 'var(--neg)',
        }}>
          {msg}
        </div>
      )}
    </div>
  )
}

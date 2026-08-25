import { useState } from 'react'
import { AlertTriangle, CheckCircle, QrCode, Smartphone, User } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { Badge } from '../components/ui'

type Tab = 'account' | 'danger'

const TABS: { id: Tab; label: string }[] = [
  { id: 'account', label: 'Account' },
  { id: 'danger', label: 'Danger zone' },
]

export default function Settings() {
  const { user, refresh } = useAuth()
  const [tab, setTab] = useState<Tab>('account')

  return (
    <div className="stack">
      <div className="h-page">
        <div>
          <h1>Settings</h1>
          <div className="sub">Your account and irreversible actions</div>
        </div>
      </div>

      <div className="tabs">
        {TABS.map(t => (
          <button key={t.id} className={`tab${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'account' && <AccountTab user={user} refresh={refresh} />}
      {tab === 'danger'  && <DangerTab />}
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
                    name="totp-verify-code"
                    autoComplete="one-time-code"
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
              name="danger-zone-reset-confirm"
              autoComplete="off"
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
              name="danger-zone-wipe-confirm"
              autoComplete="off"
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

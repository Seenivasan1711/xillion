import { useEffect, useState } from 'react'
import { CheckCircle, QrCode, Settings as SettingsIcon, Shield, Smartphone, Wifi, Key } from 'lucide-react'
import { api } from '../lib/api'
import type { BrokerStatus, ZerodhaCredentials } from '../lib/api'
import { useAuth } from '../context/AuthContext'

export default function Settings() {
  const { user, refresh } = useAuth()

  // TOTP
  const [totpSetupData, setTotpSetupData] = useState<{ secret: string; uri: string } | null>(null)
  const [totpCode, setTotpCode] = useState('')
  const [totpLoading, setTotpLoading] = useState(false)
  const [totpMsg, setTotpMsg] = useState('')

  // Risk
  const [riskStatus, setRiskStatus] = useState<{
    kill_switch_active: boolean
    account_daily_loss: string
    ops_limit: number
  } | null>(null)

  // Brokers
  const [brokers, setBrokers] = useState<BrokerStatus[]>([])
  const [reconnecting, setReconnecting] = useState<string | null>(null)

  // Zerodha credentials
  const [zerodhaStatus, setZerodhaStatus] = useState<{
    configured: boolean
    api_key_preview?: string
    user_id?: string
    updated_at?: string
  } | null>(null)
  const [showZerodhaForm, setShowZerodhaForm] = useState(false)
  const [zForm, setZForm] = useState<ZerodhaCredentials>({
    api_key: '',
    api_secret: '',
    user_id: '',
    password: '',
    totp_secret: '',
  })
  const [zSaving, setZSaving] = useState(false)
  const [zMsg, setZMsg] = useState('')
  const [zMsgKind, setZMsgKind] = useState<'ok' | 'err'>('ok')

  const loadBrokerStatus = async () => {
    const [b, z] = await Promise.all([api.brokers.connections(), api.settings.getZerodha()])
    setBrokers(b.connections)
    setZerodhaStatus(z)
  }

  useEffect(() => {
    const load = async () => {
      try {
        const r = await api.risk.status()
        setRiskStatus(r)
        await loadBrokerStatus()
      } catch {
        // ignore
      }
    }
    load()
  }, [])

  const saveZerodha = async () => {
    setZSaving(true)
    setZMsg('')
    try {
      const res = await api.settings.saveZerodha(zForm)
      if (res.connection_status === 'connected') {
        setZMsg('Saved and connected successfully')
        setZMsgKind('ok')
      } else {
        setZMsg(`Saved, but connection failed: ${res.last_error ?? 'unknown error'}`)
        setZMsgKind('err')
      }
      setShowZerodhaForm(false)
      setZForm({ api_key: '', api_secret: '', user_id: '', password: '', totp_secret: '' })
      await loadBrokerStatus()
    } catch (e) {
      setZMsg(e instanceof Error ? e.message : 'Save failed')
      setZMsgKind('err')
    } finally {
      setZSaving(false)
    }
  }

  const removeZerodha = async () => {
    if (!confirm('Remove Zerodha credentials? You will need to re-enter them to reconnect.')) return
    try {
      await api.settings.deleteZerodha()
      setZMsg('Credentials removed')
      setZMsgKind('ok')
      await loadBrokerStatus()
    } catch (e) {
      setZMsg(e instanceof Error ? e.message : 'Remove failed')
      setZMsgKind('err')
    }
  }

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

  const reconnectBroker = async (name: string) => {
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
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <SettingsIcon size={22} />
        Settings
      </h1>

      {/* Account / 2FA */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-300 border-b border-gray-800 pb-3">
          <Shield size={16} />
          Two-Factor Authentication
        </div>

        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">
              {user?.has_totp ? (
                <span className="text-emerald-400 flex items-center gap-1">
                  <CheckCircle size={14} /> 2FA enabled
                </span>
              ) : (
                <span className="text-amber-400">2FA not configured</span>
              )}
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              {user?.has_totp
                ? 'Your account is protected with a TOTP authenticator app'
                : 'Enable 2FA to secure kill-switch actions'}
            </div>
          </div>
          {user?.has_totp ? (
            <button
              onClick={disableTotp}
              disabled={totpLoading}
              className="text-xs px-3 py-1.5 rounded-md border border-gray-700 text-gray-400 hover:text-gray-200 disabled:opacity-50"
            >
              Disable 2FA
            </button>
          ) : (
            !totpSetupData && (
              <button
                onClick={startTotpSetup}
                disabled={totpLoading}
                className="text-xs px-3 py-1.5 rounded-md bg-brand-600 hover:bg-brand-700 text-white disabled:opacity-50"
              >
                Enable 2FA
              </button>
            )
          )}
        </div>

        {totpSetupData && (
          <div className="space-y-3 pt-2 border-t border-gray-800">
            <div className="text-xs text-gray-400">
              Scan the QR code with your authenticator app (Google Authenticator, Authy, etc.):
            </div>
            <div className="flex items-start gap-4">
              <div className="bg-white p-2 rounded-md">
                <QrCode size={80} className="text-gray-900" />
                {/* Real QR would be rendered here — show the URI for manual entry */}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs text-gray-500 mb-1">Or enter this secret manually:</div>
                <code className="text-xs bg-gray-800 px-2 py-1 rounded font-mono break-all text-gray-200">
                  {totpSetupData.secret}
                </code>
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1 flex items-center gap-1">
                <Smartphone size={12} /> Enter the 6-digit code from your app to verify
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  className="input w-36 text-center text-xl tracking-widest font-mono py-1.5"
                  placeholder="000000"
                  maxLength={6}
                  autoFocus
                />
                <button
                  onClick={verifyTotp}
                  disabled={totpLoading || totpCode.length !== 6}
                  className="px-4 py-2 rounded-md bg-brand-600 hover:bg-brand-700 text-white text-sm disabled:opacity-50"
                >
                  Verify &amp; Enable
                </button>
                <button
                  onClick={() => { setTotpSetupData(null); setTotpCode('') }}
                  className="px-4 py-2 rounded-md border border-gray-700 text-gray-400 hover:text-gray-200 text-sm"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {totpMsg && (
          <p className={`text-sm ${totpMsg.includes('success') || totpMsg.includes('disabled') ? 'text-emerald-400' : 'text-rose-400'}`}>
            {totpMsg}
          </p>
        )}
      </section>

      {/* Zerodha Credentials */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-300 border-b border-gray-800 pb-3">
          <Key size={16} />
          Zerodha Credentials
        </div>

        {zerodhaStatus?.configured && !showZerodhaForm && (
          <div className="flex items-center justify-between">
            <div className="text-sm">
              <div className="flex items-center gap-2 text-emerald-400">
                <CheckCircle size={14} /> Configured
              </div>
              <div className="text-xs text-gray-500 mt-1">
                User: <span className="font-mono text-gray-300">{zerodhaStatus.user_id ?? '—'}</span> ·
                API key: <span className="font-mono text-gray-300">{zerodhaStatus.api_key_preview ?? '—'}</span>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowZerodhaForm(true)}
                className="text-xs px-3 py-1.5 rounded-md border border-gray-700 text-gray-300 hover:text-white"
              >
                Update
              </button>
              <button
                onClick={removeZerodha}
                className="text-xs px-3 py-1.5 rounded-md border border-rose-900 text-rose-400 hover:bg-rose-950"
              >
                Remove
              </button>
            </div>
          </div>
        )}

        {!zerodhaStatus?.configured && !showZerodhaForm && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-400">
              No Zerodha credentials configured. Add them to enable live trading and historical data.
            </p>
            <button
              onClick={() => setShowZerodhaForm(true)}
              className="text-xs px-3 py-1.5 rounded-md bg-brand-600 hover:bg-brand-700 text-white"
            >
              Configure
            </button>
          </div>
        )}

        {showZerodhaForm && (
          <div className="space-y-3 pt-2 border-t border-gray-800">
            {[
              { key: 'api_key', label: 'API Key', type: 'text' },
              { key: 'api_secret', label: 'API Secret', type: 'password' },
              { key: 'user_id', label: 'User ID (e.g. AB1234)', type: 'text' },
              { key: 'password', label: 'Login Password', type: 'password' },
              { key: 'totp_secret', label: 'TOTP Secret (base32)', type: 'password' },
            ].map((f) => (
              <label key={f.key} className="block">
                <span className="text-xs text-gray-400">{f.label}</span>
                <input
                  type={f.type}
                  value={zForm[f.key as keyof ZerodhaCredentials]}
                  onChange={(e) => setZForm({ ...zForm, [f.key]: e.target.value })}
                  className="mt-1 w-full bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-white font-mono"
                  autoComplete="off"
                />
              </label>
            ))}
            <p className="text-xs text-gray-500">
              Credentials are encrypted at rest. The TOTP secret is the base32 string from your Zerodha 2FA setup
              — not the 6-digit code.
            </p>
            <div className="flex gap-2 pt-2">
              <button
                onClick={saveZerodha}
                disabled={zSaving || !zForm.api_key || !zForm.api_secret || !zForm.user_id}
                className="px-4 py-2 rounded-md bg-brand-600 hover:bg-brand-700 text-white text-sm disabled:opacity-50"
              >
                {zSaving ? 'Saving & connecting…' : 'Save & Connect'}
              </button>
              <button
                onClick={() => {
                  setShowZerodhaForm(false)
                  setZForm({ api_key: '', api_secret: '', user_id: '', password: '', totp_secret: '' })
                }}
                className="px-4 py-2 rounded-md border border-gray-700 text-gray-400 hover:text-gray-200 text-sm"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {zMsg && (
          <p className={`text-sm ${zMsgKind === 'ok' ? 'text-emerald-400' : 'text-rose-400'}`}>{zMsg}</p>
        )}
      </section>

      {/* Broker Connections */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-300 border-b border-gray-800 pb-3">
          <Wifi size={16} />
          Broker Connections
        </div>

        {brokers.length === 0 ? (
          <p className="text-sm text-gray-500">No broker connections configured</p>
        ) : (
          <div className="space-y-2">
            {brokers.map((b) => (
              <div key={b.name} className="flex items-center justify-between py-2 border-b border-gray-800/50 last:border-0">
                <div>
                  <div className="text-sm font-medium">{b.name}</div>
                  <div className="text-xs text-gray-500">{b.broker_name}</div>
                  {b.last_error && (
                    <div className="text-xs text-rose-400 mt-0.5 max-w-xs truncate">{b.last_error}</div>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      b.status === 'connected'
                        ? 'bg-emerald-900/40 text-emerald-400'
                        : b.status === 'error'
                        ? 'bg-rose-900/40 text-rose-400'
                        : 'bg-gray-800 text-gray-500'
                    }`}
                  >
                    {b.status}
                  </span>
                  <button
                    onClick={() => reconnectBroker(b.name)}
                    disabled={reconnecting === b.name}
                    className="text-xs px-2 py-1 rounded-md border border-gray-700 text-gray-400 hover:text-gray-200 disabled:opacity-50"
                  >
                    {reconnecting === b.name ? 'Reconnecting…' : 'Reconnect'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Risk Status */}
      {riskStatus && (
        <section className="card space-y-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-gray-300 border-b border-gray-800 pb-3">
            <Shield size={16} />
            Risk Limits (read-only)
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div className="text-gray-500 text-xs">OPS Limit</div>
              <div className="font-mono">{riskStatus.ops_limit}/s</div>
            </div>
            <div>
              <div className="text-gray-500 text-xs">Account Daily Loss</div>
              <div className="font-mono">₹{riskStatus.account_daily_loss}</div>
            </div>
            <div>
              <div className="text-gray-500 text-xs">Kill Switch</div>
              <div className={riskStatus.kill_switch_active ? 'text-rose-400 font-bold' : 'text-emerald-400'}>
                {riskStatus.kill_switch_active ? 'ACTIVE' : 'Inactive'}
              </div>
            </div>
          </div>
          <p className="text-xs text-gray-600">
            Risk limits are configured via environment variables. See <code>.env.example</code>.
          </p>
        </section>
      )}
    </div>
  )
}

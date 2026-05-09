import { useEffect, useState } from 'react'
import { CheckCircle, QrCode, Settings as SettingsIcon, Shield, Smartphone, Wifi } from 'lucide-react'
import { api } from '../lib/api'
import type { BrokerStatus } from '../lib/api'
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

  useEffect(() => {
    const load = async () => {
      try {
        const [r, b] = await Promise.all([api.risk.status(), api.brokers.connections()])
        setRiskStatus(r)
        setBrokers(b.connections)
      } catch {
        // ignore
      }
    }
    load()
  }, [])

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

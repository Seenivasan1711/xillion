import { useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'

interface Props {
  onClose: () => void
  onFired: () => void
}

export default function KillSwitchModal({ onClose, onFired }: Props) {
  const { user } = useAuth()
  const [totp, setTotp] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleFire = async () => {
    setError('')
    setLoading(true)
    try {
      const res = await api.risk.activateKillSwitch(user?.has_totp ? totp : undefined)
      onFired()
      alert(
        `Kill switch fired.\nStopped: ${res.strategies_stopped} strategies\nCancelled: ${res.orders_cancelled} orders`
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to activate kill switch')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4">
      <div className="bg-gray-900 border border-red-800 rounded-xl w-full max-w-sm">
        <div className="flex items-center justify-between p-4 border-b border-red-800">
          <div className="flex items-center gap-2 text-red-400">
            <AlertTriangle size={18} />
            <h2 className="font-bold">KILL SWITCH</h2>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
            <X size={18} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          <div className="text-sm text-gray-300 space-y-1">
            <p>This will immediately:</p>
            <ul className="list-disc list-inside text-gray-400 space-y-0.5 ml-2">
              <li>Stop all running strategies</li>
              <li>Cancel all open orders</li>
            </ul>
          </div>

          {user?.has_totp && (
            <div>
              <label className="block text-sm text-gray-400 mb-1">Confirm with 2FA code</label>
              <input
                type="text"
                inputMode="numeric"
                value={totp}
                onChange={(e) => setTotp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="input w-full text-center text-2xl tracking-widest font-mono"
                placeholder="000000"
                maxLength={6}
                autoFocus
              />
            </div>
          )}

          {error && <p className="text-sm text-red-400">{error}</p>}

          <div className="flex gap-2">
            <button onClick={onClose} className="flex-1 px-4 py-2 rounded-md text-sm border border-gray-700 text-gray-400 hover:text-gray-200">
              Cancel
            </button>
            <button
              onClick={handleFire}
              disabled={loading || (user?.has_totp ? totp.length !== 6 : false)}
              className="flex-1 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-4 py-2 rounded-md text-sm font-bold transition-colors"
            >
              {loading ? 'Firing…' : 'KILL ALL'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

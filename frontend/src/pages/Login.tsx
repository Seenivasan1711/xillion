import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [requiresTotp, setRequiresTotp] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const result = await login(username, password, requiresTotp ? totpCode : undefined)
      if (result.requires_totp) {
        setRequiresTotp(true)
      } else {
        navigate('/')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <Zap size={36} className="text-brand-500 mx-auto mb-3" />
          <h1 className="text-2xl font-bold">Xillion</h1>
          <p className="text-sm text-gray-400 mt-1">Sign in to your trading platform</p>
        </div>

        <form onSubmit={handleSubmit} className="card space-y-4">
          {!requiresTotp ? (
            <>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="input w-full"
                  placeholder="admin"
                  autoFocus
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input w-full"
                  placeholder="••••••••"
                  required
                />
              </div>
            </>
          ) : (
            <div>
              <label className="block text-sm text-gray-400 mb-1">Authenticator code</label>
              <input
                type="text"
                inputMode="numeric"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="input w-full text-center text-2xl tracking-widest font-mono"
                placeholder="000000"
                autoFocus
                maxLength={6}
                required
              />
              <p className="text-xs text-gray-500 mt-2">
                Enter the 6-digit code from your authenticator app
              </p>
              <button
                type="button"
                onClick={() => { setRequiresTotp(false); setTotpCode('') }}
                className="text-xs text-gray-500 hover:text-gray-300 mt-1"
              >
                ← Back
              </button>
            </div>
          )}

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? 'Signing in…' : requiresTotp ? 'Verify' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}

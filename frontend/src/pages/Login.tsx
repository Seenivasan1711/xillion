import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import AuthShell from '../components/AuthShell'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [requiresTotp, setRequiresTotp] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login, needsSetup, loading: authLoading } = useAuth()
  const navigate = useNavigate()

  if (!authLoading && needsSetup) return <Navigate to="/setup" replace />

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
    <AuthShell
      eyebrow="Algorithmic trading"
      headline={'Systematic entries.\nManaged risk.\nNo guesswork.'}
      sub="Every order routed through the same risk engine, every trade logged for review. Built for discipline, not adrenaline."
    >
      <h2>Sign in</h2>
      <p className="auth-sub">Enter your workspace credentials</p>

      <form onSubmit={handleSubmit}>
        {!requiresTotp ? (
          <>
            <div className="auth-field">
              <label>Username</label>
              <input
                type="text"
                name="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="input"
                style={{ width: '100%' }}
                placeholder="admin"
                autoFocus
                required
              />
            </div>
            <div className="auth-field">
              <label>Password</label>
              <input
                type="password"
                name="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input"
                style={{ width: '100%' }}
                placeholder="••••••••"
                required
              />
            </div>
          </>
        ) : (
          <div className="auth-field">
            <label>Authenticator code</label>
            <input
              type="text"
              inputMode="numeric"
              name="totp-code"
              autoComplete="one-time-code"
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              className="input"
              style={{ width: '100%', textAlign: 'center', fontSize: 22, letterSpacing: '0.3em' }}
              placeholder="000000"
              autoFocus
              maxLength={6}
              required
            />
            <p style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 8 }}>
              Enter the 6-digit code from your authenticator app
            </p>
            <button
              type="button"
              onClick={() => { setRequiresTotp(false); setTotpCode('') }}
              style={{
                background: 'none', border: 0, padding: 0, marginTop: 6, cursor: 'pointer',
                fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)',
              }}
            >
              ← Back
            </button>
          </div>
        )}

        {error && (
          <div style={{
            fontSize: 12, padding: '8px 12px', borderRadius: 7, marginBottom: 14,
            background: 'var(--neg-dim)', color: 'var(--neg)',
          }}>
            {error}
          </div>
        )}

        <button type="submit" disabled={loading} className="btn-primary" style={{ width: '100%' }}>
          {loading ? 'Signing in…' : requiresTotp ? 'Verify' : 'Sign in'}
        </button>
      </form>
    </AuthShell>
  )
}

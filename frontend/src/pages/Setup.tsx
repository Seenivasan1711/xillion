import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import AuthShell from '../components/AuthShell'

export default function Setup() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { refresh } = useAuth()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    setLoading(true)
    try {
      await api.auth.setup(username, password)
      await refresh()
      navigate('/login')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Setup failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      eyebrow="First run"
      headline={'One workspace.\nOne owner.\nFull control.'}
      sub="Create the admin account for this deployment. There's no invite flow by design — this is a single-operator trading system, not a shared workspace."
    >
      <h2>Create account</h2>
      <p className="auth-sub">Set up your admin login to get started</p>

      <form onSubmit={handleSubmit}>
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
            minLength={3}
          />
        </div>

        <div className="auth-field">
          <label>Password</label>
          <input
            type="password"
            name="new-password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input"
            style={{ width: '100%' }}
            placeholder="At least 8 characters"
            required
            minLength={8}
          />
        </div>

        <div className="auth-field">
          <label>Confirm password</label>
          <input
            type="password"
            name="confirm-password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="input"
            style={{ width: '100%' }}
            placeholder="Repeat password"
            required
          />
        </div>

        {error && (
          <div style={{
            fontSize: 12, padding: '8px 12px', borderRadius: 7, marginBottom: 14,
            background: 'var(--neg-dim)', color: 'var(--neg)',
          }}>
            {error}
          </div>
        )}

        <button type="submit" disabled={loading} className="btn-primary" style={{ width: '100%' }}>
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </AuthShell>
  )
}

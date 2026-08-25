import { useEffect } from 'react'
import Logomark from './Logomark'

type Theme = 'dark' | 'light'

function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t
}

// Pre-login pages (Login/Setup) render outside Layout, which is the only
// place theme was ever applied to <html> before -- so this screen used to
// always render dark regardless of a saved preference from a prior
// session. Mirrors Layout.tsx's own load/apply logic.
function loadTheme(): Theme {
  return (localStorage.getItem('xillion-theme') as Theme) || 'dark'
}

export default function AuthShell({
  eyebrow, headline, sub, children,
}: {
  eyebrow: string
  headline: string
  sub: string
  children: React.ReactNode
}) {
  useEffect(() => { applyTheme(loadTheme()) }, [])

  return (
    <div className="auth-shell">
      <div className="auth-brand">
        <div className="aurora" />
        <div className="auth-brand-inner">
          <div className="auth-logo">
            <Logomark size={18} />
            <span>Xillion</span>
          </div>
          <div className="auth-copy">
            <div className="auth-eyebrow">{eyebrow}</div>
            <h1>{headline}</h1>
            <p>{sub}</p>
          </div>
          <div className="auth-flow">
            <span>Backtest</span>
            <span className="arrow">→</span>
            <span>Paper</span>
            <span className="arrow">→</span>
            <span>Live</span>
          </div>
        </div>
      </div>
      <div className="auth-form-side">
        <div className="auth-form-card">
          {children}
        </div>
      </div>
    </div>
  )
}

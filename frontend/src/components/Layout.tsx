import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  BarChart2, Bell, BookOpen, ChevronDown, CircleUserRound, Cpu, LogOut, Moon, Search,
  SlidersHorizontal, Skull, Sun, Terminal, TrendingUp,
  LayoutDashboard, Link, Pause, X, RefreshCw, ArrowDownRight,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { wsClient } from '../lib/ws'
import { api } from '../lib/api'
import Logomark from './Logomark'
import CommandPalette from './CommandPalette'
import NotificationBell from './NotificationBell'

// ── Helpers ────────────────────────────────────────────────────────────────
type Theme = 'dark' | 'light'

function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t
}

function loadTheme(): Theme {
  return (localStorage.getItem('xillion-theme') as Theme) || 'dark'
}

function saveTheme(t: Theme) {
  localStorage.setItem('xillion-theme', t)
  applyTheme(t)
}

function loadCollapsed(): boolean {
  return localStorage.getItem('xillion-sidebar') === 'collapsed'
}

function saveCollapsed(v: boolean) {
  localStorage.setItem('xillion-sidebar', v ? 'collapsed' : 'expanded')
}

const CRUMB_LABELS: Record<string, string> = {
  '/': 'Dashboard',
  '/strategies': 'Strategies',
  '/trades': 'Trades',
  '/alerts': 'Alerts',
  '/journal': 'Journal',
  '/backtest': 'Backtest',
  '/logs': 'Dev',
  '/configuration': 'Configuration',
  '/settings': 'Settings',
}

// ── Kill dropdown ──────────────────────────────────────────────────────────
function KillMenu({
  killActive,
  onKill,
  onReset,
}: {
  killActive: boolean
  onKill: () => void
  onReset: () => void
}) {
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false)
        setConfirm(false)
      }
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <button
        className="icon-btn"
        onClick={() => setOpen(!open)}
        title="Safety controls"
        style={{ color: killActive ? 'var(--neg)' : undefined }}
      >
        <Skull size={16} />
      </button>

      {open && (
        <div className="menu">
          <div className="head">Safety</div>
          <div className="item" onClick={() => { setOpen(false); alert('Pausing all strategies…') }}>
            <Pause size={14} /> Pause all running strategies
          </div>
          <div className="item" onClick={() => { setOpen(false); alert('Cancelling open orders…') }}>
            <X size={14} /> Cancel all open orders
          </div>
          <div className="item" onClick={() => { setOpen(false); alert('Flattening positions…') }}>
            <ArrowDownRight size={14} /> Flatten all positions
          </div>
          <div className="sep" />

          {!killActive ? (
            !confirm ? (
              <div className="item danger" onClick={() => setConfirm(true)}>
                <Skull size={14} /> Trigger kill switch…
              </div>
            ) : (
              <>
                <div className="head" style={{ color: 'var(--neg)' }}>Confirm — irreversible until reset</div>
                <div style={{ padding: '6px 10px', fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.5 }}>
                  Halts all strategies, cancels open orders, blocks all new order submissions.
                </div>
                <div style={{ display: 'flex', gap: 6, padding: 6 }}>
                  <button className="btn ghost sm" style={{ flex: 1 }} onClick={() => setConfirm(false)}>Cancel</button>
                  <button
                    className="btn danger sm"
                    style={{ flex: 1 }}
                    onClick={() => { onKill(); setOpen(false); setConfirm(false) }}
                  >
                    Kill all
                  </button>
                </div>
              </>
            )
          ) : (
            <div className="item" onClick={() => { onReset(); setOpen(false) }}>
              <RefreshCw size={14} /> Reset kill switch
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── User dropdown ─────────────────────────────────────────────────────────
// Rendered via a portal into document.body: the sidebar has overflow:hidden
// (needed to clip nav labels during the collapse animation) and its own
// backdrop-filter, which creates a containing block that traps even
// position:fixed children -- a plain absolute/fixed dropdown here would be
// silently clipped to the sidebar's own width instead of floating over the
// page like every other dropdown in this app.
function UserMenu({
  username, collapsed, onSignOut,
}: {
  username: string
  collapsed: boolean
  onSignOut: () => void
}) {
  const [open, setOpen] = useState(false)
  const [coords, setCoords] = useState<{ left: number; bottom: number } | null>(null)
  const chipRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const initials = username.slice(0, 2).toUpperCase() || 'U'

  const toggle = () => {
    if (!open && chipRef.current) {
      const r = chipRef.current.getBoundingClientRect()
      setCoords({ left: r.left, bottom: window.innerHeight - r.top + 8 })
    }
    setOpen(!open)
  }

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => {
      const target = e.target as Node
      if (chipRef.current?.contains(target) || menuRef.current?.contains(target)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  return (
    <>
      <div ref={chipRef} className="user-chip" onClick={toggle} role="button">
        <div className="avatar">{initials.toLowerCase()}</div>
        <div className="meta">
          <span className="name">{username}</span>
          <span className="sub">Owner · IST</span>
        </div>
        {!collapsed && <ChevronDown size={13} className="chev" style={{ transform: open ? 'rotate(180deg)' : undefined }} />}
      </div>

      {open && coords && createPortal(
        <div ref={menuRef} className="menu menu-portal" style={{ left: coords.left, bottom: coords.bottom }}>
          <div className="head">Signed in as</div>
          <div style={{ padding: '0 10px 8px', fontSize: 12, color: 'var(--text)' }}>{username}</div>
          <div className="sep" />
          <div className="item danger" onClick={() => { setOpen(false); onSignOut() }}>
            <LogOut size={14} /> Sign out
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}

// ── Main Layout ────────────────────────────────────────────────────────────
export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [theme, setTheme] = useState<Theme>(loadTheme)
  const [collapsed, setCollapsed] = useState(loadCollapsed)
  const [killActive, setKillActive] = useState(false)
  const [brokerStatus, setBrokerStatus] = useState<{ label: string; ok: boolean } | null>(null)
  const [feedLatency, setFeedLatency] = useState<number | null>(null)
  const [runnerCount, setRunnerCount] = useState(0)
  const [tradeCount, setTradeCount] = useState(0)
  const [cmdkOpen, setCmdkOpen] = useState(false)

  // Global ⌘K / Ctrl+K to open the command palette from anywhere
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCmdkOpen((v) => !v)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  // Apply initial theme
  useEffect(() => { applyTheme(theme) }, [])

  const toggleTheme = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    saveTheme(next)
  }

  const toggleCollapsed = () => {
    const next = !collapsed
    setCollapsed(next)
    saveCollapsed(next)
  }

  // Poll risk + broker status
  useEffect(() => {
    const load = async () => {
      try {
        const [riskRes, healthRes, instRes] = await Promise.all([
          api.risk.status().catch(() => null),
          api.health().catch(() => null),
          api.instances.list().catch(() => null),
        ])
        if (riskRes) setKillActive(riskRes.kill_switch_active)
        if (healthRes?.brokers?.length) {
          const b = healthRes.brokers[0]
          setBrokerStatus({ label: `${b.broker_name} · ${b.status}`, ok: b.status === 'connected' })
        }
        if (instRes) {
          setRunnerCount(instRes.instances.filter(i => i.status === 'running').length)
        }
      } catch { /* ignore */ }
    }
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [])

  // WebSocket — kill_switch, tick latency, trade count
  useEffect(() => {
    let count = 0
    const unsub = wsClient.subscribe((event) => {
      if (event.type === 'kill_switch') setKillActive(Boolean(event.active))
      if (event.type === 'heartbeat' && typeof event.lag === 'number') setFeedLatency(event.lag as number)
      if (event.type === 'trade') { count++; setTradeCount(count) }
    })
    return unsub
  }, [])

  const handleKill = async () => {
    try {
      await api.risk.activateKillSwitch()
      setKillActive(true)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Kill switch failed')
    }
  }

  const handleReset = async () => {
    try {
      await api.risk.resetKillSwitch()
      setKillActive(false)
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Reset failed')
    }
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const path = location.pathname
  const crumb = CRUMB_LABELS[path] ?? 'Xillion'

  const navItems = [
    { key: '/',           label: 'Dashboard',  Icon: LayoutDashboard, pill: null },
    { key: '/strategies', label: 'Strategies', Icon: Cpu,             pill: runnerCount > 0 ? String(runnerCount) : null },
    { key: '/trades',     label: 'Trades',     Icon: TrendingUp,      pill: tradeCount > 0 ? String(tradeCount) : null },
    { key: '/alerts',     label: 'Alerts',     Icon: Bell,            pill: null },
    { key: '/journal',    label: 'Journal',    Icon: BookOpen,        pill: null },
    { key: '/backtest',   label: 'Backtest',   Icon: BarChart2,       pill: null },
    { key: '/logs',       label: 'Dev',        Icon: Terminal,        pill: null },
    { key: '/configuration', label: 'Configuration', Icon: SlidersHorizontal, pill: null },
    { key: '/settings',   label: 'Settings',   Icon: CircleUserRound, pill: null },
  ]

  const systemItems = [
    { key: '/configuration', label: 'Brokers', Icon: Link, pill: brokerStatus ? (brokerStatus.ok ? '1/1' : '0/1') : null },
  ]

  return (
    <>
      <div className="aurora" />
      <div className={`app ${collapsed ? 'collapsed' : ''}`}>

        {/* ── Sidebar ── */}
        <aside className="sidebar">
          <div className="brand">
            <div className="logo logo-toggle" onClick={toggleCollapsed} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
              <Logomark />
            </div>
            <span className="word">Xillion</span>
          </div>

          <div className="section-label">Workspace</div>
          <nav>
            {navItems.map(({ key, label, Icon, pill }) => (
              <div
                key={key}
                className={`nav-item ${path === key ? 'active' : ''}`}
                onClick={() => navigate(key)}
                title={label}
              >
                <Icon size={16} className="ico" />
                <span className="lbl">{label}</span>
                {pill && <span className="pill">{pill}</span>}
              </div>
            ))}
          </nav>

          <div className="section-label">System</div>
          <nav>
            {systemItems.map(({ key, label, Icon, pill }) => (
              <div
                key={key}
                className={`nav-item ${path === key ? 'active' : ''}`}
                onClick={() => navigate(key)}
                title={label}
              >
                <Icon size={16} className="ico" />
                <span className="lbl">{label}</span>
                {pill && <span className="pill">{pill}</span>}
              </div>
            ))}
          </nav>

          <div className="foot">
            <UserMenu username={user?.username ?? '—'} collapsed={collapsed} onSignOut={handleLogout} />
          </div>
        </aside>

        {/* ── Main column ── */}
        <div className="main">
          {killActive && (
            <div className="kill-banner">
              <Skull size={14} />
              <strong>KILL SWITCH ACTIVE</strong>
              <span style={{ color: 'color-mix(in srgb, var(--neg) 70%, var(--text-dim))' }}>
                — all strategies halted, new orders blocked
              </span>
              <div style={{ flex: 1 }} />
              <button className="btn ghost sm" onClick={handleReset}>Reset</button>
            </div>
          )}

          {/* Topbar */}
          <div className="topbar">
            <div className="crumbs">
              <span className="dim">Xillion</span>
              <span className="sep">/</span>
              <span className="here">{crumb}</span>
            </div>

            <div style={{ flex: 1 }} />

            {/* Global search — opens the ⌘K command palette rather than
                filtering in place, so it's a real trigger, not decoration */}
            <div
              onClick={() => setCmdkOpen(true)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer',
                background: 'var(--surface-2)', border: '1px solid var(--border)',
                borderRadius: 9, padding: '0 10px', height: 30, width: 260,
              }}
            >
              <Search size={13} style={{ color: 'var(--text-faint)', flexShrink: 0 }} />
              <input
                placeholder="Search strategies, symbols…"
                readOnly
                style={{
                  flex: 1, background: 'transparent', border: 0, outline: 'none',
                  fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text)', cursor: 'pointer',
                }}
              />
              <span className="kbd">⌘K</span>
            </div>

            {/* Status dots */}
            {brokerStatus && (
              <span className={`status-dot ${brokerStatus.ok ? '' : 'bad'}`}>
                <span className="dot" />
                {brokerStatus.label}
              </span>
            )}
            {feedLatency !== null && (
              <span className={`status-dot ${feedLatency > 100 ? 'warn' : ''}`}>
                <span className="dot" />
                Feed {feedLatency}ms
              </span>
            )}

            {/* Theme toggle */}
            <button className="icon-btn" onClick={toggleTheme} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>

            {/* Notifications */}
            <NotificationBell />

            {/* Kill menu */}
            <KillMenu killActive={killActive} onKill={handleKill} onReset={handleReset} />
          </div>

          {/* Page content */}
          <div className="scroll">
            <Outlet />
          </div>
        </div>
      </div>

      <CommandPalette
        open={cmdkOpen}
        onClose={() => setCmdkOpen(false)}
        toggleTheme={toggleTheme}
        killActive={killActive}
        onKill={handleKill}
      />
    </>
  )
}

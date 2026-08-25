import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Cpu, TrendingUp, Bell, BookOpen, BarChart2,
  Terminal, Settings, Link, Sun, Skull,
} from 'lucide-react'

export interface Command {
  id: string
  label: string
  section?: string
  Icon: typeof LayoutDashboard
  action: () => void
  keywords?: string
}

function useCommands(navigate: (path: string) => void, toggleTheme: () => void): Command[] {
  return [
    { id: 'dashboard', label: 'Dashboard', section: 'Go to', Icon: LayoutDashboard, action: () => navigate('/') },
    { id: 'strategies', label: 'Strategies', section: 'Go to', Icon: Cpu, action: () => navigate('/strategies') },
    { id: 'trades', label: 'Trades', section: 'Go to', Icon: TrendingUp, action: () => navigate('/trades') },
    { id: 'alerts', label: 'Alerts', section: 'Go to', Icon: Bell, action: () => navigate('/alerts') },
    { id: 'journal', label: 'Journal', section: 'Go to', Icon: BookOpen, action: () => navigate('/journal') },
    { id: 'backtest', label: 'Backtest', section: 'Go to', Icon: BarChart2, action: () => navigate('/backtest') },
    { id: 'logs', label: 'Logs', section: 'Go to', Icon: Terminal, action: () => navigate('/logs') },
    { id: 'settings', label: 'Settings', section: 'Go to', Icon: Settings, action: () => navigate('/settings'), keywords: 'brokers config data providers risk notifications account' },
    { id: 'brokers', label: 'Brokers', section: 'Go to', Icon: Link, action: () => navigate('/settings') },
    { id: 'theme', label: 'Toggle theme', section: 'Actions', Icon: Sun, action: toggleTheme, keywords: 'dark light mode' },
  ]
}

export default function CommandPalette({
  open, onClose, toggleTheme, killActive, onKill,
}: {
  open: boolean
  onClose: () => void
  toggleTheme: () => void
  killActive: boolean
  onKill: () => void
}) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const base = useCommands((path) => { navigate(path); onClose() }, () => { toggleTheme(); onClose() })
  const commands: Command[] = killActive ? base : [
    ...base,
    { id: 'kill', label: 'Trigger kill switch', section: 'Actions', Icon: Skull, action: () => { onKill(); onClose() }, keywords: 'emergency halt stop' },
  ]

  const filtered = commands.filter((c) => {
    const q = query.trim().toLowerCase()
    if (!q) return true
    return c.label.toLowerCase().includes(q) || (c.keywords ?? '').includes(q)
  })

  useEffect(() => {
    if (open) {
      setQuery('')
      setActiveIndex(0)
      setTimeout(() => inputRef.current?.focus(), 10)
    }
  }, [open])

  useEffect(() => { setActiveIndex(0) }, [query])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIndex((i) => Math.min(i + 1, filtered.length - 1)) }
      if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIndex((i) => Math.max(i - 1, 0)) }
      if (e.key === 'Enter') { e.preventDefault(); filtered[activeIndex]?.action() }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, filtered, activeIndex, onClose])

  if (!open) return null

  let lastSection = ''

  return (
    <div className="cmdk-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="cmdk-panel">
        <div className="cmdk-input-row">
          <span style={{ color: 'var(--text-faint)', fontSize: 13 }}>⌘K</span>
          <input
            ref={inputRef}
            className="cmdk-input"
            placeholder="Jump to a page or run an action…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
            name="command-palette-query"
          />
          <span className="kbd">Esc</span>
        </div>
        <div className="cmdk-list">
          {filtered.length === 0 && (
            <div style={{ padding: '18px 14px', fontSize: 12, color: 'var(--text-faint)', textAlign: 'center' }}>
              No matches.
            </div>
          )}
          {filtered.map((c, i) => {
            const showHeader = c.section && c.section !== lastSection
            lastSection = c.section ?? lastSection
            return (
              <div key={c.id}>
                {showHeader && <div className="cmdk-section">{c.section}</div>}
                <div
                  className={`cmdk-item ${i === activeIndex ? 'active' : ''}`}
                  onMouseEnter={() => setActiveIndex(i)}
                  onClick={c.action}
                >
                  <c.Icon size={14} className="ico" />
                  <span>{c.label}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

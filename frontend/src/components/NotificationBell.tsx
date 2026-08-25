import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, ArrowUpRight, ArrowDownRight, CircleDot } from 'lucide-react'
import { api } from '../lib/api'
import type { SignalLogEntry } from '../lib/api'

const SEEN_KEY = 'xillion-last-seen-signal-id'

function timeAgo(ts: string): string {
  const diffMs = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function NotificationBell() {
  const navigate = useNavigate()
  const [signals, setSignals] = useState<SignalLogEntry[]>([])
  const [open, setOpen] = useState(false)
  const [lastSeenId, setLastSeenId] = useState<number>(() => Number(localStorage.getItem(SEEN_KEY) ?? 0))
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const load = () => {
      api.signals.list({ limit: 15 }).then((res) => setSignals(res.signals)).catch(() => {})
    }
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const unreadCount = signals.filter((s) => s.id > lastSeenId).length

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next && signals.length > 0) {
      const newestId = Math.max(...signals.map((s) => s.id))
      setLastSeenId(newestId)
      localStorage.setItem(SEEN_KEY, String(newestId))
    }
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <button className="icon-btn" title="Notifications" style={{ position: 'relative' }} onClick={toggle}>
        <Bell size={16} />
        {unreadCount > 0 && (
          <span className="notif-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>
        )}
      </button>

      {open && (
        <div className="menu notif-menu">
          <div className="head">Recent alerts</div>
          {signals.length === 0 && (
            <div style={{ padding: '18px 14px', fontSize: 12, color: 'var(--text-faint)', textAlign: 'center' }}>
              No alerts yet.
            </div>
          )}
          {signals.map((s) => (
            <div key={s.id} className="notif-item" onClick={() => { setOpen(false); navigate('/alerts') }}>
              {s.signal_type === 'EXIT'
                ? <ArrowDownRight size={13} className="ico" style={{ color: 'var(--neg)' }} />
                : s.signal_type === 'ENTER'
                  ? <ArrowUpRight size={13} className="ico" style={{ color: 'var(--pos)' }} />
                  : <CircleDot size={13} className="ico" style={{ color: 'var(--info)' }} />}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.underlying_symbol} — {s.message}
                </div>
                <div style={{ fontSize: 10.5, color: 'var(--text-faint)', marginTop: 2 }}>{timeAgo(s.ts)}</div>
              </div>
            </div>
          ))}
          {signals.length > 0 && (
            <div className="item" style={{ justifyContent: 'center', color: 'var(--text-dim)' }} onClick={() => { setOpen(false); navigate('/alerts') }}>
              View all in Alerts
            </div>
          )}
        </div>
      )}
    </div>
  )
}

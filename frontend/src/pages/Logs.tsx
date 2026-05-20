import { useEffect, useRef, useState } from 'react'
import { Download, Trash2, Search } from 'lucide-react'
import { wsClient } from '../lib/ws'
import { Badge, SegmentedControl } from '../components/ui'

interface LogLine {
  id: number
  ts: string
  level: string
  source: string
  message: string
  fields: Record<string, unknown>
}

const LEVEL_MAP: Record<string, string> = {
  debug: 'dbg',
  info: 'info',
  warning: 'warn',
  warn: 'warn',
  error: 'err',
  critical: 'err',
}

export default function Logs() {
  const [logs, setLogs] = useState<LogLine[]>([])
  const [filter, setFilter] = useState('')
  const [level, setLevel] = useState('all')
  const [paused, setPaused] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const idRef = useRef(0)

  useEffect(() => {
    const unsub = wsClient.subscribe((event) => {
      if (paused || event.type !== 'log') return
      const line: LogLine = {
        id: ++idRef.current,
        ts: (event.ts as string) || new Date().toISOString(),
        level: (event.level as string) || 'info',
        source: (event.source as string) || 'system',
        message: (event.message as string) || JSON.stringify(event),
        fields: (event.fields as Record<string, unknown>) || {},
      }
      setLogs(prev => [...prev.slice(-500), line])
    })
    return unsub
  }, [paused])

  useEffect(() => {
    if (!paused) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs, paused])

  const filtered = logs.filter(l => {
    const lvl = l.level.toLowerCase()
    if (level !== 'all') {
      if (level === 'err' && lvl !== 'error' && lvl !== 'critical') return false
      if (level === 'warn' && lvl !== 'warning' && lvl !== 'warn') return false
      if (level === 'info' && lvl !== 'info') return false
      if (level === 'debug' && lvl !== 'debug') return false
    }
    if (filter && !l.message.toLowerCase().includes(filter.toLowerCase()) &&
        !l.source.toLowerCase().includes(filter.toLowerCase())) return false
    return true
  })

  const exportLogs = () => {
    const text = filtered.map(l => `${l.ts} [${l.level.toUpperCase()}] ${l.source}: ${l.message}`).join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `xillion-logs-${Date.now()}.txt`
    a.click()
  }

  return (
    <div className="stack">
      <div className="h-page">
        <div>
          <h1>Logs</h1>
          <div className="sub">Live engine output · scrollback retained for 24h</div>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={exportLogs} disabled={logs.length === 0}>
            <Download size={13} /> Download
          </button>
          <button className="btn ghost" onClick={() => setLogs([])} disabled={logs.length === 0}>
            <Trash2 size={13} /> Clear
          </button>
        </div>
      </div>

      <div className="card" style={{ overflow: 'hidden' }}>
        {/* Card header with embedded filter + controls */}
        <div className="card-head">
          <div className="row" style={{ gap: 10 }}>
            {/* Search */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--surface-2)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '0 10px', height: 28,
            }}>
              <Search size={12} style={{ color: 'var(--text-faint)', flexShrink: 0 }} />
              <input
                placeholder="filter…"
                value={filter}
                onChange={e => setFilter(e.target.value)}
                style={{
                  background: 'transparent', border: 0, outline: 'none',
                  fontFamily: 'var(--font-mono)', fontSize: 11.5,
                  color: 'var(--text)', width: 200,
                }}
              />
            </div>
            {/* Level segmented control */}
            <SegmentedControl
              options={[
                { value: 'all',   label: 'all'   },
                { value: 'info',  label: 'info'  },
                { value: 'warn',  label: 'warn'  },
                { value: 'err',   label: 'err'   },
                { value: 'debug', label: 'debug' },
              ]}
              value={level}
              onChange={setLevel}
            />
          </div>
          <div className="row" style={{ gap: 8 }}>
            {!paused
              ? <Badge tone="pos" dot>tailing</Badge>
              : <Badge>paused</Badge>
            }
            <span className="faint" style={{ fontSize: 11 }}>{filtered.length} lines</span>
            <button
              className="btn ghost sm"
              onClick={() => setPaused(p => !p)}
            >
              {paused ? 'Resume' : 'Pause'}
            </button>
          </div>
        </div>

        {/* Log stream */}
        <div style={{ maxHeight: '65vh', overflowY: 'auto', background: 'rgba(7,9,12,0.4)' }}>
          {filtered.length === 0 ? (
            <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-faint)', fontSize: 13 }}>
              {logs.length === 0 ? 'Waiting for log events from backend…' : 'No logs match your filters'}
            </div>
          ) : (
            filtered.map(l => {
              const cls = LEVEL_MAP[l.level.toLowerCase()] || 'dbg'
              return (
                <div key={l.id} className="log-line">
                  <span className="faint">
                    {new Date(l.ts).toLocaleString('en-IN', { hour12: false }).replace(',', '')}
                  </span>
                  <span className={`lvl ${cls}`}>{l.level.toUpperCase().slice(0, 5)}</span>
                  <span>
                    <span className="dim">{l.source}</span>
                    {'  '}
                    {l.message}
                  </span>
                </div>
              )
            })
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  )
}

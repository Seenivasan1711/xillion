import { useEffect, useRef, useState } from 'react'
import { Download, Filter, Terminal } from 'lucide-react'
import { wsClient } from '../lib/ws'

interface LogLine {
  id: number
  ts: string
  level: string
  source: string
  message: string
  fields: Record<string, unknown>
}

const LEVEL_COLOR: Record<string, string> = {
  debug: 'text-gray-500',
  info: 'text-sky-400',
  warning: 'text-amber-400',
  warn: 'text-amber-400',
  error: 'text-rose-400',
  critical: 'text-rose-300 font-bold',
}

export default function Logs() {
  const [logs, setLogs] = useState<LogLine[]>([])
  const [filter, setFilter] = useState('')
  const [levelFilter, setLevelFilter] = useState<string>('all')
  const [paused, setPaused] = useState(false)
  const [expanded, setExpanded] = useState<number | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const idRef = useRef(0)

  useEffect(() => {
    const unsub = wsClient.subscribe((event) => {
      if (paused) return
      if (event.type === 'log' || event.type === 'heartbeat' || event.type === 'tick') {
        if (event.type !== 'log') return
        const line: LogLine = {
          id: ++idRef.current,
          ts: (event.ts as string) || new Date().toISOString(),
          level: (event.level as string) || 'info',
          source: (event.source as string) || 'system',
          message: (event.message as string) || JSON.stringify(event),
          fields: (event.fields as Record<string, unknown>) || {},
        }
        setLogs((prev) => [...prev.slice(-500), line])
      }
    })
    return unsub
  }, [paused])

  useEffect(() => {
    if (!paused) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, paused])

  const filtered = logs.filter((l) => {
    if (levelFilter !== 'all' && l.level !== levelFilter) return false
    if (filter && !l.message.toLowerCase().includes(filter.toLowerCase()) &&
        !l.source.toLowerCase().includes(filter.toLowerCase())) return false
    return true
  })

  const exportLogs = () => {
    const text = filtered
      .map((l) => `${l.ts} [${l.level.toUpperCase()}] ${l.source}: ${l.message}`)
      .join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `xillion-logs-${Date.now()}.txt`
    a.click()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Terminal size={22} />
          Logs
        </h1>
        <div className="flex items-center gap-2">
          <button onClick={exportLogs} className="p-2 text-gray-500 hover:text-gray-300" title="Export">
            <Download size={16} />
          </button>
          <button
            onClick={() => setPaused((p) => !p)}
            className={`text-xs px-3 py-1.5 rounded-md border transition-colors ${
              paused
                ? 'border-amber-600 text-amber-400 hover:bg-amber-950/30'
                : 'border-gray-700 text-gray-400 hover:text-gray-200'
            }`}
          >
            {paused ? 'Resume' : 'Pause'}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search logs…"
            className="input w-full pl-8 py-1.5 text-sm"
          />
        </div>
        <select
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
          className="input py-1.5 text-sm"
        >
          {['all', 'debug', 'info', 'warning', 'error', 'critical'].map((l) => (
            <option key={l} value={l}>{l === 'all' ? 'All levels' : l}</option>
          ))}
        </select>
        {logs.length > 0 && (
          <button onClick={() => setLogs([])} className="text-xs text-gray-500 hover:text-gray-300">
            Clear
          </button>
        )}
      </div>

      {/* Log stream */}
      <div className="card font-mono text-xs space-y-0 max-h-[65vh] overflow-y-auto bg-gray-950">
        {filtered.length === 0 ? (
          <div className="py-12 text-center text-gray-600">
            {logs.length === 0 ? 'Waiting for log events from backend…' : 'No logs match your filters'}
          </div>
        ) : (
          filtered.map((l) => (
            <div key={l.id}>
              <div
                className="flex items-start gap-3 py-1 px-2 hover:bg-gray-900 cursor-pointer"
                onClick={() => setExpanded(expanded === l.id ? null : l.id)}
              >
                <span className="text-gray-600 flex-shrink-0 tabular-nums">
                  {new Date(l.ts).toLocaleTimeString()}
                </span>
                <span className={`w-16 flex-shrink-0 uppercase ${LEVEL_COLOR[l.level] || 'text-gray-400'}`}>
                  {l.level}
                </span>
                <span className="text-gray-500 flex-shrink-0 w-24 truncate">{l.source}</span>
                <span className="text-gray-300 truncate flex-1">{l.message}</span>
              </div>
              {expanded === l.id && Object.keys(l.fields).length > 0 && (
                <pre className="px-4 pb-2 text-[10px] text-gray-500 bg-gray-900/50">
                  {JSON.stringify(l.fields, null, 2)}
                </pre>
              )}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

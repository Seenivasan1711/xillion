import { useLayoutEffect, useRef, useState } from 'react'

interface Series {
  label: string
  data: number[]
  color: string
}

// Overlays 2+ equity curves on one chart, each normalized to % change from
// its own first value -- so two runs with different starting capital or a
// different number of bars are still visually comparable (added 2026-09-22
// for the backtest run-comparison feature; Sparkline is deliberately left
// single-series, this is a separate component rather than a rewrite of it).
export default function EquityCompareChart({ series, height = 220 }: { series: Series[]; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(400)

  useLayoutEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(() => {
      if (ref.current) setW(ref.current.clientWidth)
    })
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])

  const usable = series.filter(s => s.data.length > 1)
  if (usable.length === 0) return <div ref={ref} style={{ width: '100%', height }} />

  const normalized = usable.map(s => {
    const base = s.data[0] || 1
    return { ...s, pct: s.data.map(v => ((v - base) / base) * 100) }
  })

  const allPct = normalized.flatMap(s => s.pct)
  const min = Math.min(...allPct, 0)
  const max = Math.max(...allPct, 0)
  const range = max - min || 1
  const zeroY = height - 6 - ((0 - min) / range) * (height - 12)

  const pathFor = (pct: number[]) =>
    pct
      .map((v, i) => {
        const x = (i / (pct.length - 1)) * w
        const y = height - 6 - ((v - min) / range) * (height - 12)
        return `${i === 0 ? 'M' : 'L'}${x},${y}`
      })
      .join(' ')

  return (
    <div ref={ref} style={{ width: '100%' }}>
      <svg
        style={{ width: '100%', height, display: 'block' }}
        viewBox={`0 0 ${w} ${height}`}
        preserveAspectRatio="none"
      >
        <line x1={0} y1={zeroY} x2={w} y2={zeroY} stroke="var(--border)" strokeDasharray="3 3" strokeWidth={1} />
        {normalized.map(s => (
          <path key={s.label} d={pathFor(s.pct)} fill="none" stroke={s.color} strokeWidth={1.75} />
        ))}
      </svg>
      <div className="row" style={{ gap: 14, marginTop: 6, flexWrap: 'wrap' }}>
        {normalized.map(s => (
          <span key={s.label} className="faint" style={{ fontSize: 10.5, display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color, display: 'inline-block' }} />
            {s.label} (% change from start)
          </span>
        ))}
      </div>
    </div>
  )
}

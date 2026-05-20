import { useLayoutEffect, useRef, useState } from 'react'

interface SparklineProps {
  data: number[]
  color?: string
  height?: number
  area?: boolean
}

export default function Sparkline({ data, color, height = 56, area = true }: SparklineProps) {
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

  if (!data || data.length < 2) return <div ref={ref} style={{ width: '100%', height }} />

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = height - 6 - ((v - min) / range) * (height - 12)
    return [x, y] as [number, number]
  })

  const d = pts.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(' ')
  const aPath = `${d} L${w},${height} L0,${height} Z`
  const auto = data[data.length - 1] >= data[0] ? 'var(--pos)' : 'var(--neg)'
  const c = color || auto
  const gradId = `sg-${data.length}-${Math.round(min)}`

  return (
    <div ref={ref} style={{ width: '100%' }}>
      <svg
        style={{ width: '100%', height, display: 'block' }}
        viewBox={`0 0 ${w} ${height}`}
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={c} stopOpacity="0.28" />
            <stop offset="100%" stopColor={c} stopOpacity="0" />
          </linearGradient>
        </defs>
        {area && <path d={aPath} fill={`url(#${gradId})`} />}
        <path d={d} fill="none" stroke={c} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

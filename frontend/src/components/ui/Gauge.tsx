interface GaugeProps {
  value: number
  max?: number
  label: string
  sub?: string
  tone?: 'warn' | 'bad'
}

export default function Gauge({ value, max = 100, label, sub, tone }: GaugeProps) {
  const pct = Math.min(1, Math.max(0, value / max))
  const r = 64, cx = 80, cy = 76

  const arc = (frac: number) => {
    const a0 = Math.PI
    const a1 = Math.PI + Math.PI * frac
    const x0 = cx + r * Math.cos(a0)
    const y0 = cy + r * Math.sin(a0)
    const x1 = cx + r * Math.cos(a1)
    const y1 = cy + r * Math.sin(a1)
    const large = frac > 0.5 ? 1 : 0
    return `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`
  }

  const color = tone === 'warn' ? 'var(--warn)' : tone === 'bad' ? 'var(--neg)' : 'var(--text)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <svg width="160" height="92" viewBox="0 0 160 92">
        <path d={arc(1)} stroke="var(--accent-soft)" strokeWidth="10" fill="none" strokeLinecap="round" />
        <path d={arc(pct)} stroke={color} strokeWidth="10" fill="none" strokeLinecap="round" />
        <text
          x="80" y="70"
          textAnchor="middle"
          fontFamily="var(--font-mono)"
          fontSize="22"
          fill="var(--text)"
          style={{ fontVariantNumeric: 'tabular-nums' }}
        >
          {Math.round(pct * 100)}
          <tspan fontSize="11" fill="var(--text-dim)" dx="2">%</tspan>
        </text>
      </svg>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.14em', textTransform: 'uppercase' }}>
          {label}
        </div>
        {sub && (
          <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 2 }}>{sub}</div>
        )}
      </div>
    </div>
  )
}

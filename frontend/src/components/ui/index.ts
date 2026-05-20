export { default as Sparkline } from './Sparkline'
export { default as Gauge } from './Gauge'
export { default as SegmentedControl } from './SegmentedControl'
export { default as Badge } from './Badge'

export function fmtINR(n: number | null | undefined, opts: { signed?: boolean } = {}): string {
  if (n == null || isNaN(n)) return '—'
  const sign = opts.signed && n > 0 ? '+' : ''
  const abs = Math.abs(n)
  const v = abs >= 1000
    ? Math.round(abs).toLocaleString('en-IN')
    : abs.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${sign}${n < 0 ? '−' : ''}₹${v}`
}

export function fmtPct(n: number | null | undefined, opts: { signed?: boolean } = {}): string {
  if (n == null || isNaN(n)) return '—'
  const sign = opts.signed && n > 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-IN', { hour12: false })
}

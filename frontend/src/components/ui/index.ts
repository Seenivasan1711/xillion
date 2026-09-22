export { default as Sparkline } from './Sparkline'
export { default as EquityCompareChart } from './EquityCompareChart'
export { default as Gauge } from './Gauge'
export { default as SegmentedControl } from './SegmentedControl'
export { default as Badge } from './Badge'
export { Skeleton, SkeletonCard, SkeletonRows } from './Skeleton'

export function fmtINR(n: number | null | undefined, opts: { signed?: boolean } = {}): string {
  return fmtMoney(n, '₹', opts)
}

// Which currency symbol a set of instruments should be displayed in --
// XAU/USD-denominated strategies (Gold, forex) are $, everything else
// (NIFTY, options, equities) is ₹. Same rule as Alerts.tsx's original
// fmtPrice() fix, generalized here so every page can share one
// implementation instead of re-deriving it (found duplicated 3x across
// Alerts.tsx/Strategies.tsx/Backtest.tsx in one session, 2026-09-22).
export function currencyFor(instruments: string[] | null | undefined): '₹' | '$' {
  return (instruments ?? []).some(i => /XAU|USD/i.test(i)) ? '$' : '₹'
}

export function fmtMoney(
  n: number | null | undefined,
  currency: '₹' | '$' = '₹',
  opts: { signed?: boolean } = {}
): string {
  if (n == null || isNaN(n)) return '—'
  const sign = opts.signed && n > 0 ? '+' : ''
  const abs = Math.abs(n)
  const v = currency === '₹'
    ? (abs >= 1000
        ? Math.round(abs).toLocaleString('en-IN')
        : abs.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
    : abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${sign}${n < 0 ? '−' : ''}${currency}${v}`
}

export function fmtPct(n: number | null | undefined, opts: { signed?: boolean } = {}): string {
  if (n == null || isNaN(n)) return '—'
  const sign = opts.signed && n > 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-IN', { hour12: false })
}

export function Skeleton({ width, height = 14, radius = 6, style }: { width?: number | string; height?: number; radius?: number; style?: React.CSSProperties }) {
  return (
    <div
      className="skeleton"
      style={{ width: width ?? '100%', height, borderRadius: radius, ...style }}
    />
  )
}

/** A stand-in for a .card while its data loads -- a header line, then N
 * body lines of varying width so it doesn't look like a uniform gray box. */
export function SkeletonCard({ lines = 3, headerWidth = '40%' }: { lines?: number; headerWidth?: number | string }) {
  return (
    <div className="card card-pad stack" style={{ gap: 10 }}>
      <Skeleton width={headerWidth} height={11} />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} width={i === lines - 1 ? '55%' : '85%'} height={14} />
      ))}
    </div>
  )
}

/** A stand-in for a data table's rows while it loads. */
export function SkeletonRows({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="stack" style={{ gap: 10, padding: '4px 0' }}>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="row" style={{ gap: 16 }}>
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} width={c === 0 ? '20%' : `${Math.max(10, 30 - c * 5)}%`} height={13} />
          ))}
        </div>
      ))}
    </div>
  )
}

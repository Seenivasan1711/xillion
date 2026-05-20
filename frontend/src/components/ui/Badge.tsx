import type { ReactNode } from 'react'

interface BadgeProps {
  children: ReactNode
  tone?: 'pos' | 'neg' | 'warn'
  dot?: boolean
  className?: string
}

export default function Badge({ children, tone, dot, className }: BadgeProps) {
  const cls = ['badge', tone, dot ? 'dot' : '', className].filter(Boolean).join(' ')
  return <span className={cls}>{children}</span>
}

export default function Logomark({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 18C9 18 8 6 20 6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M4 6C9 6 8 18 20 18" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.45" />
      <circle cx="12.2" cy="12" r="1.9" fill="currentColor" />
    </svg>
  )
}

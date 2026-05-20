interface Option {
  value: string
  label: string
}

interface SegmentedControlProps {
  options: Option[]
  value: string
  onChange: (v: string) => void
  className?: string
}

export default function SegmentedControl({ options, value, onChange, className }: SegmentedControlProps) {
  return (
    <div className={`seg ${className ?? ''}`}>
      {options.map((o) => (
        <button
          key={o.value}
          className={value === o.value ? 'on' : ''}
          onClick={() => onChange(o.value)}
          type="button"
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

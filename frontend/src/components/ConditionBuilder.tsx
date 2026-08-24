import { Plus, Trash2 } from 'lucide-react'
import type { ConditionRow, MetricSpec } from '../lib/api'

const METRICS: { value: string; label: string; needsPeriod: boolean }[] = [
  { value: 'close', label: 'Close', needsPeriod: false },
  { value: 'open', label: 'Open', needsPeriod: false },
  { value: 'high', label: 'High', needsPeriod: false },
  { value: 'low', label: 'Low', needsPeriod: false },
  { value: 'volume', label: 'Volume', needsPeriod: false },
  { value: 'sma', label: 'SMA', needsPeriod: true },
  { value: 'ema', label: 'EMA', needsPeriod: true },
  { value: 'rsi', label: 'RSI', needsPeriod: true },
  { value: 'atr', label: 'ATR', needsPeriod: true },
  { value: 'vwap', label: 'VWAP (rolling)', needsPeriod: true },
  { value: 'bb_upper', label: 'Bollinger upper', needsPeriod: true },
  { value: 'bb_mid', label: 'Bollinger mid', needsPeriod: true },
  { value: 'bb_lower', label: 'Bollinger lower', needsPeriod: true },
  { value: 'macd_line', label: 'MACD line', needsPeriod: false },
  { value: 'macd_signal', label: 'MACD signal', needsPeriod: false },
  { value: 'macd_hist', label: 'MACD histogram', needsPeriod: false },
  { value: 'supertrend', label: 'Supertrend', needsPeriod: true },
]

const OPERATORS: { value: ConditionRow['operator']; label: string }[] = [
  { value: '>', label: '>' },
  { value: '<', label: '<' },
  { value: '>=', label: '>=' },
  { value: '<=', label: '<=' },
  { value: '==', label: '==' },
  { value: 'crosses_above', label: 'crosses above' },
  { value: 'crosses_below', label: 'crosses below' },
]

function metricInfo(name: string) {
  return METRICS.find(m => m.value === name) ?? METRICS[0]
}

function MetricPicker({ value, onChange, label }: { value: MetricSpec; onChange: (v: MetricSpec) => void; label?: string }) {
  const info = metricInfo(value.name)
  return (
    <div className="row" style={{ gap: 6, alignItems: 'center' }}>
      {label && <span className="faint" style={{ fontSize: 10.5, width: 56, flexShrink: 0 }}>{label}</span>}
      <select
        className="input" style={{ fontSize: 11.5, minWidth: 130 }}
        value={value.name}
        onChange={e => onChange({ name: e.target.value, period: 14 })}
      >
        {METRICS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
      </select>
      {info.needsPeriod && (
        <input
          className="input" type="number" style={{ width: 60, fontSize: 11.5 }}
          value={value.period ?? 14}
          onChange={e => onChange({ ...value, period: parseInt(e.target.value) || 1 })}
          title="period"
        />
      )}
    </div>
  )
}

function ConditionRowEditor({ row, onChange, onRemove }: {
  row: ConditionRow
  onChange: (r: ConditionRow) => void
  onRemove: () => void
}) {
  const comparesToMetric = row.other_metric != null

  return (
    <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap', padding: '6px 0' }}>
      <MetricPicker value={row.metric} onChange={metric => onChange({ ...row, metric })} />

      <select
        className="input" style={{ fontSize: 11.5, width: 130 }}
        value={row.operator}
        onChange={e => onChange({ ...row, operator: e.target.value as ConditionRow['operator'] })}
      >
        {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>

      <select
        className="input" style={{ fontSize: 11.5, width: 90 }}
        value={comparesToMetric ? 'metric' : 'value'}
        onChange={e => {
          if (e.target.value === 'metric') {
            onChange({ ...row, other_metric: { name: 'sma', period: 14 }, threshold: undefined })
          } else {
            onChange({ ...row, other_metric: undefined, threshold: row.threshold ?? 0 })
          }
        }}
      >
        <option value="value">vs value</option>
        <option value="metric">vs metric</option>
      </select>

      {comparesToMetric ? (
        <MetricPicker value={row.other_metric!} onChange={other_metric => onChange({ ...row, other_metric })} />
      ) : (
        <input
          className="input" type="number" style={{ width: 90, fontSize: 11.5 }}
          value={row.threshold ?? 0}
          onChange={e => onChange({ ...row, threshold: parseFloat(e.target.value) || 0 })}
        />
      )}

      <button type="button" className="icon-btn" onClick={onRemove} title="Remove condition" style={{ marginLeft: 'auto' }}>
        <Trash2 size={13} />
      </button>
    </div>
  )
}

export function ConditionListEditor({ label, hint, conditions, onChange }: {
  label: string
  hint?: string
  conditions: ConditionRow[]
  onChange: (c: ConditionRow[]) => void
}) {
  const addRow = () => onChange([...conditions, { metric: { name: 'close' }, operator: '>', threshold: 0 }])
  const updateRow = (i: number, row: ConditionRow) => onChange(conditions.map((c, idx) => idx === i ? row : c))
  const removeRow = (i: number) => onChange(conditions.filter((_, idx) => idx !== i))

  return (
    <div className="field">
      <label>{label}{conditions.length > 1 && <span className="faint"> (ALL must be true)</span>}</label>
      {hint && <div className="faint" style={{ fontSize: 10.5, marginBottom: 6 }}>{hint}</div>}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, padding: '4px 10px' }}>
        {conditions.length === 0 && (
          <div className="faint" style={{ fontSize: 11, padding: '8px 0' }}>No conditions yet — this will never fire.</div>
        )}
        {conditions.map((row, i) => (
          <div key={i} style={{ borderTop: i > 0 ? '1px solid var(--border)' : 'none' }}>
            <ConditionRowEditor row={row} onChange={r => updateRow(i, r)} onRemove={() => removeRow(i)} />
          </div>
        ))}
      </div>
      <button type="button" className="btn ghost sm" onClick={addRow} style={{ marginTop: 6 }}>
        <Plus size={12} /> Add condition
      </button>
    </div>
  )
}

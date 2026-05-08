const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  health: () => request<{ status: string; version: string; timestamp: string }>('/health'),

  strategies: {
    classes: () =>
      request<{ strategies: StrategyClass[]; errors: Record<string, string> }>('/strategies/classes'),
    reload: () => request<{ reloaded: boolean; strategy_count: number }>('/strategies/reload', { method: 'POST' }),
    runners: () => request<{ runners: Runner[] }>('/strategies/runners'),
  },

  brokers: {
    classes: () => request<{ brokers: BrokerClass[] }>('/brokers/classes'),
  },

  backtest: {
    run: (body: BacktestRequest) =>
      request<BacktestResponse>('/backtest/run', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  },
}

export interface StrategyClass {
  name: string
  version: string
  description: string
  author: string
  timeframe: string
  params_schema: ParamSpec[]
  code_hash: string
}

export interface ParamSpec {
  name: string
  type: string
  default: unknown
  description: string
  min?: number
  max?: number
  choices?: string[]
}

export interface BrokerClass {
  name: string
  version: string
  capabilities: Record<string, unknown>
}

export interface Runner {
  instance_id: string
  status: string
  last_error: string | null
}

export interface BacktestRequest {
  strategy_name: string
  instruments: string[]
  timeframe?: string
  initial_capital?: number
  slippage_bps?: number
  params?: Record<string, unknown>
  bars?: BarData[]
}

export interface BarData {
  symbol: string
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  timeframe?: string
}

export interface BacktestResponse {
  run_id: string
  strategy_name: string
  status: string
  error: string | null
  metrics: Record<string, number | null>
  equity_curve: number[]
  trade_count: number
  from_ts: string
  to_ts: string
}

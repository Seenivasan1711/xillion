const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    ...options,
  })
  if (res.status === 401) {
    // Let callers handle auth errors — don't redirect here
    const err = await res.json().catch(() => ({ detail: 'Unauthorized' }))
    throw new Error(err.detail || 'Unauthorized')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  health: () =>
    request<{
      status: string
      version: string
      timestamp: string
      brokers: BrokerStatus[]
      brokers_connected: boolean
    }>('/health'),

  auth: {
    setupStatus: () => request<{ needs_setup: boolean }>('/auth/setup-status'),
    setup: (username: string, password: string) =>
      request<{ created: boolean; username: string }>('/auth/setup', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }),
    login: (username: string, password: string, totp_code?: string) =>
      request<{ authenticated?: boolean; requires_totp?: boolean; username?: string }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password, totp_code }),
      }),
    logout: () => request<{ logged_out: boolean }>('/auth/logout', { method: 'POST' }),
    me: () => request<User>('/auth/me'),
    totpSetup: () => request<{ secret: string; uri: string }>('/auth/totp/setup', { method: 'POST' }),
    totpVerify: (secret: string, code: string) =>
      request<{ totp_enabled: boolean }>('/auth/totp/verify', {
        method: 'POST',
        body: JSON.stringify({ secret, code }),
      }),
    totpDisable: () => request<{ totp_disabled: boolean }>('/auth/totp/disable', { method: 'POST' }),
  },

  strategies: {
    classes: () =>
      request<{ strategies: StrategyClass[]; errors: Record<string, string> }>('/strategies/classes'),
    reload: () => request<{ reloaded: boolean; strategy_count: number }>('/strategies/reload', { method: 'POST' }),
    runners: () => request<{ runners: Runner[] }>('/strategies/runners'),
  },

  risk: {
    status: () =>
      request<{
        kill_switch_active: boolean
        kill_switch_at: string | null
        account_daily_loss: string
        ops_limit: number
      }>('/risk/status'),
    activateKillSwitch: (totp_code?: string, exit_positions = false) =>
      request<{ activated: boolean; strategies_stopped: number; orders_cancelled: number }>(
        '/risk/kill-switch/activate',
        { method: 'POST', body: JSON.stringify({ totp_code, exit_positions }) }
      ),
    resetKillSwitch: (totp_code?: string) =>
      request<{ reset: boolean }>('/risk/kill-switch/reset', {
        method: 'POST',
        body: JSON.stringify({ totp_code }),
      }),
  },

  instances: {
    list: () => request<{ instances: StrategyInstance[] }>('/instances'),
    create: (body: CreateInstanceRequest) =>
      request<{ id: string; name: string; status: string }>('/instances', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    get: (id: string) => request<StrategyInstance>(`/instances/${id}`),
    update: (id: string, body: Partial<CreateInstanceRequest>) =>
      request<{ updated: boolean }>(`/instances/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    start: (id: string) => request<{ started: boolean; status: string }>(`/instances/${id}/start`, { method: 'POST' }),
    stop: (id: string) => request<{ stopped: boolean }>(`/instances/${id}/stop`, { method: 'POST' }),
    delete: (id: string) => request<{ deleted: boolean }>(`/instances/${id}`, { method: 'DELETE' }),
  },

  brokers: {
    classes: () => request<{ brokers: BrokerClass[] }>('/brokers/classes'),
    connections: () => request<{ connections: BrokerStatus[] }>('/brokers/connections'),
    reconnect: (name: string) =>
      request<{ name: string; status: string }>(`/brokers/connections/${encodeURIComponent(name)}/reconnect`, {
        method: 'POST',
      }),
  },

  backtest: {
    run: (body: BacktestRequest) =>
      request<BacktestResponse>('/backtest/run', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  },
}

// ── Types ──────────────────────────────────────────────────────────────────────

export interface User {
  id: number
  username: string
  has_totp: boolean
  last_login_at: string | null
}

export interface BrokerStatus {
  name: string
  broker_name: string
  status: 'connected' | 'error' | 'disconnected'
  last_error: string | null
  connected_at: string | null
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

export interface StrategyInstance {
  id: string
  name: string
  strategy_class_name: string
  strategy_class_version: string
  mode: 'paper' | 'live' | 'backtest'
  status: 'idle' | 'running' | 'paused' | 'error' | 'killed'
  last_error: string | null
  instruments: string[]
  timeframe: string
  params: Record<string, unknown>
  capital_allocation: number
  risk_limits: Record<string, unknown>
  last_started_at: string | null
  last_stopped_at: string | null
  created_at: string
  updated_at: string
}

export interface CreateInstanceRequest {
  name: string
  strategy_class_name: string
  mode: 'paper' | 'live'
  instruments: string[]
  timeframe: string
  params: Record<string, unknown>
  capital_allocation: number
  risk_limits: Record<string, unknown>
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

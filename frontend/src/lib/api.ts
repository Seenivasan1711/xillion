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
    start: (id: string) =>
      request<{ started: boolean; status: string; tick_source?: string; warning?: string | null }>(
        `/instances/${id}/start`,
        { method: 'POST' }
      ),
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

  settings: {
    getZerodha: () =>
      request<{ configured: boolean; api_key_preview?: string; user_id?: string; updated_at?: string }>(
        '/settings/zerodha'
      ),
    saveZerodha: (body: ZerodhaCredentials) =>
      request<{ saved: boolean; connection_status: string; last_error: string | null }>(
        '/settings/zerodha',
        { method: 'PUT', body: JSON.stringify(body) }
      ),
    deleteZerodha: () =>
      request<{ deleted: boolean }>('/settings/zerodha', { method: 'DELETE' }),
    getNotifications: () =>
      request<NotificationSettings>('/settings/notifications'),
    saveNotifications: (body: NotificationSettings) =>
      request<{ saved: boolean }>('/settings/notifications', { method: 'PUT', body: JSON.stringify(body) }),
    getRiskLimits: () =>
      request<RiskLimits>('/settings/risk-limits'),
    saveRiskLimits: (body: RiskLimits) =>
      request<{ saved: boolean }>('/settings/risk-limits', { method: 'PUT', body: JSON.stringify(body) }),
    resetData: () =>
      request<{ reset: boolean }>('/settings/reset-data', { method: 'POST' }),
    wipeAll: () =>
      request<{ wiped: boolean }>('/settings/wipe', { method: 'POST' }),
  },

  portfolio: {
    summary: () => request<PortfolioSummary>('/portfolio/summary'),
  },

  trades: {
    list: (page = 1, limit = 500) =>
      request<{ trades: MatchedTrade[]; total: number; page: number; limit: number }>(
        `/trades?page=${page}&limit=${limit}`
      ),
  },

  backtest: {
    run: (body: BacktestRequest) =>
      request<BacktestResponse>('/backtest/run', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    runCsv: async (file: File, cfg: BacktestCsvConfig): Promise<BacktestResponse> => {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('strategy_name', cfg.strategy_name)
      fd.append('instruments', (cfg.instruments ?? []).join(','))
      fd.append('timeframe', cfg.timeframe ?? '5m')
      fd.append('initial_capital', String(cfg.initial_capital ?? 100000))
      fd.append('slippage_bps', String(cfg.slippage_bps ?? 5))
      fd.append('params', JSON.stringify(cfg.params ?? {}))
      const res = await fetch(`${BASE}/backtest/run-csv`, {
        method: 'POST',
        body: fd,
        credentials: 'include',
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      return res.json()
    },
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
  // Extended fields (populated when backend supports them)
  pnl?: number
  trade_count?: number
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
  bars_loaded?: number
  parse_errors?: string[]
  elapsed_seconds?: number
  trades?: BacktestTrade[]
}

export interface BacktestTrade {
  ts: string
  side: 'BUY' | 'SELL'
  entry_price: number
  exit_price: number
  bars_held: number
  pnl: number
}

export interface NotificationSettings {
  telegram_bot_token: string
  telegram_chat_id: string
  on_strategy_start_stop: boolean
  on_order_filled: boolean
  on_order_rejected: boolean
  on_drawdown_breach: boolean
  on_kill_switch: boolean
}

export interface RiskLimits {
  daily_loss_pct: number
  per_trade_risk_pct: number
  max_open_positions: number
  position_size_cap: number
  ops_limit: number
  burst_window: number
}

export interface BacktestCsvConfig {
  strategy_name: string
  instruments?: string[]
  timeframe?: string
  initial_capital?: number
  slippage_bps?: number
  params?: Record<string, unknown>
}

export interface PortfolioSummary {
  pnl_today: number
  pnl_today_pct: number
  equity_total: number
  intraday_curve: Array<{ ts: string; value: number }>
  historical_equity: Array<{ ts: string; value: number }>
  drawdown_pct: number
  capital_used_pct: number
  loss_budget_pct: number
  open_trades: number
  closed_trades_today: number
  win_rate: number
  avg_trade_pnl: number
}

export interface MatchedTrade {
  id: string
  symbol: string
  instance_id: string
  instance_name: string
  side: 'LONG' | 'SHORT'
  quantity: number
  entry_price: number
  exit_price: number
  entry_ts: string
  exit_ts: string
  pnl: number
  mode: 'paper' | 'live'
}

export interface ZerodhaCredentials {
  api_key: string
  api_secret: string
  user_id: string
  password: string
  totp_secret: string
}

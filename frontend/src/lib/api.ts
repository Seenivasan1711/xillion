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
        trading_enabled: boolean
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

  reconciliation: {
    reports: (limit = 20) =>
      request<{ reports: ReconciliationReport[] }>(`/reconciliation/reports?limit=${limit}`),
    acknowledge: (id: number) =>
      request<{ acknowledged: boolean; trading_resumed: boolean }>(
        `/reconciliation/reports/${id}/acknowledge`,
        { method: 'POST' }
      ),
  },

  instances: {
    list: () => request<{ instances: StrategyInstance[] }>('/instances'),
    create: (body: CreateInstanceRequest) =>
      request<{ id: string; name: string; status: string }>('/instances', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    get: (id: string) => request<StrategyInstance>(`/instances/${id}`),
    update: (id: string, body: Partial<CreateInstanceRequest> & { auto_start?: boolean }) =>
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

  logs: {
    list: (opts?: { limit?: number; level?: string }) => {
      const params = new URLSearchParams()
      if (opts?.limit) params.set('limit', String(opts.limit))
      if (opts?.level) params.set('level', opts.level)
      const qs = params.toString()
      return request<{ logs: LogEntry[] }>(`/logs${qs ? `?${qs}` : ''}`)
    },
  },

  brokers: {
    classes: () => request<{ brokers: BrokerClass[] }>('/brokers/classes'),
    connections: () => request<{ connections: BrokerStatus[] }>('/brokers/connections'),
    reconnect: (name: string) =>
      request<{ name: string; status: string }>(`/brokers/connections/${encodeURIComponent(name)}/reconnect`, {
        method: 'POST',
      }),
    status: (name: string) =>
      request<{ name: string; broker_name: string; status: string; last_error: string | null; connected_at: string | null }>(
        `/brokers/connections/${encodeURIComponent(name)}/status`
      ),
    setFailoverTarget: (name: string, targetName: string | null) =>
      request<{ name: string; failover_connection_name: string | null }>(
        `/brokers/connections/${encodeURIComponent(name)}/failover-target`,
        { method: 'PATCH', body: JSON.stringify({ target_name: targetName }) }
      ),
    triggerFailover: (name: string) =>
      request<{ status: string; positions_found: number; exited: string[]; failed_to_exit: string[] }>(
        `/brokers/connections/${encodeURIComponent(name)}/failover`,
        { method: 'POST' }
      ),
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
    getDhan: () =>
      request<{ configured: boolean; client_id?: string; updated_at?: string }>(
        '/settings/dhan'
      ),
    saveDhan: (body: DhanCredentials) =>
      request<{ saved: boolean; connection_status: string; last_error: string | null }>(
        '/settings/dhan',
        { method: 'PUT', body: JSON.stringify(body) }
      ),
    deleteDhan: () =>
      request<{ deleted: boolean }>('/settings/dhan', { method: 'DELETE' }),
    getNotifications: () =>
      request<NotificationSettings>('/settings/notifications'),
    saveNotifications: (body: NotificationSettings) =>
      request<{ saved: boolean }>('/settings/notifications', { method: 'PUT', body: JSON.stringify(body) }),
    testNotifications: () =>
      request<{ sent: boolean }>('/settings/notifications/test', { method: 'POST' }),
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
    runProvider: (body: BacktestProviderRequest) =>
      request<BacktestResponse>('/backtest/run-provider', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    runs: (limit = 50) => request<{ runs: BacktestRunSummary[] }>(`/backtest/runs?limit=${limit}`),
    runDetail: (runId: string) => request<BacktestRunDetail>(`/backtest/runs/${encodeURIComponent(runId)}`),
    optimize: (body: OptimizeRequest) =>
      request<OptimizeResponse>('/backtest/optimize', { method: 'POST', body: JSON.stringify(body) }),
    walkForward: (body: WalkForwardRequest) =>
      request<WalkForwardResponse>('/backtest/walk-forward', { method: 'POST', body: JSON.stringify(body) }),
  },

  dataProviders: {
    classes: () =>
      request<{ providers: DataProviderClass[]; errors: Record<string, string> }>('/data-providers/classes'),
    saveCredentials: (name: string, payload: Record<string, string>) =>
      request<{ saved: boolean }>(`/data-providers/${encodeURIComponent(name)}/credentials`, {
        method: 'PUT',
        body: JSON.stringify({ payload }),
      }),
    deleteCredentials: (name: string) =>
      request<{ deleted: boolean }>(`/data-providers/${encodeURIComponent(name)}/credentials`, {
        method: 'DELETE',
      }),
  },

  signals: {
    list: (opts?: { instance_id?: string; limit?: number }) => {
      const params = new URLSearchParams()
      if (opts?.instance_id) params.set('instance_id', opts.instance_id)
      if (opts?.limit) params.set('limit', String(opts.limit))
      const qs = params.toString()
      return request<{ signals: SignalLogEntry[] }>(`/signals${qs ? `?${qs}` : ''}`)
    },
  },

  journal: {
    list: (opts?: { instance_id?: string; strategy_name?: string; limit?: number }) => {
      const params = new URLSearchParams()
      if (opts?.instance_id) params.set('instance_id', opts.instance_id)
      if (opts?.strategy_name) params.set('strategy_name', opts.strategy_name)
      if (opts?.limit) params.set('limit', String(opts.limit))
      const qs = params.toString()
      return request<{ entries: JournalEntryRow[] }>(`/journal${qs ? `?${qs}` : ''}`)
    },
    setNote: (body: { source: string; source_id: string; failure_mode?: string; change_made?: string }) =>
      request<{ saved: boolean }>('/journal/note', { method: 'PUT', body: JSON.stringify(body) }),
    versions: (strategyName: string) =>
      request<{ strategy_name: string; versions: { version: string; code_hash: string; recorded_at: string }[] }>(
        `/journal/versions/${encodeURIComponent(strategyName)}`
      ),
    export: (strategyName: string) =>
      request<{ path: string; entry_count: number }>('/journal/export', {
        method: 'POST', body: JSON.stringify({ strategy_name: strategyName }),
      }),
  },

  data: {
    coverage: () => request<{ coverage: BarCoverage[] }>('/data/coverage'),
    backfill: (body: BackfillRequest) =>
      request<{ job_id: string; status: string }>('/data/backfill', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    backfillJobs: () => request<{ jobs: BackfillJob[] }>('/data/backfill'),
    backfillStatus: (jobId: string) => request<BackfillJob>(`/data/backfill/${encodeURIComponent(jobId)}`),
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
  failover_connection_name?: string | null
  health?: {
    consecutive_failures: number
    last_checked_at: string | null
    last_healthy_at: string | null
    failover_triggered: boolean
  } | null
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

export interface LogEntry {
  id: number
  ts: string
  level: string
  source: string
  message: string
  fields: Record<string, unknown>
}

export interface StrategyInstance {
  id: string
  name: string
  strategy_class_name: string
  strategy_class_version: string
  mode: 'paper' | 'live' | 'backtest' | 'alert'
  status: 'idle' | 'running' | 'paused' | 'error' | 'killed'
  last_error: string | null
  instruments: string[]
  timeframe: string
  params: Record<string, unknown>
  capital_allocation: number
  risk_limits: Record<string, unknown>
  last_started_at: string | null
  last_stopped_at: string | null
  auto_start: boolean
  created_at: string
  updated_at: string
  // Extended fields (populated when backend supports them)
  pnl?: number
  trade_count?: number
}

export interface CreateInstanceRequest {
  name: string
  strategy_class_name: string
  mode: 'paper' | 'live' | 'alert'
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

export interface ReconciliationReport {
  id: number
  trading_date: string
  broker_name: string
  checked_at: string
  status: 'CLEAN' | 'DISCREPANCY' | 'FAILED'
  position_mismatches: { symbol: string; issue: string; broker_qty: number | null; internal_qty: number | null }[]
  eod_open_positions: string[]
  order_mismatches: {
    broker_order_id: string
    symbol: string
    issue: string
    broker_status: string | null
    internal_status: string | null
    broker_filled_qty: number | null
    internal_filled_qty: number | null
    broker_avg_price: string | null
    internal_avg_price: string | null
  }[]
  notes: string[]
  acknowledged: boolean
  acknowledged_at: string | null
  acknowledged_by: string | null
}

export interface BacktestCsvConfig {
  strategy_name: string
  instruments?: string[]
  timeframe?: string
  initial_capital?: number
  slippage_bps?: number
  params?: Record<string, unknown>
}

export interface BacktestProviderRequest {
  strategy_name: string
  provider_name: string
  symbol: string
  exchange?: string
  instrument_type?: string
  timeframe?: string
  from_date: string
  to_date: string
  initial_capital?: number
  slippage_bps?: number
  params?: Record<string, unknown>
}

// A condition row from the Strategy Builder -- see xillion/engine/condition.py.
export interface MetricSpec {
  name: string
  period?: number
  fast?: number
  slow?: number
  signal?: number
  num_std?: number
  multiplier?: number
}

export interface ConditionRow {
  metric: MetricSpec
  operator: '>' | '<' | '>=' | '<=' | '==' | 'crosses_above' | 'crosses_below'
  threshold?: number
  other_metric?: MetricSpec
}

interface ProviderBarSourceFields {
  strategy_name: string
  provider_name: string
  symbol: string
  exchange?: string
  instrument_type?: string
  timeframe?: string
  from_date: string
  to_date: string
  initial_capital?: number
  slippage_bps?: number
}

export interface OptimizeRequest extends ProviderBarSourceFields {
  base_params?: Record<string, unknown>
  param_grid?: Record<string, unknown[]>
  rank_by?: string
}

export interface GridResultEntry {
  params: Record<string, unknown>
  metrics: Record<string, number | null>
  trade_count: number
}

export interface OptimizeResponse {
  rank_by: string
  bars_loaded: number
  results: GridResultEntry[]
}

export interface WalkForwardRequest extends OptimizeRequest {
  n_folds?: number
  train_ratio?: number
}

export interface WalkForwardFoldEntry {
  train_from: string
  train_to: string
  test_from: string
  test_to: string
  best_params: Record<string, unknown>
  in_sample_metrics: Record<string, number | null>
  out_of_sample_metrics: Record<string, number | null>
}

export interface WalkForwardResponse {
  rank_by: string
  bars_loaded: number
  avg_in_sample: number | null
  avg_out_of_sample: number | null
  is_likely_overfit: boolean
  folds: WalkForwardFoldEntry[]
}

export interface SignalLogEntry {
  id: number
  strategy_instance_id: string
  strategy_instance_name: string | null
  ts: string
  underlying_symbol: string
  resolved_tradingsymbol: string | null
  signal_type: 'ENTER' | 'EXIT' | 'SIGNAL'
  tag: string | null
  parent_signal_id: number | null
  target_price: number | null
  stop_loss_price: number | null
  side: 'BUY' | 'SELL' | null
  price: number | null
  message: string
  mode: string
  notified: boolean
  notified_at: string | null
}

export interface JournalEntryRow {
  source: 'signal_log' | 'backtest_trade'
  source_id: string
  strategy_instance_id: string | null
  symbol: string
  side: string | null
  entry_price: number | null
  exit_price: number | null
  entry_ts: string | null
  exit_ts: string | null
  pnl: number | null
  target_price: number | null
  stop_loss_price: number | null
  ai_confidence: number | null
  outcome: 'stopped_out' | 'target_hit' | 'win' | 'loss' | 'unclassified' | 'still_open'
  tag: string | null
  manual_failure_mode?: string | null
  change_made?: string | null
}

export interface BarCoverage {
  symbol: string
  exchange: string
  timeframe: string
  provider_name: string
  from_date: string
  to_date: string
  updated_at: string
}

export interface BackfillRequest {
  provider_name: string
  symbol: string
  exchange?: string
  instrument_type?: string
  timeframe?: string
  from_date: string
  to_date: string
}

export interface BackfillJob {
  id: string
  provider_name: string
  symbol: string
  exchange: string
  timeframe: string
  from_date: string
  to_date: string
  status: 'queued' | 'running' | 'done' | 'failed'
  bars_fetched: number | null
  error: string | null
  started_at: string
  finished_at: string | null
}

export interface BacktestRunSummary {
  id: string
  strategy_class_id: number
  status: string
  timeframe: string
  from_ts: string
  to_ts: string
  initial_capital: number
  started_at: string
  finished_at: string | null
  metrics: Record<string, number | null>
  error: string | null
}

export interface BacktestRunDetail extends BacktestRunSummary {
  strategy_class_version: string
  params: Record<string, unknown>
  instruments: string[]
  slippage_bps: number
  equity_curve: number[]
  trades: {
    symbol: string
    side: string
    quantity: number
    entry_ts: string
    entry_price: number
    exit_ts: string | null
    exit_price: number | null
    pnl: number | null
    tag: string | null
  }[]
}

export interface DataProviderCapabilities {
  supports_equity: boolean
  supports_futures: boolean
  supports_options: boolean
  supports_forex: boolean
  requires_credentials: boolean
  requires_broker: boolean
  max_lookback_days: number | null
}

export interface DataProviderCredentialField {
  key: 'api_key' | 'api_secret'
  label: string
  type: string
}

export interface DataProviderClass {
  name: string
  version: string
  description: string
  credential_fields: DataProviderCredentialField[]
  capabilities: DataProviderCapabilities
  configured: boolean
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

export interface DhanCredentials {
  client_id: string
  access_token: string
  pin: string
  totp_secret: string
}

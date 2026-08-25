---
doc_id: 12-CONFIG
title: Configuration Schema
audience: backend, ops
version: 1.0
---

# 12 — CONFIGURATION SCHEMA

**Principle: anything that can change without a code change must be config.** Indian F&O rules changed four times in two years (`01` §1.5) — lot sizes, expiry days and cost rates are the classic examples of values that must never be constants in code.

Validated by Pydantic on load. `K05` re-validates on change; `R06` audits config against live exchange data weekly.

---

## 12.1 Root config

```yaml
# config/base.yaml
environment: production            # production | paper | backtest
mode: paper                        # paper | live      ← the safety switch

compliance:                        # 01 §1.4 — NOT tunable
  max_orders_per_second: 7
  max_orders_per_second_burst: 9
  static_ip_required: true
  oauth_only: true
  session_max_lifetime_hours: 24
  audit_retention_years: 5

capital:
  total: 300000
  currency: INR
  reserve_pct: 20                  # never deploy the last 20%

risk:
  risk_per_trade_pct: 1.0
  daily_risk_budget_pct: 3.0
  max_concurrent_positions: 3
  max_positions_per_strategy: 1
  max_trades_per_day: 5
  max_lots_per_trade: 5
  max_consec_losses: 3
  max_portfolio_heat_pct: 6.0
  max_portfolio_delta: 200
  max_notional_per_order: 2000000
  max_orders_per_day: 50
  global_size_multiplier: 1.0      # manual throttle: set 0.5 to halve everything

circuit_breakers:
  daily_loss_soft_pct: 60          # of daily budget → size 50%
  daily_loss_hard_pct: 100         # → block new entries
  daily_loss_critical_pct: 150     # → FLATTEN + kill
  account_drawdown_pct: 10         # → anti-martingale size reduction
  data_staleness_block_sec: 5
  data_staleness_flatten_sec: 30
  broker_errors_per_min: 5
```

---

## 12.2 Instrument config — **audited weekly by R06**

```yaml
instruments:
  NIFTY:
    exchange: NSE
    segment: NFO
    lot_size: 65                   # ⚠️ Jan 2026. R06 verifies against API daily.
    tick_size: 0.05
    expiry_day: TUESDAY            # ⚠️ changed from Thursday, Sep 2025
    expiry_frequency: WEEKLY
    freeze_qty: 1800
    strike_step: 50
    min_oi: 100000
    min_volume: 1000
    max_spread_pct: 0.1

  SENSEX:
    exchange: BSE
    segment: BFO
    lot_size: 20                   # ⭐ far friendlier to small accounts than Nifty's 65
    tick_size: 0.05
    expiry_day: THURSDAY
    expiry_frequency: WEEKLY
    strike_step: 100

  BANKNIFTY:
    lot_size: 30
    expiry_frequency: MONTHLY      # ⚠️ weeklies discontinued Nov 2024
    expiry_day: TUESDAY

  GOLDM:
    exchange: MCX
    lot_size: 100                  # grams
    tick_size: 1
    expiry_frequency: MONTHLY

costs:                             # ⚠️ STT raised to 0.15% Apr 2026. R06 audits.
  stt_options_sell_pct: 0.15       # sell side of premium only
  stt_options_exercise_pct: 0.15
  brokerage_per_order: 20
  exchange_txn_pct: 0.05
  gst_pct: 18                      # on brokerage + exchange charges
  stamp_duty_pct: 0.003            # buy side
  sebi_fee_pct: 0.0001
```

---

## 12.3 Strategy config

```yaml
strategies:
  credit_spread_weekly:
    enabled: true
    lane: A
    risk_class: DEFINED
    structure_type: CREDIT_SPREAD
    instruments: [NIFTY, SENSEX]

    arming:
      allowed_regimes: [NORMAL, HIGH]        # NOT low-VIX — credit too thin
      allowed_stages: [S2, S3, S4]
      min_iv_rank: 30
      min_vix_percentile: 40                 # ⭐ the highest-value filter found
      block_on_high_impact_event: true
      block_if_vrp_inverted: false           # reduce size instead
      vrp_inverted_size_mult: 0.5

    entry:
      time_windows: [{start: "09:45", end: "10:30"}]
      short_delta_target: 0.20
      width_points: 200
      min_credit_pct_of_width: 15
      max_spread_pct: 0.1
      require_trend_alignment: true

    management:
      profit_target_pct_of_credit: 50
      stop_loss_pct_of_credit: 200
      # ⚠️ break-even WR for these = 200/(200+50) = 80%. See KB 07.
      # M05 computes wr_margin against this automatically.
      time_stop_dte: 1
      trail_algorithm: credit_trail
      breakeven_trigger_r: 1.0
      scale_out: []

    limits:
      max_lots: 3
      min_capital_required: 50000

  gold_london_breakout:
    enabled: true
    lane: B1
    risk_class: DEFINED
    structure_type: DIRECTIONAL
    instruments: [XAUUSD]

    arming:
      allowed_sessions: [london, overlap]
      blocked_sessions: [asian, overnight]
      max_spread_pips: 3.0
      block_on_high_impact_event: true

    entry:
      setup: asian_range_breakout
      asian_range_window: {start: "05:30", end: "13:30"}
      min_range_pips: 20
      volume_confirm_mult: 1.5

    management:
      trail_algorithm: chandelier
      atr_period: 14
      atr_multiplier: 2.0
      breakeven_trigger_r: 1.0
      scale_out:
        - {at_r: 1.0, exit_pct: 50}
        - {at_r: 2.0, exit_pct: 25}
      max_hold_minutes: 240
      rollover_exit: true
```

---

## 12.4 Lane and broker config

```yaml
brokers:
  dhan:
    enabled: true
    primary: true
    adapter: openalgo               # or 'native'
    rate_limits: {order: 10, data: 5, quote: 1, non_trading: 20}
    static_ip: "x.x.x.x"
    credentials_ref: vault://dhan   # never inline

  zerodha:
    enabled: true
    primary: false                  # failover
    rate_limits: {order: 10}
    static_ip: "x.x.x.x"

  mt5:
    enabled: true
    lane: B1
    bridge_url: "http://mt5-box:8100"
    terminal_path: "C:/Program Files/MetaTrader 5/terminal64.exe"
    magic_number: 20260824
    prop_firm:
      name: funding_pips
      internal_daily_dd_pct: 4.0    # firm ~5.0 — we halt first (01 §1.3)
      internal_max_dd_pct: 8.0      # firm ~10.0
      dd_model: trailing_peak_equity
      flatten_on_breach: true
      # ⚠️ P07-B must READ live account terms at startup and refuse to arm
      #    if these cannot be confirmed.

alerts:
  telegram: {enabled: true, bot_token_ref: vault://tg, chat_id_ref: vault://tg_chat}
  escalation:
    p0: [telegram, email, phone]
    p1: [telegram, email]
    p2: [telegram]
  ack_timeout_minutes: 5            # unacked P0 → escalate

kill_switch:
  file_sentinel: /var/run/trading/KILL
  flatten_on_kill:
    A: false                        # leave positions but verify broker stops exist
    B1: true                        # prop firm — always flatten
    B2: true
  require_manual_rearm: true        # never auto-resume
```

---

## 12.5 Config rules

1. **No secrets in config files.** Use `vault://` refs resolved at runtime.
2. **Layered:** `base.yaml` → `{environment}.yaml` → env vars. Later wins.
3. **Validated on load.** Invalid config = refuse to start, do not fall back to defaults.
4. **Versioned in git**, secrets excluded. Every change is reviewable.
5. **Hot-reload allowed only for:** `global_size_multiplier`, strategy `enabled` flags, alert routing. Everything else requires a restart.
6. **`mode: live` requires an explicit, separate confirmation flag at startup** — it must never be reachable by editing one line.

```python
class Config(BaseSettings):
    mode: Literal["paper", "live"] = "paper"
    live_confirmed: bool = False

    @model_validator(mode="after")
    def guard_live(self):
        if self.mode == "live" and not self.live_confirmed:
            raise ValueError(
                "mode=live requires live_confirmed=true AND --i-understand-live flag"
            )
        return self
```

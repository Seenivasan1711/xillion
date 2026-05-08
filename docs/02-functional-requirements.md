# 02 — Functional Requirements

Every requirement has a priority:

- **P0** = Must-have for v1 (MVP). Without it, the system is not safe or not usable.
- **P1** = Should-have for v1. Significantly degraded UX without it.
- **P2** = Nice-to-have for v1. Skip if time-pressed.
- **P3** = Future / commercial.

## 1. Strategy management

| ID | Requirement | Priority |
|---|---|---|
| F-S-01 | Auto-discover strategies from a configured folder (`strategies/`) on startup and on manual reload | P0 |
| F-S-02 | Each strategy is a Python class implementing the `Strategy` interface (see doc 04) | P0 |
| F-S-03 | Strategies expose a parameter schema (name, type, default, range) the UI can render | P0 |
| F-S-04 | Strategies can be enabled, disabled, paused, killed individually | P0 |
| F-S-05 | A strategy can be assigned to backtest, paper, or live mode without code changes | P0 |
| F-S-06 | A strategy instance is `(strategy_class, parameters, instrument(s), broker, mode, capital_allocation)` — multiple instances of the same class allowed | P0 |
| F-S-07 | Strategy errors (exceptions) auto-pause that strategy and alert; do not crash the platform | P0 |
| F-S-08 | Strategy code can be hot-reloaded via UI button (no full restart) | P1 |
| F-S-09 | Strategy version history — when code changes, system records hash & timestamp | P1 |
| F-S-10 | Strategy parameter optimisation (grid search) | P2 |
| F-S-11 | Walk-forward optimisation | P2 |

## 2. Broker plugins

| ID | Requirement | Priority |
|---|---|---|
| F-B-01 | Auto-discover broker plugins from `brokers/` folder | P0 |
| F-B-02 | Each broker is a Python class implementing the `Broker` interface (see doc 04) | P0 |
| F-B-03 | Built-in **Paper** broker that simulates fills against live or historical ticks | P0 |
| F-B-04 | Built-in **Backtest** broker that simulates fills with configurable slippage & fees | P0 |
| F-B-05 | **Zerodha (Kite Connect)** broker plugin: auth, market data (REST + WebSocket), historical data, orders (regular, AMO, BO, CO), positions, holdings, margins | P0 |
| F-B-06 | Token refresh handled automatically (Kite tokens expire ~6 AM IST daily) | P0 |
| F-B-07 | Static IP whitelisting hooks (config-level — required by SEBI 2025) | P0 |
| F-B-08 | Order tagging — every order carries a strategy ID and (in 2026) exchange-issued algo ID | P0 |
| F-B-09 | Broker connection state surfaced in UI (Connected / Disconnected / Auth Failed / Rate-limited) | P0 |
| F-B-10 | Second broker plugin (Upstox or Fyers) — proves the abstraction holds | P1 |

## 3. Market data

| ID | Requirement | Priority |
|---|---|---|
| F-D-01 | Live tick stream subscription per instrument | P0 |
| F-D-02 | Bar aggregation (1m, 5m, 15m, 30m, 1h, 1d) computed from ticks | P0 |
| F-D-03 | Historical data fetcher: from broker API + CSV import | P0 |
| F-D-04 | Local cache of historical bars (don't re-fetch every backtest) | P0 |
| F-D-05 | Data quality checks: gap detection, duplicate detection, holiday awareness | P1 |
| F-D-06 | Multiple instruments per strategy | P1 |
| F-D-07 | Order book / depth data subscription (optional, for strategies that use it) | P2 |

## 4. Order & execution

| ID | Requirement | Priority |
|---|---|---|
| F-O-01 | Place market and limit orders | P0 |
| F-O-02 | Stop-loss and target orders (broker-native or simulated) | P0 |
| F-O-03 | Order modification & cancellation | P0 |
| F-O-04 | Order state machine: `PENDING → SUBMITTED → ACCEPTED → FILLED / PARTIAL / CANCELLED / REJECTED` | P0 |
| F-O-05 | Position tracking per strategy and aggregate per account | P0 |
| F-O-06 | Bracket orders (entry + SL + target as one unit) | P1 |
| F-O-07 | Trailing stop-loss | P1 |
| F-O-08 | OCO (one-cancels-other) order pairs | P2 |
| F-O-09 | Iceberg / slice orders for large quantities | P2 |

## 5. Risk management

| ID | Requirement | Priority |
|---|---|---|
| F-R-01 | **Global kill switch** — single button stops all strategies, cancels all open orders, optionally exits positions | P0 |
| F-R-02 | Per-strategy daily P&L limit — auto-pause strategy when breached | P0 |
| F-R-03 | Account-level daily P&L limit — kill switch fires when breached | P0 |
| F-R-04 | Per-strategy max open positions cap | P0 |
| F-R-05 | Per-strategy max capital allocation (cannot exceed) | P0 |
| F-R-06 | Per-strategy max position size (cannot exceed) | P0 |
| F-R-07 | OPS (orders-per-second) rate limiter — stay under SEBI's 10/sec retail threshold | P0 |
| F-R-08 | Pre-trade margin check (don't send orders that will reject) | P0 |
| F-R-09 | Post-trade reconciliation — confirm broker state matches our state | P0 |
| F-R-10 | Circuit-breaker: if N consecutive errors from broker, pause all live trading | P0 |
| F-R-11 | "Can this strategy place an order right now?" gate function callable from anywhere | P0 |
| F-R-12 | Configurable cooldown after stop-loss hit | P1 |
| F-R-13 | Volatility-based position sizing (ATR or VIX) | P2 |

## 6. Backtesting

| ID | Requirement | Priority |
|---|---|---|
| F-T-01 | Run a strategy on a date range with parameters | P0 |
| F-T-02 | Standard metrics: total return, CAGR, Sharpe, Sortino, max drawdown, drawdown duration, win rate, profit factor, expectancy, average win/loss, # trades | P0 |
| F-T-03 | Equity curve chart | P0 |
| F-T-04 | Trade-by-trade list with entry/exit, P&L, slippage | P0 |
| F-T-05 | Configurable commission, slippage, latency simulation | P0 |
| F-T-06 | Compare two backtest runs side by side | P1 |
| F-T-07 | Save backtest runs to history (search later) | P1 |
| F-T-08 | Monte Carlo simulation on trade sequences | P2 |
| F-T-09 | Out-of-sample / walk-forward split helpers | P1 |
| F-T-10 | Backtest reproducibility — same code + same data + same seed = same result | P0 |

## 7. UI / dashboard

| ID | Requirement | Priority |
|---|---|---|
| F-U-01 | Dashboard home: live P&L, active strategies, system status, prominent kill switch | P0 |
| F-U-02 | Strategies page: list, status, config, recent activity per strategy | P0 |
| F-U-03 | Backtest page: pick strategy, set params, run, see results | P0 |
| F-U-04 | Trades page: filterable list of orders & fills with drill-down | P0 |
| F-U-05 | Logs page: structured log search by strategy/time/level | P0 |
| F-U-06 | Settings page: brokers, risk limits, alerts, account | P0 |
| F-U-07 | Mobile-responsive (good on phone, not just tablet) | P0 |
| F-U-08 | Real-time updates via WebSocket (no manual refresh needed) | P0 |
| F-U-09 | Dark mode default | P1 |
| F-U-10 | Strategy chart: live price + trade markers | P1 |
| F-U-11 | Diff view for strategy code changes | P2 |

## 8. Authentication & authorisation

| ID | Requirement | Priority |
|---|---|---|
| F-A-01 | Single-user login with password | P0 |
| F-A-02 | 2FA (TOTP) required for sensitive actions (go live, kill switch confirm, broker connect) | P0 |
| F-A-03 | Session timeout (configurable, default 8 hours) | P0 |
| F-A-04 | Audit log of all logins, logouts, sensitive actions | P0 |
| F-A-05 | Multi-user support with roles (admin, trader, viewer) | P3 |

## 9. Notifications & alerts

| ID | Requirement | Priority |
|---|---|---|
| F-N-01 | Telegram bot integration for alerts | P0 |
| F-N-02 | Email alerts as fallback | P1 |
| F-N-03 | Alert categories (configurable per channel): trade entry/exit, errors, risk breach, broker disconnect, daily summary | P0 |
| F-N-04 | Mobile push (PWA) | P2 |
| F-N-05 | Quiet hours (don't ping at 3 AM unless critical) | P1 |

## 10. Audit & compliance

| ID | Requirement | Priority |
|---|---|---|
| F-C-01 | Immutable audit log of every: order, fill, signal, config change, login, kill switch trigger | P0 |
| F-C-02 | Audit log retention ≥5 years (SEBI minimum) | P0 |
| F-C-03 | Audit log export (CSV, JSON) | P0 |
| F-C-04 | Strategy code version pinning per trade (which version produced this trade?) | P0 |
| F-C-05 | OPS counter visible in real-time | P1 |
| F-C-06 | Compliance dashboard summarising regulatory state (IP whitelist, OPS thresholds, etc.) | P1 |

## 11. Operations

| ID | Requirement | Priority |
|---|---|---|
| F-Op-01 | Single-command startup (`docker compose up` or `python -m algotrader`) | P0 |
| F-Op-02 | Graceful shutdown (cancel orders, close WebSocket, flush DB) | P0 |
| F-Op-03 | Health check endpoint | P0 |
| F-Op-04 | Database migration scripts | P0 |
| F-Op-05 | Backup script for DB and config | P1 |
| F-Op-06 | Crash recovery — restart picks up positions and orders correctly | P0 |
| F-Op-07 | Resource usage stays predictable (no memory leaks over a trading day) | P0 |

## Acceptance criteria (when is v1 "done"?)

The v1 release is complete when **every P0 requirement above is implemented, tested, and documented**, AND the following end-to-end demo works:

1. Start fresh on a clean machine
2. Drop a strategy file into `strategies/`
3. Drop the Zerodha broker file (already there) and configure credentials
4. Open dashboard, log in with 2FA
5. Run a backtest of the strategy on 6 months of data — see metrics
6. Switch the strategy to paper mode — see it place simulated orders for one trading session
7. Switch to live mode (with confirmation) — see it place a real (small) order
8. Trigger the kill switch — confirm all orders cancel within 5 seconds
9. Export the day's audit log

If steps 1–9 work without manual code edits, v1 is done.

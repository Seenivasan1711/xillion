# 01 — Product Requirements Document (PRD)

## 1. Vision

Build a **self-hosted, personal algorithmic trading platform** where adding a new strategy is as easy as dropping a Python file in a folder, and adding a new broker is just as easy. The platform handles backtesting, paper trading, and live execution from the same strategy code, with a clean dashboard for monitoring and a hard kill switch for safety.

The system should feel like infrastructure you trust, not a science project — even when you're the only user.

## 2. Why this exists

You want to:

- Automate your trading instead of clicking buttons in a broker app.
- Test strategy ideas against historical data before risking real money.
- Watch a live position from your phone without writing custom dashboards each time.
- Add a new broker someday (Upstox, Fyers, AngelOne, Dhan, etc.) without rewriting strategies.
- Eventually offer this to others — but only after the personal-use version has earned your trust.

Existing options have gaps:

| Option | Gap |
|---|---|
| Pure scripts (kiteconnect + cron) | No UI, no risk controls, no multi-strategy management |
| Backtrader / Backtesting.py alone | Great for backtesting, weak for live ops & dashboards |
| No-code platforms (Streak, Tradetron) | Vendor lock-in, limited strategy expressiveness |
| Open-source frameworks (OpenAlgo, etc.) | Closer fit, but most are broker-coupled or not plugin-clean |

This project occupies the gap: **lightweight, personal, plugin-clean, dashboard-first.**

## 3. Target users

### v1 — Primary user (you)

- One person, one machine, one or two brokers.
- Comfortable writing Python.
- Trades on Indian markets (NSE/BSE/F&O via Zerodha to start).
- Wants visibility on phone but doesn't want to babysit the bot all day.

### Future — Commercial users (out of scope for v1)

- Other retail traders who want a self-hosted bot but don't want to build one.
- Small advisory firms running strategies on family/friend accounts (within SEBI's personal-and-immediate-family rules).

The PRD focuses on v1. Commercial requirements are noted as **[Future]** where they shape current decisions.

## 4. Goals

### Primary goals (must achieve in v1)

| ID | Goal | Success looks like |
|---|---|---|
| G1 | **Zero-friction strategy addition** | Drop a `.py` file in `strategies/`, refresh UI, see it listed and configurable |
| G2 | **Zero-friction broker addition** | Drop a `.py` file in `brokers/`, configure credentials in env/DB, it works |
| G3 | **Same code, three modes** | A strategy works in backtest, paper, and live mode without conditional code in the strategy |
| G4 | **Operational confidence** | Clear UI showing: what's running, P&L, positions, errors, plus a one-click kill switch |
| G5 | **Auditability** | Every order, fill, signal, and config change logged for ≥5 years (SEBI requirement) |
| G6 | **SEBI compliance for personal use** | Stay within retail thresholds; static IP; no shared algos |

### Secondary goals (nice to have in v1)

- Mobile-friendly UI (responsive, not native app).
- Telegram/email alerts on critical events.
- Strategy parameter optimisation (grid search, walk-forward).
- Multi-account paper trading (run several strategies in parallel without real money).

### Non-goals (explicitly out of scope)

- High-frequency trading, sub-millisecond latency.
- Multi-tenant SaaS in v1.
- Black-box / signal-selling features (would require SEBI Research Analyst registration).
- Automated strategy generation / ML model training pipeline.
- Crypto, forex, or non-Indian markets in v1 (architecture supports it, but no implementation).

## 5. Scope at a glance

### In scope (v1 — MVP)

- Plugin loaders for strategies and brokers
- Strategy lifecycle: backtest → paper → live
- Zerodha (Kite Connect) broker plugin
- Built-in paper-trade broker plugin
- Web dashboard: list strategies, P&L, positions, orders, logs, kill switch
- Single-user auth (login + 2FA)
- SQLite storage (Postgres-ready schema)
- Risk controls: per-strategy & global daily loss cap, position limits, kill switch, OPS rate limit
- Audit log (immutable, exportable)
- Backtest engine with standard metrics (Sharpe, Sortino, max drawdown, win rate, profit factor)
- Historical data fetcher (Zerodha + CSV import)
- Telegram alerts for critical events

### v1.5 (next iteration)

- Second broker plugin (Upstox or Fyers) — proves the abstraction works
- Strategy parameter optimisation
- Walk-forward backtesting
- Email reports (daily summary)
- Postgres migration path documented and tested

### Future / commercial

- Multi-tenant accounts
- Per-user broker connections
- Subscription billing
- Strategy marketplace (regulatory homework required)
- Mobile native app (only if responsive web isn't enough)

## 6. User journeys (the ones that matter)

### Journey A: "I just thought of a new strategy"

1. Open VS Code, copy `strategies/_template.py` to `strategies/orb_breakout.py`.
2. Implement `on_bar()` and `on_tick()` methods with my logic.
3. Open dashboard → Strategies → click **Reload**.
4. New strategy appears. Click it → set instrument (NIFTY), capital (₹50k), parameters (range = 30 min, qty = 1 lot).
5. Click **Run Backtest** → 2024 data → see equity curve, Sharpe 1.4, max DD 8%. OK-ish.
6. Click **Switch to Paper** → leave it for 5 trading days.
7. Paper results match backtest within tolerance. Click **Switch to Live**. Confirm with 2FA.
8. Strategy now trades real money. Phone gets Telegram pings on entries/exits.

### Journey B: "I want to add Upstox"

1. Read `brokers/_base.py` to see the broker interface.
2. Copy `brokers/zerodha.py` to `brokers/upstox.py` and adapt the API calls (mostly: auth, place_order, get_positions, get_quote, websocket).
3. Add `UPSTOX_API_KEY` etc. to `.env`.
4. Restart the backend.
5. Dashboard → Settings → Brokers → "Upstox" appears, marked Connected.
6. Existing strategies can now be assigned to Upstox without code changes.

### Journey C: "Something is going wrong"

1. Phone Telegram ping: "Strategy ORB_NIFTY drawdown -2.5%, approaching daily limit (-3%)."
2. Open dashboard → see live equity curve dipping.
3. Either:
    - Click **Pause Strategy** (stops new entries, keeps current position) — or
    - Click the red **KILL SWITCH** in the header (stops everything, cancels open orders, optionally exits positions).
4. Investigate at leisure. Audit log shows every signal and order in the last hour.

### Journey D: "I want to know what happened today"

1. Dashboard → Today tab.
2. See: total P&L, per-strategy P&L, trade count, win rate, biggest winner, biggest loser.
3. Click any trade → drill into entry/exit reasoning, signals at the time, slippage vs expected.
4. Export to CSV for personal records.

## 7. Constraints & assumptions

### Constraints

- **Solo developer.** Build budget is realistic evenings/weekends, not full-time.
- **Indian regulations.** SEBI personal-use rules (see doc 07) shape several decisions.
- **One broker at start.** Zerodha first because it's where you have an account; abstraction must allow others.
- **Self-hosted.** Runs on your own machine or VPS. No cloud services that would compromise auth tokens.

### Assumptions

- You're trading on Zerodha and have a Kite Connect subscription (₹500/month) or are willing to get one.
- You can write Python (the strategy authoring is in Python).
- You're trading instruments where bar-level data and ≤1-second decision latency is acceptable. Not HFT.
- For commercial mode (later): users will be SEBI-aware retail traders running their own strategies on their own accounts.

## 8. Success metrics

For v1 personal use, success isn't ARR or DAU. It's:

| Metric | Target | How measured |
|---|---|---|
| Time to add a new strategy | < 30 min from idea to backtest | Personal log |
| Time to add a new broker plugin | < 1 day for someone with the broker's API docs | Self-test by adding Upstox |
| Strategy uptime in live mode | > 99% during market hours | Monitoring/logs |
| False positives on alerts | < 1 per week | Telegram alert review |
| Audit log completeness | 100% of orders + fills logged | DB cross-check vs broker |
| Kill switch latency | All orders cancelled within 5 seconds | Manual test |

## 9. Risks (high-level — see doc 07 for full risk register)

| Risk | Severity | Mitigation |
|---|---|---|
| A bug causes runaway orders | Critical | OPS limiter + daily loss cap + kill switch + paper-mode default |
| Broker API token expires mid-day | High | Daily auto-relogin (Kite tokens expire ~6 AM IST); alert on auth failure |
| Misreading a backtest, then losing money live | High | Paper-trade gate before live; clear divergence reporting |
| Network drop during open position | High | Reconnection logic; alert on disconnect; broker-side stops |
| SEBI rule changes | Medium | Compliance doc kept current; build to spec, not to loophole |
| Security breach (token theft) | Critical | Local-only DB by default; secrets in env, not committed; 2FA on dashboard |

## 10. Release plan summary

See [09 Progress Tracker](./09-progress-tracker.md) for the detailed plan. High-level phases:

| Phase | Duration (rough) | Outcome |
|---|---|---|
| 0 — Foundations | 1 week | Repo, scaffolding, CI, dev env |
| 1 — Plugin core | 2 weeks | Strategy & broker loaders work; paper broker plays back fake data |
| 2 — Backtest engine | 2 weeks | Run a strategy against historical CSV; see metrics |
| 3 — Zerodha integration | 2 weeks | Connect, fetch data, place paper-mode orders via Kite |
| 4 — Live trading + risk | 2 weeks | Real orders, kill switch, daily loss cap, audit log |
| 5 — Dashboard polish | 2 weeks | The UI you'd actually use on phone |
| 6 — Hardening | 1 week | Tests, docs, alerts, deploy |

Total: **~12 weeks evenings/weekends** to a usable v1. Optimise for "trustworthy" over "feature-rich."

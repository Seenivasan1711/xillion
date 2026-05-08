# 07 — Risk Management & SEBI Compliance

This is the document you re-read before going live.

## Part A: Risk management

A trading bot can lose money faster than a human. Three core risks dominate:

1. **Strategy risk** — your idea doesn't work in production
2. **Execution risk** — the bot does something it shouldn't (bug, race condition, runaway loop)
3. **Operational risk** — outages, network drops, broker rate-limits

The goal of v1's risk system is to **box your worst day** so it can't become your last day.

### A.1 Risk control hierarchy

Five gates an order passes through before reaching the broker. Each can stop it.

```
Strategy generates signal
        │
        ▼
   ┌────────────────────────────────┐
   │ 1. Strategy-internal checks    │  ← author-defined; e.g. "skip if VIX > 30"
   └────────────────────────────────┘
        │
        ▼
   ┌────────────────────────────────┐
   │ 2. Per-strategy risk limits    │  ← framework: max position, daily loss
   └────────────────────────────────┘
        │
        ▼
   ┌────────────────────────────────┐
   │ 3. Account-level risk limits   │  ← framework: total exposure, daily loss
   └────────────────────────────────┘
        │
        ▼
   ┌────────────────────────────────┐
   │ 4. Rate / OPS limiter          │  ← framework: stay below SEBI threshold
   └────────────────────────────────┘
        │
        ▼
   ┌────────────────────────────────┐
   │ 5. Pre-trade margin / sanity   │  ← framework: enough margin? sane price?
   └────────────────────────────────┘
        │
        ▼
   ┌────────────────────────────────┐
   │ 6. Broker-side risk            │  ← Zerodha / exchange: their checks
   └────────────────────────────────┘
        │
        ▼
   Order goes to market
```

Any gate rejects → audit log + alert + return error to strategy. The strategy sees a `RejectionError`, not a silently dropped order.

### A.2 Required risk controls (P0)

| Control | Description | Where enforced |
|---|---|---|
| Per-strategy daily loss cap | If strategy realised+unrealised P&L < −X, auto-pause | Risk Manager |
| Account daily loss cap | If account P&L < −X, kill switch fires | Risk Manager |
| Per-strategy max position | Cap on `abs(quantity)` per symbol | Risk Manager |
| Per-strategy max open positions | Cap on count of non-zero positions | Risk Manager |
| Per-strategy capital allocation | Cap on `Σ(price × qty)` of open positions | Risk Manager |
| OPS limiter | ≤ 9 orders/sec/exchange (under SEBI 10/sec retail threshold) | Risk Manager |
| Margin pre-check | Reject if estimated margin > available | Risk Manager |
| Price sanity | Reject limit orders > 5% from LTP unless explicitly tagged | Risk Manager |
| Quantity sanity | Reject if quantity > some absolute cap | Risk Manager |
| Idempotency | Same `client_order_id` twice → reject second | Execution |
| Disconnect protection | If broker disconnected > N seconds, pause new orders | Execution |
| Reconciliation | Periodic state diff vs broker; alert on mismatch | Background job |
| Kill switch | One button stops all, cancels open orders, optionally exits | UI + Risk Manager |
| Strategy crash isolation | Exception in one strategy doesn't crash others | Strategy Engine |
| Daily loss → cooldown | After hitting per-strategy loss, no auto-resume next day | Risk Manager |

### A.3 Position sizing

The system supports several models; the strategy picks one:

- **Fixed quantity** — "always buy 1 lot"
- **Fixed capital** — "use ₹50k per trade"
- **% of capital** — "use 10% of allocated capital"
- **Volatility-based (ATR)** — "size such that 1×ATR move = 1% of capital"
- **Custom** — strategy author overrides

For v1, fixed quantity and fixed capital are required; ATR-based is P1.

### A.4 The kill switch — design specifics

**Triggers:**
1. User clicks UI button (with 2FA)
2. Account daily loss threshold hit
3. Reconciliation detects severe mismatch (positions differ by > tolerance)
4. N consecutive broker errors in M seconds
5. CLI command (`algotrader kill`)

**Effect:**
1. Set `daily_risk_state.kill_switch_active = 1` (durable flag)
2. Send `cancel_all_open_orders` to every connected broker (with retry)
3. If "exit positions" toggle is on: send market orders to flatten
4. Pause all strategy instances → status `KILLED`
5. Append immutable audit log entry
6. Push UI banner + Telegram alert

**Reset:**
Manual only. User opens admin → "Reset kill switch" → confirms with 2FA + types reason.

**Latency target:** < 5 seconds from click to "all open orders cancelled."

### A.5 Reconciliation

Every 60 seconds (configurable), a background job:
1. Fetches positions, orders, holdings from each connected broker
2. Compares with our DB
3. If everything matches: log heartbeat
4. If discrepancy (within tolerance): log warning
5. If significant discrepancy: pause new orders, alert critical

This catches: missed websocket messages, manual orders the user placed in Kite app, broker-side cancellations we missed.

### A.6 Things we deliberately don't do (yet)

- **Smart order routing** — single broker per instance, no venue selection
- **Dynamic VaR** — position limits are static configs, not VaR-based
- **Cross-strategy hedging** — strategies are independent
- **Auto-resume after kill switch** — manual reset always required

## Part B: SEBI compliance (India, 2025–2026)

### B.1 The headline rules

In February 2025 SEBI issued a circular on "safer participation of retail investors in algorithmic trading." It came into effect August 2025 and becomes fully mandatory for brokers from April 2026.

The key facts that shape this product:

1. **Retail traders may run their own algos** for their own and immediate-family accounts (spouse, dependent children/parents). Self-developed algorithms can only be used for personal accounts, including those of immediate family members. Sharing/selling algos to others triggers vendor / Research Analyst rules.

2. **OPS threshold = 10 orders/second/exchange.** If your trading frequency stays below 10 orders per second, you are considered a regular API user, not an algo trader. Above that threshold, mandatory registration applies.

3. **Static IP whitelisting.** Broker APIs require traders to whitelist a static IP from which API calls originate.

4. **2FA / OAuth-based auth.** Open APIs are deprecated; OAuth + 2FA are mandatory.

5. **Audit trail.** Brokers maintain 5-year logs of algo activity. Your bot should keep its own logs of equal duration.

6. **Algo tagging.** Each registered algo gets a unique exchange-issued Algo ID; orders carry this ID. (Only relevant if you cross the OPS threshold and register.)

7. **White box vs black box.** Strategies whose logic is fully transparent to the trader (you wrote it, you know what it does) are white box and have lighter requirements. Black box (you don't know the logic) requires the provider to be a SEBI-registered Research Analyst. Personal-use, self-written strategies are white box by definition.

### B.2 What this means for v1 (personal use)

Provided you:
- Stay **under 10 OPS per exchange**
- Use the bot **only for your own and immediate-family accounts**
- Connect via **broker API with static IP and 2FA**
- Maintain **audit logs**

…you are inside the retail-permitted lane and **don't need to formally register your algos with the exchange**.

The bot should make this safe by default:
- OPS limiter set to 9/sec by default (configurable, never above 10)
- Static IP banner: bot warns at startup if outbound IP doesn't match `APP_BIND_IP` env var
- Audit log retention ≥ 5 years
- 2FA gate on all sensitive actions
- Single-user auth in v1 (you can't accidentally let someone else trade through it)

### B.3 What changes for commercial use

The moment you offer this to other people, the regulatory picture changes drastically:

- You are a **vendor / algo provider** under SEBI rules
- You must **empanel with stock exchanges** (NSE/BSE)
- Your brokers (the brokers your users trade through) conduct due diligence on you
- Each strategy you offer must be **registered and approved** by the exchange
- If any strategy is black box (logic not disclosed to user): you need **SEBI Research Analyst registration**, plus published research reports per strategy, with re-registration required for any logic change

There is also a meaningful infrastructure rule: Only algorithms hosted and deployed through broker-owned infrastructure will be permitted. Third-party servers, cloud services, or uncontrolled environments are prohibited unless integrated with the broker system. For commercial deployment you'd be integrating into broker infrastructure or operating as an empanelled vendor — not just spinning up an EC2 box.

**The implication for this product:**
- v1 personal-use is fully fine
- Commercial pivot requires real legal work, not just code work
- Architecture should keep the option open (multi-tenant data model in doc 05 hints at this) but **not pretend the regulatory path is solved**

### B.4 Concrete compliance features in v1

| Feature | Implementation |
|---|---|
| Order tagging | Every order carries `strategy_instance_id` and `tag`; field for exchange Algo ID is in schema (nullable for v1) |
| OPS rate limiter | Token-bucket per exchange, default 9/s |
| Audit log with hash chain | See `audit_log` table in doc 05 |
| Static IP enforcement | Startup check; warns or refuses if IP differs from configured |
| 2FA on sensitive actions | Login + go-live + kill switch + broker connect |
| Token rotation | Daily Kite token refresh job (Kite tokens expire ~6 AM IST) |
| Encrypted secrets | API keys in env, TOTP secrets encrypted in DB |
| Personal-use scope | Single-user auth in v1; no "share strategy" feature |
| Compliance dashboard | Settings → Compliance shows IP, OPS, last token refresh, audit log status |

### B.5 Things to verify with your broker before going live

1. **Static IP whitelisting process** — Zerodha's procedure to register your bot's IP
2. **Token refresh automation** — Zerodha disallows automating the OAuth login in some interpretations; review their developer terms before deploying TOTP-based auto-login
3. **OPS measurement** — confirm whether they measure OPS at the broker or exchange level
4. **Algo registration** — only needed if you exceed OPS threshold; their procedure if you ever do

These are operational details, not architecture, but the bot's settings panel should remind you about them.

### B.6 Disclaimer

This document summarises rules as the author understands them in 2025–2026. **Regulations change.** Before going live with real money, verify the current SEBI / NSE / BSE circulars and your broker's current policies. The bot is infrastructure; legal compliance is on you.

## Part C: Risk-mitigation playbook

A handful of "before you do this, do that" rules to live by:

1. **Backtest on out-of-sample data.** Train/optimise on 2022–2023; test on 2024. Don't promote a strategy from backtest to paper if it only worked on the data you tuned it on.
2. **Paper trade for at least N sessions** before going live. Default N = 5 trading days; configurable. The system can enforce this — make `live` mode require a successful paper-trade history.
3. **Start small.** New live strategy → low capital allocation. Only increase after a few weeks of stable behaviour.
4. **Daily loss caps are not aspirational.** Set them. The bot enforces them. Don't override them on a hunch.
5. **Don't trust a strategy that hasn't seen a market regime change.** A strategy backtested only on 2023's range-bound chop will surprise you in a trending year.
6. **Read the audit log weekly.** It's the only honest history.
7. **The kill switch is free to use.** If you're nervous, kill it. Re-deploy when you've thought it through.

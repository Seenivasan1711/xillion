# 16 — Deferred Backlog

> Things consciously **not** being built right now, with the reason. This
> exists so nobody (human or AI) rediscovers them as "gaps" and burns time
> re-deciding. If you find yourself thinking "why doesn't this have X?" —
> check here first.
>
> **Deferred ≠ rejected.** Each entry has a trigger that would make it worth
> revisiting.

**Last reviewed:** 2026-08-24

---

## Product scope

| Item | Why deferred | Revisit when |
|---|---|---|
| Multi-user auth, RBAC | Single-user personal system. Auth exists for *you*, not tenancy | This becomes a product with other users |
| Per-tenant data isolation | Same as above — pure complexity cost today | Same as above |
| Subscription billing | No customers | Same as above |
| SEBI vendor empanelment | Legal track only relevant for a commercial offering. Personal algo use is already permitted under the 2025/26 retail framework | Going commercial |
| Mobile native app | Responsive web works on phone; a native app is months of work for marginal gain | Web genuinely fails on mobile during a stressful trading moment |

## Integrations

| Item | Why deferred | Revisit when |
|---|---|---|
| Upstox / Fyers broker plugin | Zerodha works; MT5 is the *needed* second broker (gold/forex). A third adds maintenance with no new capability | Zerodha becomes unreliable, or you need an instrument it doesn't offer |
| TrueData / Global Datafeeds | Paid tiers (~₹1-2k+/mo). Free NSE bhavcopy covers daily bars; Kite covers intraday | A strategy genuinely needs OI/IV/Greeks *history* — see the data-tier table in [13-quantman-parity-roadmap.md](../product/roadmap-quantman-parity.md) |
| Sensibull / Opstra | Analytics products, not raw data feeds. Useful for manual validation, not for our engine | You want a second opinion on payoff/greeks, manually |
| Offshore retail forex/CFD brokers | FEMA grey-to-prohibited for Indian residents. Funding Pips prop model chosen instead | Never, unless the regulatory position changes materially |

## Engine features

| Item | Why deferred | Revisit when |
|---|---|---|
| Tick-level backtesting | Daily/minute bars are enough for the current strategy class, and tick data is expensive + slow | A strategy's edge depends on intra-bar sequencing |
| Realistic LIMIT order simulation | Backtest fills at bar close ± slippage. Fine for market orders | Strategies start relying on passive limit fills |
| Options greeks engine (own IV/delta calc) | Not needed until a strategy conditions on greeks | A course strategy uses delta/theta thresholds |
| Portfolio-level position sizing (Kelly, risk parity) | Single strategy, fixed sizing. Premature | Running 3+ uncorrelated strategies simultaneously |
| Multi-timeframe strategies | Current strategies use one timeframe | A strategy needs e.g. daily trend + 5m entry |
| Backtest custom date-range picker (UI) | Largely covered — provider mode already takes explicit from/to dates | The UI gap actually bites |

## Crypto specifics

| Item | Why deferred | Revisit when |
|---|---|---|
| Entire crypto asset class | **1% TDS per transaction** in India. A strategy trading 100×/month pays ~100% of one position's value in TDS annually — structurally unprofitable for active trading. 30% flat tax on gains on top | Tax regime changes, **or** a genuinely low-frequency (weekly+) crypto strategy is identified |

## Explicitly rejected (not just deferred)

| Item | Why |
|---|---|
| LLM constructing orders freeform | An LLM must never be able to invent an order. MCP exposes query + guarded control only (start/stop/kill-switch). This is a safety boundary, not a feature gap |
| Auto-scaling capital on good weeks | Capital increases only on a proven multi-month track record. Scaling on a hot streak is how accounts blow up |
| Skipping paper soak to go live faster | The soak is calendar-bound *by design* — it's the gate that catches what backtests can't |

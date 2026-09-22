# 16 — Deferred Backlog

> Things consciously **not** being built right now, with the reason. This
> exists so nobody (human or AI) rediscovers them as "gaps" and burns time
> re-deciding. If you find yourself thinking "why doesn't this have X?" —
> check here first.
>
> **Deferred ≠ rejected.** Each entry has a trigger that would make it worth
> revisiting.

**Last reviewed:** 2026-08-28

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

## Automation platform

| Item | Why deferred | Revisit when |
|---|---|---|
| DB/UI-configurable Twelve Data + Finnhub credentials | Shipped 2026-09-21 as `.env`-only (`TWELVE_DATA_API_KEY`, `FINNHUB_API_KEY`) to get real Gold data flowing fast — same shortcut `MT5_FUNDING_PIPS_ENABLED` uses. Dhan/Zerodha/MT5 all have the proper DB-backed Settings-page pattern; these two don't yet. Not urgent for a single-user local setup (edit `.env` + restart). Real fix: a Settings → Data Providers card + `POST/GET /settings/twelve-data` mirroring Dhan's single-field shape | Rakesh wants to rotate/change either key without editing `.env`, or a second person/machine needs its own key |

## Engine features

| Item | Why deferred | Revisit when |
|---|---|---|
| Tick-level backtesting | Daily/minute bars are enough for the current strategy class, and tick data is expensive + slow | A strategy's edge depends on intra-bar sequencing |
| Realistic LIMIT order simulation | Backtest fills at bar close ± slippage. Fine for market orders | Strategies start relying on passive limit fills |
| Options greeks engine (own IV/delta calc) | Not needed until a strategy conditions on greeks | A course strategy uses delta/theta thresholds |
| Portfolio-level position sizing (Kelly, risk parity) | Single strategy, fixed sizing. Premature | Running 3+ uncorrelated strategies simultaneously |
| Multi-timeframe strategies | Current strategies use one timeframe | A strategy needs e.g. daily trend + 5m entry |
| Backtest custom date-range picker (UI) | Largely covered — provider mode already takes explicit from/to dates | The UI gap actually bites |

## Gold Lane B1 (XAUUSD/Funding Pips MT5) specifics

**Historical Gold (XAUUSD) data source for backtesting — built 2026-08-29,
no longer deferred.** Rakesh picked candidates (a) and (b) together
(explicitly declined (c), the paid option) — see "Gold Lane B1 backtest
data source" under CP15/Track B in `docs/status/task-tracker.md` for the
full writeup:
- **(a)** `mt5_bridge/bridge.py` extended to also fulfil on-demand
  historical requests via MT5's own `copy_rates_range()`, using the same
  DB-queue-and-poll shape already used for live orders (migration 019) —
  registered as the `MT5 Bridge (Gold)` data provider.
- **(b)** `data_providers/alpha_vantage_fx.py`, a free (API-key-only)
  daily-bar backup for when the bridge itself isn't reachable — registered
  as the `Alpha Vantage FX` data provider.
- Also requested: a persistent "local agent" connection so backtests work
  even away from the Mac. This is exactly what the bridge's existing
  poll-out (not poll-in) architecture already provides — no separate
  mechanism was needed, just extending the one channel that already
  exists to carry historical requests too.

## Gold Sweep-Reversal — planned Stage 2 follow-up analysis (2026-09-22)

Not deferred-forever, this is the actual next-up queue for this
strategy specifically, in priority order Rakesh set 2026-09-22 after
seeing the first real backtest + parameter sweep both come back
net-negative (see `docs/strategies/gold-xauusd-sweep-reversal.md` §3):

1. **Session-window sweep** — test `session_start_utc_hour`/
   `session_end_utc_hour` combinations (not just London 07:00-13:00 UTC)
   against the same 6-month sample, to find which time-of-day window (if
   any) actually has an edge, rather than assuming the card's own window
   is the right one for this specific signal.
2. **Richer level data for the decision** — the current daily levels are
   only Asian session + previous-day high/low. Before deciding whether to
   change the session window (item 1), it'd help to have high/low broken
   out per named session (Asian/London/NY, not just "Asian" + "previous
   day as a whole") and over more than just 1 prior day (e.g. last 3-5
   days), as supporting context for whichever decision comes out of the
   sweeps above — not necessarily new tradeable levels, but visibility.
3. **`min_sl_pts`/`max_sl_pts` further optimization** — the two sweeps run
   2026-09-22 (30 + 27 combos) didn't find a profitable combination, but
   only covered a fairly coarse grid; a finer sweep (and combined with
   item 1's session-window changes, since the two may interact) is
   reasonable before concluding the parameter family is dead.
4. **`tp_pts` further optimization** — same as above, same reasoning
   (coarse grid so far, worth a finer/combined sweep before concluding).
5. **Confidence scoring for entries** — a "how confident is this specific
   setup" score (a %, not just a binary sweep/reclaim yes-or-no), used to
   gate which signals actually fire and/or to make the post-entry cooldown
   itself dynamic (a high-confidence setup might not need as long a
   cooldown before the next one is allowed; a low-confidence one might
   need longer, or should be skipped/flagged rather than auto-fired at
   all). Not designed yet -- needs a real feature set (e.g. how far past
   the level did price sweep, how quickly it reclaimed, recent win/loss
   streak, time-of-day, spread if ever available) and a real decision on
   whether the score is a hard gate or just extra context shown in the
   Telegram/reasoning text. This is what makes cooldown "optimizable"
   rather than the current fixed `cooldown_minutes`.

## Advanced / next-level (explicitly deferred until the above is settled)

**Agent/workflow-driven signal generation ("JEV").** Rakesh is exploring
having signal generation itself go through an agent/workflow pipeline
(multiple steps/checks, not a single mechanical rule function) rather than
today's direct on_bar logic -- his own framing, 2026-09-22. **Explicitly
deferred by his own call** until the current code-level strategy (backtest
economics, session/level analysis, confidence scoring above) is "perfected"
first -- there's no value building an agent pipeline around a signal
function whose own edge hasn't been established yet. Revisit once items
1-5 above are resolved and Gold Sweep-Reversal has a real, decided-on
parameter set. Related, already-built precedent to reuse rather than
reinvent: CP8's AI-confidence hook (`prosper-engine`, cross-repo, see
CLAUDE.md) already wires an LLM into the signal path as a background,
non-blocking check -- worth revisiting as a starting point rather than a
from-scratch design.

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

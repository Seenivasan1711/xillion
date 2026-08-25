# Strategy: Credit Spread Weekly

> One file per strategy. Written at Stage 1, updated at every pipeline stage.
> **These files are ingested into the RAG layer (CP8)** — the assistant answers
> "why did this strategy fail last October?" from here, so write for a reader
> with no memory of the conversation.

**Asset class:** options (Nifty / Sensex weekly)
**Broker:** Zerodha (paper/live) — Dhan once CP15 lands
**Status:** Stage 1 build (done, 2026-08-25) — implementation at
[strategies/credit_spread_weekly.py](../../strategies/credit_spread_weekly.py)
**Created:** 2026-08-25 · **Last updated:** 2026-08-25

---

## 1. The rules (plain language)

Full mechanical source: [knowledge-base/10-FIRST-STRATEGY-SPEC.md](knowledge-base/10-FIRST-STRATEGY-SPEC.md)
(KB Rank 1 — [knowledge-base/07-RANKED-LOW-RISK-HIGH-WIN.md](knowledge-base/07-RANKED-LOW-RISK-HIGH-WIN.md)).
This file states the rules exactly as coded; the KB file has the research and
alternative arms this run doesn't yet cover.

- **Universe:** Nifty weekly (Tuesday expiry, lot 65) or Sensex weekly
  (Thursday expiry, lot 20) — chosen per instance via the `underlying` param.
  Sensex's smaller lot fits far more capital tiers (KB 10 §1).
- **Entry timing:** 09:45–10:30 IST only, and only when the resolved
  contract's DTE equals `entry_dte` (default 4, cycle stage S3 — best
  risk-adjusted seller window per KB 01 §1.2).
- **Direction:** on the underlying's 15m chart — price > rolling VWAP AND
  20EMA > 50EMA → **Bull Put Spread** (sell downside). Price < VWAP AND
  20EMA < 50EMA → **Bear Call Spread** (sell upside). Anything else → skip
  this bar, don't force a trade.
- **Strikes:** short leg `short_offset_strikes` strikes OTM from ATM
  (default 4); long/protective leg a further `width_strikes` strikes beyond
  that (default 4). This is a strike-count proxy for the KB's delta-based
  selection (10–30 delta) — xillion has no options-greeks engine yet, so
  this is coarser than the spec's ideal. Both legs resolved via
  `ctx.resolve_strike`, walking the real listed ladder — never a hardcoded
  interval.
- **Entry filters applied:**
  - Credit adequacy: credit ≥ 15% of spread width (`min_credit_pct_of_width`) —
    KB 10 §5 Filter 4.
  - Trend alignment: baked into the direction rule above — KB 10 §5 Filter 2.
  - DTE gate: only at the configured `entry_dte` — approximates KB 10 §5's
    cycle-stage timing.
- **Entry filters NOT applied (honest gaps, not silent skips):**
  - VIX percentile filter (KB 10 §5 Filter 1 — "the single largest
    improvement found in any research reviewed", ~70%→86% win rate in the
    45-DTE study). No VIX data provider is wired into xillion. The
    `require_vix_filter` param exists so this is visible in the UI rather
    than silently absent.
  - Event veto (RBI/CPI/Fed/Budget) — no economic calendar provider wired.
  - Liquidity filter (bid-ask spread) — only checked when a broker actually
    returns bid/ask on its Tick; several data sources (e.g. NSE Bhavcopy)
    don't.
- **Sizing:** `max_loss_per_lot = (width − credit) × lot_size`,
  `lots = floor(risk_pct × capital / max_loss_per_lot)`. **Lots < 1 → skip,
  never round up** — KB 10 §7, the exact rule that rules out most Nifty
  spreads under ~₹5L capital.
- **Multi-leg entry/exit (CP11):** long/protective leg always placed first
  on entry, short leg placed first on exit. If a leg fails partway through,
  the leg-failure protocol ([xillion/core/multileg_execution.py](../../xillion/core/multileg_execution.py))
  either force-unwinds at market (if a naked short would otherwise result),
  retries once and unwinds cleanly (if the partial structure is still
  defined-risk), or halts for manual review (unclassifiable partial state) —
  see `docs/architecture/automation-platform-spec/06-JOBS-ENTRY.md` E05.
- **Target:** spread value decays to `(1 − profit_target_pct)` of entry
  credit (default 50% captured).
- **Stop-loss:** spread value rises to `stop_multiple_of_credit × entry
  credit` (default 2.0× = a loss equal to 100% of the credit received).
- **Time stop:** force-exit at `time_stop_dte` days to expiry (default 1) —
  avoids expiry-day gamma entirely, regardless of P&L.
- **Protective-order mechanics:** software stop, monitored on every tick of
  either leg by the strategy's own `on_tick` (not a separate always-on
  framework job yet — that generalisation is CP12's trailing-stop engine).
  No broker plugin in this codebase wires a real bracket/GTT order path
  today, so this is the spec's own documented fallback
  ([06-JOBS-ENTRY.md](../../docs/architecture/automation-platform-spec/06-JOBS-ENTRY.md)
  E07's ELSE branch), not a shortcut around it. Caveat inherited from the
  spec: a software stop needs the process alive to fire — a crash mid-position
  leaves it unprotected until CP12's watchdog exists.
- **What edge is this exploiting?** Selling option premium (theta decay)
  with a defined-risk hedge, entered when trend alignment gives the short
  side extra room to be wrong (3 of 4 outcomes still win: market rises,
  goes sideways, or falls modestly). The KB's own honest framing: this
  edge existed 2022–2025 and the evidence suggests it may have stopped
  paying in early 2026 (VRP inversion) — the backtest exists to find out
  which regime we're actually in before capital is at risk.

## 2. Backtest results (Stage 2)

**Not yet run.** Blocked on wiring options resolution (`get_spot` /
`resolve_strike` / `get_option_price`) into `BacktestEngine`'s context —
`_BacktestContext` in `xillion/engine/backtest_engine.py` doesn't implement
those methods today, so this strategy can only run in paper/live mode right
now. This is a real, separate piece of engineering (historical options
chain data + backtest-mode strike resolution), not something CP11 or this
strategy file addresses. Tracked as a Track B follow-up in
`docs/status/task-tracker.md`.

| Period | Regime | Trades | Win % | Total P&L | Max DD | Sharpe |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — |

- **Parameter sensitivity:** not yet tested
- **Manual spot-check:** not yet done
- **Data source + timeframe used:** n/a

## 3. Paper results (Stage 3)

**Window:** not yet started.

## 4. Live results (Stage 4)

Not started — Stage 2/3 gate this per `docs/process/asset-pipeline.md`.

## 5. Failure log

| Date | What happened | Failure mode | Change made |
|---|---|---|---|
| | | | |

Failure modes: `stopped_out` · `target_missed` · `late_entry` · `slippage` ·
`no_fill` · `gap` · `regime_change` · `data_gap` · `system_error`

## 6. Version history

| Version | Date | Change | Why |
|---|---|---|---|
| v1.0.0 | 2026-08-25 | Initial implementation — 2-leg credit spread, CP11 multi-leg execution + protective orders | First strategy built from the options knowledge-base + automation-platform-spec retrofit (D17-D20) |

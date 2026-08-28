# Strategy: Iron Condor Weekly

> One file per strategy. Written at Stage 1, updated at every pipeline stage.
> **These files are ingested into the RAG layer (CP8)** — the assistant answers
> "why did this strategy fail last October?" from here, so write for a reader
> with no memory of the conversation.

**Asset class:** options (Nifty / Sensex weekly)
**Broker:** Zerodha (paper/live) or Dhan
**Status:** Stage 1 build (done, 2026-08-29) — implementation at
[strategies/iron_condor_weekly.py](../../strategies/iron_condor_weekly.py)
**Created:** 2026-08-29 · **Last updated:** 2026-08-29

---

## 1. The rules (plain language)

Full mechanical source:
[knowledge-base/03-BAG-A-SELLING-DEFINED-RISK.md §A1](knowledge-base/03-BAG-A-SELLING-DEFINED-RISK.md).
This file states the rules exactly as coded; the KB file has the research
and win-rate citations.

- **Universe:** Nifty weekly or Sensex weekly, chosen via the `underlying`
  param — same as [credit-spread-weekly.md](credit-spread-weekly.md).
- **Entry timing:** 09:45–10:30 IST, and only when the resolved contract's
  DTE is at or below `entry_dte` (default 4) — same nearest-reachable-DTE
  rule as the credit spread, for the same expiry-weekday-regime reason.
- **Market view — the key difference from the credit spread:** the credit
  spread trades WITH a detected trend. The iron condor trades the opposite
  view — range-bound, no clear direction (KB §Regime: "range-bound ->
  neutral structures... do not sell a neutral structure into a trend
  day"). This strategy reuses the exact same 15m VWAP+EMA20/EMA50 trend
  check the credit spread uses, and enters exactly when NEITHER the bull
  NOR the bear condition holds — the credit spread's own "no clear trend,
  skipping entry" branch is this strategy's entry signal.
- **Structure:** four legs, one net credit — sell `short_offset_strikes`
  OTM call + buy a further `width_strikes` OTM call (call credit spread),
  and sell `short_offset_strikes` OTM put + buy a further `width_strikes`
  OTM put (put credit spread), same underlying/expiry. Both sides use the
  SAME offset/width params (KB's own worked example is symmetric); the
  real listed strike ladder may not be perfectly symmetric around spot, so
  the call-side and put-side point-widths are computed independently and
  sizing uses whichever is wider (the worst case a single-side breach
  could cost — loss only ever occurs on one side, never both).
- **Entry filters applied:**
  - Credit adequacy: combined credit ≥ 25% of the wider side's width
    (`min_credit_pct_of_width`, default 0.25 — KB A1's own "target credit
    ≈ 25–33% of width", a higher bar than the credit spread's 15% since a
    condor's credit is the sum of two sides).
  - Range-bound gate, described above.
  - DTE gate.
- **Entry filters NOT applied (honest gaps, inherited from the credit
  spread, not repeated in full here):** VIX percentile filter, economic
  event veto, liquidity (bid-ask) filter beyond what a broker's Tick
  actually provides. See [credit-spread-weekly.md](credit-spread-weekly.md)
  for the full reasoning on each.
- **Sizing:** `max_loss_per_lot = (width − credit) × lot_size` (same
  formula as the credit spread — `width` here is the wider side's width,
  `credit` is the combined credit from both sides), `lots = floor(risk_pct
  × capital / max_loss_per_lot)`. Lots < 1 → skip, never round up.
- **Multi-leg entry/exit:** both long (wing) legs placed before both short
  legs on entry; both short legs closed before either long leg on exit —
  same `order_entry_sequence`/`order_exit_sequence` discipline as the
  credit spread, generalised to 4 legs by
  [xillion/core/multileg_execution.py](../../xillion/core/multileg_execution.py).
  **Building this strategy is what proved that generalisation actually
  held** — two real bugs were found and fixed in the leg-failure protocol
  along the way (2026-08-29, see that module's own docstring for the full
  writeup): entry used to silently stop attempting legs after the first
  failure instead of trying an unrelated pair (invisible with the credit
  spread's exactly-2-leg shape, wrong for 4), and a failed exit's "force
  unwind" would have re-sold a leg that had already closed successfully,
  recreating exactly the naked position the protocol exists to prevent —
  a latent bug in the 2-leg case too, never caught because nothing tested
  a leg failing partway through an exit until this strategy's own test
  suite did.
- **Target:** combined condor value decays to `(1 − profit_target_pct)` of
  entry credit (default 50% captured, KB A1).
- **Stop-loss:** combined condor value rises to `stop_multiple_of_credit ×
  entry credit` (default 2.0× = a loss equal to 100% of credit received,
  KB A1).
- **Time stop:** force-exit at `time_stop_dte` days to expiry (default 1).
- **Protective-order mechanics:** software stop only, monitored every tick
  across all four legs via `condor_value()` (sum of both sides'
  `spread_value()` — see
  [xillion/core/protective_orders.py](../../xillion/core/protective_orders.py)).
  **No broker-native GTT backstop for this structure** — a real, deliberate
  scope cut, not an oversight: the credit spread's GTT anchors a single-
  instrument broker trigger to one spread's entry-fill price; fairly
  splitting a condor's combined stop/target threshold across two
  independent single-instrument GTTs needs its own allocation logic that
  doesn't exist yet. The software stop remains the primary protection
  mechanism regardless (same as the credit spread), so this is a gap in
  the worst-case backstop only, not in day-to-day protection.
- **What edge is this exploiting?** The same theta-decay premium-selling
  edge as the credit spread, but collecting premium from BOTH sides when
  the market has no directional conviction — doubles the number of moving
  parts (4 legs vs 2) and the transaction cost (KB 01 §Market-structure:
  "an iron condor is 4 legs × 2 (entry+exit) = 8 chargeable events") in
  exchange for collecting credit regardless of which way a small move
  breaks, as long as it doesn't run through either wing.

## 2. Backtest results (Stage 2)

**Not yet run.** Options-chain backtesting infrastructure exists
(`xillion/data/option_chain.py` + `BacktestEngine`'s
`option_chain_warehouse`, wired during the credit spread's own CP11
follow-up) and this strategy's `on_bar`/`on_tick` shape matches the credit
spread's closely enough that it should work unmodified — genuinely not yet
run, not assumed to work.

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
| v1.0.0 | 2026-08-29 | Initial implementation — 4-leg iron condor, first consumer of multi-leg execution beyond 2 legs, two real leg-failure-protocol bugs found and fixed along the way | "Multi-leg structures beyond 2-leg" — the multi-leg infrastructure was built generic from CP11 but never actually exercised past the credit spread's 2-leg shape |

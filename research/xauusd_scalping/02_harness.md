# XAUUSD scalping research harness — API reference

Standalone research infrastructure, deliberately separate from xillion's
production `xillion/engine/backtest_engine.py` — see the module docstring
in `engine/backtest_engine.py` for why (a from-scratch, fully-audited
engine is the point of `<part_4_proof>`; reusing unaudited production code
would defeat it). Read xillion's production code for patterns; nothing
here imports from it.

## Engine choice: custom, not backtesting.py/vectorbt

This project's correctness requirements are unusual: pessimistic
same-bar-ambiguity resolution as a first-class, tested, flippable flag;
a session/volatility-regime-tagged cost model (not a flat spread
constant); explicit gap-vs-touch fill distinction. Wrapping an existing
library would mean fighting its own fill-model assumptions as much as a
lean custom loop costs to write and prove correct — ~250 lines, and every
line is exercised by a synthetic-data test with a hand-computable expected
answer (`tests/test_engine.py`, 5/5 passing).

## What a strategy module must implement

```python
class MyStrategy:
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> Signal | None:
        ...
```

- Called **once per closed bar** — never on a forming candle, and never
  with a future bar visible (`ctx.bars()` only ever returns already-seen
  history; see `tests/test_engine.py::test_no_lookahead_possible_...`).
- Return `None` to do nothing this bar. Return a `Signal` to request an
  entry — but only if `ctx.has_open_position` is `False` (the engine
  itself only asks when flat, but the strategy should not assume it will
  never be asked with a position notionally still open on the same bar —
  see the same-bar re-entry note below).
- `ctx.bars(lookback: int) -> list[Bar]` — up to `lookback` most recent
  closed bars, oldest first, last element is the bar currently being
  evaluated.

## `Signal` fields

`side` (Side.LONG/SHORT), `stop_price`, `target_price`, `reason` (free
text, for later trade-log auditing), `partial_r`/`partial_pct` (not yet
wired into the engine's exit logic — accepted on the dataclass, TODO for
whichever P3 strategy actually needs partial-close/breakeven/trailing;
the base engine currently only manages a single stop+target per position).

## Fill mechanics (the part that matters most)

- **Pessimistic same-bar ambiguity** (default on, `pessimistic_same_bar_resolution`
  flag on `BacktestEngine.__init__`): if one bar's range contains both the
  stop and the target, the STOP is recorded as hit. `ambiguous_bar_count`
  on the result tells you how often this actually happened.
- **Gap-through fills at the gap, not the stop/target level**: if the
  bar's own `open` already jumped past the stop/target (not just the
  high/low touching it), the fill is at `open` — a resting order fills at
  whatever price the market actually gapped to. See
  `test_gap_through_stop_fills_at_gap_not_at_stop_price`.
- **Same-bar re-entry**: if a position closes mid-bar-processing (its stop
  or target was hit on bar N) and the strategy is flat and not halted, the
  engine will ask for a new signal on that SAME bar N before moving to
  bar N+1. This is a real, tested behavior (not a bug) — a strategy that
  cares about this should check `ctx.has_open_position` and its own
  internal cooldown state, the same way `strategies/gold_sweep_reversal.py`
  already does in the production xillion app.

## Cost model (`engine/cost_model.py`)

`CostModel` is a function of `(Session, VolBucket)`, not a flat constant —
`session_for(ts)` tags UTC-hour sessions (Asia/London/London-NY
overlap/NY/dead-zone), `vol_bucket_for(atr_percentile)` buckets by ATR
percentile tercile (P3's job to compute and pass in; the base engine
currently defaults every entry/exit cost lookup to `VolBucket.MEDIUM` —
**a known simplification**, not yet wired to a real rolling-ATR feed. A
strategy or P3's harness extension should override this before trusting
the by-session cost breakdown too literally).

Spread table values are a **stated pessimistic assumption**, not measured
from a real broker feed (Dukascopy's public tick data has no retail-spread
history attached) — see the table's own docstring. `CostModel.zero()`
exists for exactly the kind of cost-differential proof test in
`tests/test_engine.py`.

## Risk / session controls (`RiskLimits`, `SizingConfig`)

`max_trades_per_session`, `daily_loss_cap_usd` (checked **after** a trade
closes, using updated daily P&L — see the halt-timing note in
`test_daily_loss_cap_halts_new_entries_for_the_rest_of_the_day`),
`consecutive_loss_halt`, `max_spread_pts`. Sizing: `fixed_lot` or
`fixed_fractional` (risk % of current equity ÷ stop distance).

## Not yet built (flagged, not silently skipped)

- **News blackout window** is accepted as a constructor arg
  (`news_windows: list[tuple[datetime, datetime]]`) and widens
  slippage during it (`news_slippage_multiplier`), but there is no
  automatic free-econ-calendar-driven population of that list yet — the
  same real constraint this session already found for xillion's
  production Finnhub-based news veto (confirmed live: Finnhub's free tier
  doesn't include the economic-calendar endpoint). P3 will need to decide
  how to source real blackout windows, or accept this as a documented gap.
- **Partial close / breakeven / M5-trail management** — `Signal` has the
  fields, the engine doesn't act on them yet. Add when a P1 strategy
  actually needs it, not speculatively.
- **Monte Carlo trade-shuffling and walk-forward splitting** are P3's job,
  not this harness's — the harness's job (done) is producing a clean,
  auditable trade log (`Trade` dataclass: MAE/MFE, R-multiple, session,
  bars held, cost paid, ambiguous-bar flag) for P3 to run those analyses
  against.

## Running the tests

```
cd research/xauusd_scalping
python -m pytest tests/test_engine.py -v
```

5/5 passing as of this writeup, including all 4 tests the build spec's
`<part_4_proof>` explicitly requires (deterministic P&L, gap fill, no
lookahead, cost differential) plus one additional daily-loss-cap test.

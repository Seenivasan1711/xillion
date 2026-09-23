# Design question for another LLM: how should S04 detect a genuine multi-day trading range?

**Purpose of this file:** self-contained enough to hand to a different LLM
(no other project context) and get back a concrete, implementable design
recommendation. If you are that LLM: everything you need is below. Answer
with (1) a specific detection method, (2) why it's the right one for this
exact situation, (3) concrete default thresholds and how you'd justify
them without curve-fitting to the data described below, and (4) the
Python function signature to slot into the existing code.

## The strategy this feeds

"S04 — Wyckoff Spring/Upthrust at Range Extremes," one of 10 XAUUSD
scalping strategy candidates in a systematic research pipeline (not yet
proven, not live). The idea: find a multi-day price range (accumulation or
distribution, in Wyckoff terms), wait for a false breakout beyond the
range ("spring" below support, "upthrust" above resistance) that gets
reclaimed back inside, and trade the reversal.

This requires, as a precondition, correctly identifying that the last N
days actually *were* a range — as opposed to a trend, where a "breakout
beyond the recent extreme" is just trend continuation, not a spring/
upthrust reversal setup.

## The current (buggy) implementation

```python
@dataclass(frozen=True)
class RangeSpringResult:
    fired: bool
    range_high: float = 0.0
    range_low: float = 0.0
    direction: Direction | None = None  # UP = upthrust, DOWN = spring
    reclaimed: bool = False
    reason: str = ""

def range_spring_upthrust(
    self,
    daily_bars: list[Bar],       # one-bar-per-calendar-day OHLC, pre-resampled by the caller
    intraday_bars: list[Bar],    # the last few native-timeframe (M1) bars, for the actual sweep check
    range_min_days: int = 5,
    range_tolerance_pct: float = 1.5,
) -> RangeSpringResult:
    if len(daily_bars) < range_min_days:
        return RangeSpringResult(fired=False, reason="not enough daily history")
    window = daily_bars[-range_min_days:]
    range_high = max(b.high for b in window)
    range_low = min(b.low for b in window)
    span = range_high - range_low
    if span <= 0:
        return RangeSpringResult(fired=False, reason="degenerate range")
    tolerance = span * (range_tolerance_pct / 100.0)
    is_real_range = all(
        (range_high - b.high) <= tolerance and (b.low - range_low) <= tolerance for b in window
    )
    if not is_real_range or not intraday_bars:
        return RangeSpringResult(fired=False, reason="not a tight enough range")

    last = intraday_bars[-1]
    if last.high > range_high:
        return RangeSpringResult(fired=True, range_high=range_high, range_low=range_low,
            direction=Direction.UP, reclaimed=last.close < range_high, reason=f"upthrust beyond {range_high:.2f}")
    if last.low < range_low:
        return RangeSpringResult(fired=True, range_high=range_high, range_low=range_low,
            direction=Direction.DOWN, reclaimed=last.close > range_low, reason=f"spring beyond {range_low:.2f}")
    return RangeSpringResult(fired=False, range_high=range_high, range_low=range_low, reason="range holding")
```

**The bug is in `is_real_range`**: it requires **every single day** in the
5-day window to have its high within `tolerance` of the window's own
overall high, **and** its low within `tolerance` of the window's own
overall low — i.e., every day must touch near *both* extremes of the
range. Real daily OHLC bars (even genuinely range-bound ones) almost never
do both; a normal day in a real range touches near one edge, or neither,
not both simultaneously.

## Empirical evidence this is actually broken (not just theoretically iffy)

Traced directly against 174,554 real M1 XAUUSD bars (Dukascopy,
2026-03-01 to 2026-09-16, resampled to daily), sampling ~850-870 windows
across the full backtest:

- **852 of 873 sampled windows failed with `"not a tight enough range"`.**
  Only 21 failed with `"not enough daily history"` (early in the backtest,
  before 5 days existed). The strategy has never fired a signal in any
  backtest run — this single check is why.
- Two quick fixes were tried and both rejected:
  1. **Relaxing the per-day AND to an OR** (day counts if *either* its
     high is near the top *or* its low is near the bottom): still fired
     **0 times out of 852** samples. Still too strict.
  2. **A standard trend/range "efficiency ratio"** (`abs(close[-1] -
     close[0]) / sum(daily high-low ranges)`, a well-known Kaufman-style
     measure — low ratio = choppy/ranging, high = trending): fired on
     **~98% of the 852 sampled windows** at a threshold of 0.5. The
     percentile distribution of the ratio across those windows was: min
     0.0002, p10 0.032, p25 0.085, median 0.18, p75 0.30, p90 0.39, max
     0.58. **Every single window falls under even a strict 0.6 threshold**
     — the metric doesn't discriminate at all on this instrument/
     timeframe, because gold's daily high-low range (spread + intraday
     volatility) is large relative to any multi-day net directional move,
     regardless of whether the period was actually trending or ranging.
     This makes the metric useless here, not just imperfect.

Both attempts were abandoned rather than shipped, specifically to avoid
picking an arbitrary threshold under time pressure just to make the
strategy fire — see this project's own honesty clause: fixes must not be
chosen because they produce a *result*, only because they're demonstrably
correct.

## What you're being asked to design

A replacement for `is_real_range` (or the whole function, if you think the
per-day-touching-both-extremes concept should be discarded entirely) that:

1. Correctly distinguishes "the market spent the last N days ranging"
   from "the market spent the last N days trending," using **daily OHLC
   bars only** (no access to intraday data, no other indicators computed
   elsewhere unless you specify exactly what to add — `IndicatorSignals`
   in the same codebase has RSI, EMA, ATR-style helpers if you want to
   reference them, but nothing wired into this function today).
2. Works on real gold (XAUUSD) daily bars, where the raw daily high-low
   range is large relative to typical net multi-day price moves (see the
   efficiency-ratio numbers above — this is why that particular metric
   failed).
3. Has thresholds you can justify from first principles / established
   technical-analysis practice (ADX conventions, Bollinger Bandwidth
   percentile logic, Donchian channel containment, Choppiness Index, or
   something else) — **not** thresholds chosen by trying values until
   something fires a "reasonable" number of times on this dataset. If you
   want to reference typical values from the literature for whatever
   method you choose, do so explicitly and say where they come from.
4. Fits this signature (or propose a clean alternative if you think the
   interface itself should change, and say why):
   ```python
   def range_spring_upthrust(
       self,
       daily_bars: list[Bar],
       intraday_bars: list[Bar],
       range_min_days: int = 5,
       range_tolerance_pct: float = 1.5,
   ) -> RangeSpringResult:
   ```
   `Bar` has `.ts, .open, .high, .low, .close, .volume`. This method is a
   pure function — no hidden state, no calls to other detectors required
   (see the module docstring's rationale: a future LLM/JEV orchestrator
   should be able to call this alone).

## What NOT to do

- Don't tune to make this specific 6.5-month gold window "look good" —
  the goal is a correct detector, and whether S04 turns out profitable or
  not afterward is a separate, later question this file isn't asking.
- Don't assume more historical days automatically fixes this — the
  problem is the *shape* of the check, not the sample size (S04 already
  has a comfortable multi-thousand-bar lookback window feeding
  `daily_bars`, unrelated to this bug).
- If you genuinely think no simple daily-OHLC-only method can reliably
  make this distinction, say so plainly and explain what additional
  input (e.g. a volatility indicator, a longer lookback, intraday
  structure) would actually be required — that's a valid and useful
  answer, per this project's own rule against forcing a fix that isn't
  real.

## Where the final answer should land

Whoever implements the recommendation should update:
`research/xauusd_scalping/signals/price_action.py` (`range_spring_upthrust`),
add a regression test in `research/xauusd_scalping/tests/test_signals.py`
(there was no prior test for this function — a real coverage gap, now on
record), rerun `research/xauusd_scalping/run_backtests.py`, and update
`research/xauusd_scalping/03_results.md` and
`docs/status/decisions-and-open-questions.md` (see D27) with the outcome.

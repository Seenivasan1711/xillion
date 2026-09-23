# S11 (video-sourced) — first backtest result and a confirmed encoding bug

**Verdict: no verdict. S11 fires 1 trade in 6.5 months, and the cause is a
structural contradiction in how the video's rules were encoded — not a
finding about whether the strategy works.**

Source and full rule specification:
`05_consolidated_findings_and_strategy_request.md` section 8.1.
Implementation: `strategies/s11_video_liquidity_mtf_scalp.py`.

## The raw result

| Run | n | Win% | PF | Avg R | Total PnL |
|---|---|---|---|---|---|
| S11, real cost | 1 | 0.0 | 0.00 | -1.28 | -$7.00 |
| S11, zero cost | 1 | 0.0 | 0.00 | -1.00 | -$3.20 |

n=1 is not a result. Reporting it only to be explicit that it was run, not
to suggest it means anything either way.

## Where the funnel actually collapses (measured, not assumed)

Instrumented every gate in `on_bar` and counted survivors across 34,871
sampled bars of the real dataset (`s11_funnel.py`):

| Stage | Survivors | Note |
|---|---|---|
| Bars checked | 34,871 | every 5th bar of the full dataset |
| 1H break-of-structure fired | 15,632 | 45% — not a bottleneck |
| + 15m BOS fired, same direction | 8,767 | 25% — **the hard 1H/15m alignment filter is NOT the bottleneck** |
| + 15m order block mitigated (POI touched) | **82** | **0.24% — 99.1% of survivors die here** |
| + a nearby swing found to watch for a sweep | 82 | no loss at this stage |
| → became an actual trade | **1** | a second ~99% collapse, in the sweep/confirmation stage |

**I predicted the hard 1H/15m alignment filter (the implementation's own
flagged "ambiguity #1" — the video treats alignment as a soft preference,
the implementation made it a hard gate) would be the bottleneck. The
measurement says it isn't** — 25% of bars clear alignment fine. Recording
that the prediction was wrong, because the whole point of measuring
instead of assuming is that the measurement gets to win.

## The actual bug: two conditions that can't easily both hold

The POI gate requires, **on the same bar**:
1. `break_of_structure` on the 15m series to be *firing* — meaning the
   most recent 15m bar just closed decisively beyond a swing level, and
2. `order_block_zone(...)` derived from *that same BOS* to be mitigated —
   meaning price is *currently inside* the order block that caused it.

These are close to mutually exclusive by construction. A break of
structure fires precisely because price made a decisive impulsive move
**away** from the order block; at that moment price is, by definition,
far from the zone it just left. Requiring a simultaneous retest of that
zone leaves only the rare wobble cases where a still-forming 15m candle
counts as "fired" while price happens to sit back in the zone — which is
exactly the 82-out-of-8,767 (0.9%) survival rate observed.

The video describes a **sequence over time**, not simultaneous
conditions: structure shifts bullish (a persistent state that stays true
until invalidated) → price *later* pulls back into the zone → *then* a
liquidity sweep → *then* entry. The implementation collapsed that
sequence into one bar's worth of conjunctions.

**This is the third instance of the same bug class in this project**, all
found by tracing rather than by accepting a zero/near-zero signal count
at face value:
- S02: a lookback window too small to ever produce the daily bars its own
  gate required.
- S04: a range check requiring every day to touch both range extremes
  simultaneously.
- S11 (here): a just-fired break of structure required to coincide with a
  retest of the very zone it just broke away from.

Worth naming as a recurring pattern: **whenever a strategy in this project
reports near-zero signals, the prior should be "a condition combination is
structurally unsatisfiable," not "the market didn't offer this setup."**
It has been the former every single time so far.

## What was deliberately NOT done

No threshold was loosened, no gate was relaxed, and no parameter was
tuned to make S11 produce more trades. The fix is a genuine restructure —
persist the bias and the identified zone as state across bars, then wait
for mitigation, then wait for the sweep, as sequential stages — not a
threshold tweak. Doing the tweak instead would manufacture trades without
fixing the encoding, which is precisely the failure mode this project's
honesty clause exists to prevent.

## Status

S11 is **not yet testable**. The implementation needs the sequential
state-machine restructure described above before any backtest of it means
anything. Until then it has no verdict — not "negative," not
"promising" — and it should not be compared against S01-S10's results,
which were at least measuring something real.

The zero-cost and random-entry benchmarks specified for S11 were not run:
with n=1 they'd be meaningless, and they should be run only after the
restructure produces a real sample.

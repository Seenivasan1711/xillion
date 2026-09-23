# The risk/reward geometry bug — and the resulting research plan

**Headline: every strategy in this project has been tested with a ~1:1
risk/reward structure, when the code intended 2:1. This is a mechanical
bug, proven by an exact algebraic identity across 90/90 S11 trades and
~900 trades overall, and it invalidates the framing of every "this
strategy is negative" conclusion reached so far.**

Found 2026-09-24 while investigating how to make S11 profitable. The
investigation found something much more important than an S11 tweak.

## 1. The bug

`signals/risk_floor.py`'s `apply_floor` widens any stop/target to a
minimum "cost-clearing" distance — `min_sl_pts=40`, `min_target_pts=80`,
a deliberate 2:1 structure. It computes both **relative to the reference
price the strategy sees** (`bar.close`).

The engine then fills the order at a **cost-adjusted** price:
`entry_price = bar.close ± entry_cost_pts` (half-spread + slippage,
measured median **23 points** on this dataset).

So for a long:

```
          designed          actual (measured from the real fill)
stop      ref - 40          fill - stop  =  40 + 23  =  63 pts away
target    ref + 80          target - fill = 80 - 23  =  57 pts away
R:R       80/40 = 2.00      57/63          = 0.90
```

The cost markup is **subtracted from the target and added to the stop** —
it damages the trade from both ends simultaneously.

## 2. The proof (not inference — an exact identity)

If the hypothesis is right, then for every trade
`stop_distance + target_distance` must equal exactly `40 + 80 = 120`,
because the `+23` and `−23` cancel. Measured:

| Strategy | n | Median stop | Median target | Actual R:R | Trades where sum == exactly 120.0 |
|---|---|---|---|---|---|
| S01 | 114 | 58.0 | 63.0 | 1.09 | 95/114 |
| S03 | 178 | 58.0 | 62.0 | 1.07 | 170/178 |
| S05 | 174 | 58.0 | 62.0 | 1.07 | **174/174** |
| S06 | 49 | 57.0 | 63.0 | 1.11 | 46/49 |
| S07 | 106 | 63.0 | 62.0 | 0.98 | 92/106 |
| S08 | 109 | 58.0 | 62.0 | 1.07 | 106/109 |
| S09 | 72 | 57.0 | 63.0 | 1.11 | 53/72 |
| S10 | 172 | 58.0 | 62.0 | 1.07 | 169/172 |
| **S11** | **90** | **63.0** | **57.0** | **0.90** | **90/90** |

The trades that *don't* sum to exactly 120 are the ones where the
strategy's own structural levels were already wider than the floor, so
the floor didn't bind — the expected exception, not a contradiction.

## 3. Why this matters enormously

Breakeven win rate is `1 / (1 + R:R)`:

| Structure | Breakeven win rate needed |
|---|---|
| Designed 2.00:1 | **33.3%** |
| Actual 0.90:1 | **52.6%** |

Observed win rates across the project cluster at **26–44%**. Several
strategies comfortably clear 33.3%. **None come close to 52.6%.**

S11 is the cleanest illustration: 35.6% win rate. At the designed 2:1 that
is a *profitable* structure. At the actual 0.9:1 it is hopeless. The
strategy was never being tested on its merits — it was being tested
carrying a structural handicap that no realistic win rate could overcome.

**This also re-frames the C1 zero-cost finding.** With costs zeroed,
`entry_cost = 0`, so the geometry silently reverts to the intended 2:1.
So C1's "6 of 8 have gross edge" was measuring *two* things at once:
removing cost **and** restoring the correct risk/reward geometry. That
conflation was not understood at the time.

## 4. What this does NOT mean — the honest caveat

**Fixing this does not create edge, and it will not automatically make
anything profitable.** Three reasons to be disciplined about it:

1. **Win rate is not independent of target distance.** Widening the true
   target from 57 to 80 points means fewer trades reach it, so win rates
   *will fall*. Any arithmetic that holds win rate constant while
   improving R:R is the classic backtest self-deception. The real effect
   can only be measured by re-running, not projected.
2. **The random-entry baseline was handicapped too — and worse.**
   `random_entry_benchmark.py` resampled (stop, target) distances that
   were *already* measured from cost-adjusted fills, then passed them
   through the same distortion a second time (`ref ± pts`, then fill at
   `ref ± cost`) — giving random trades roughly 86/34, a ~0.4:1
   structure. So the random baseline was *more* crippled than the real
   strategies, meaning C3's comparison flattered the real strategies and
   they *still* only matched it. **C3's "no entry-timing skill"
   conclusion therefore holds a fortiori** — but the comparison must be
   redone cleanly before quoting those numbers again.
3. Cost is still genuinely paid (~$3.80/trade) regardless of geometry.
   Fixing the floor removes a self-inflicted handicap; it does not remove
   the spread.

## 5. The plan

### Phase 1 — Fix the geometry, then re-measure everything (highest priority)

1. **Fix `apply_floor` so the floor is applied to the expected fill, not
   the pre-cost reference.** The cleanest fix is for the engine to apply
   the floor *after* computing the fill price, or for `apply_floor` to
   take the session/vol-bucket entry cost as an argument and pre-compensate
   (`stop = ref − 40 − cost`, `target = ref + 80 + cost`). The second is
   less invasive; the first is more correct. Decide deliberately, and add
   a regression test asserting the realised-from-fill R:R equals the
   designed one.
2. **Fix the same double-distortion in `random_entry_benchmark.py`** so the
   baseline is apples-to-apples.
3. **Re-run all 11 strategies** (real cost, zero cost, random-entry) on
   correct geometry. Every conclusion in `03_results.md`, `03b`, `03c`,
   `03d` is provisional until this is done. Expect win rates to *drop*
   and R to *improve*; the net is genuinely unknown and must not be
   predicted in advance beyond that directional statement.
4. Bundle in the two known-deferred defects while everything is being
   re-run anyway (D28): `VolBucket` dead code, and `BacktestEngine.run()`'s
   O(n²) history copy.

### Phase 2 — Let the data choose the targets (MAE/MFE), instead of assuming 2:1

The 40/80 floor was derived from the cost table, not from where price
actually goes. Every trade log already records `mae_pts` and `mfe_pts`
(maximum adverse and favourable excursion). Analysing those distributions
answers empirically: *how far does price actually travel in our favour
before reversing, and how much heat do winners take first?* That yields a
target/stop pair grounded in observed price behaviour rather than a
round-number assumption — and it is a pure measurement, not a parameter
sweep, so it does not violate the honesty clause. **This has never been
done and is the single cheapest high-value analysis available** — the data
already exists on disk.

### Phase 3 — Make S11 reusable by keeping its skeleton and replacing its brain

S11's entry premise (liquidity sweep after POI mitigation) showed **no
skill versus random**. Tuning it would be curve-fitting. But S11 produced
something genuinely valuable that should be kept and reused:

> **The sequential multi-timeframe state machine** — persistent structural
> bias, a marked zone remembered across bars, and explicit
> IDLE → ARMED → MITIGATED → entry staging with finite lifetimes.

That skeleton is strategy-agnostic. The reusable move is to **keep S11's
state machine and drive it with the one signal that has demonstrated real
skill: S07 (Market Profile Value-Area Rotation)** — the only strategy of
the ten that beat the random-entry benchmark, and the highest gross PF
(1.67). Concretely: use S07's value-area logic to decide *direction and
zone*, and S11's staging to decide *when* — waiting for a genuine pullback
into that zone rather than entering immediately as S07 currently does.

This is a real, falsifiable hypothesis, not a reshuffle: it predicts fewer
trades than S07 alone, with higher expectancy per trade — which is exactly
the direction that helps against a fixed per-trade cost. It must be tested
against **S07 alone** as the control, not against random, since the
question is whether the staging *adds* anything.

### Phase 4 — Use the confidence layer that already exists but gates nothing

`signals/confidence.py` (a weighted 0–100 scorer) is built, tested, and
currently used by **no** strategy to decide anything. This is the natural
home for Rakesh's own stated intent — keep the indicators "for better
confidence-level markup." With per-trade cost fixed and edge thin, taking
*fewer, higher-confidence* trades is one of the few structural levers that
genuinely improves the cost-to-edge ratio. Gate the Phase-3 combination on
a confidence threshold and measure trade count vs. expectancy as the
threshold rises.

### Phase 5 — Only now, the walk-forward

Still never run. But running it *before* Phase 1 would validate results
produced through a broken geometry — wasted effort. Sequence it after the
re-measurement.

## 6. What not to do

- **Do not tune S11's parameters to make it profitable.** Its entries have
  no measured skill; tuning would manufacture a backtest curve with
  nothing underneath it.
- **Do not project profitability from the corrected geometry** using the
  old win rates (see §4.1). Re-run and measure.
- **Do not quote `03_results.md` / `03b` / `03c` / `03d` numbers as final**
  until Phase 1 completes. They are all measurements taken through the
  same distorted lens.

## 7. One-line summary

The research program has not yet answered "do these strategies have an
edge" — it has been answering "do these strategies have an edge while
carrying a systematic 2:1-to-0.9:1 risk/reward handicap," and the answer
to *that* question was always going to be no.

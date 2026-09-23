# P4 Plan — Combine into one system and freeze the rulebook

**This is a plan, not P4's output.** P4 (per `00_build_prompts.md`)
synthesizes a deployable system from P3's validated, out-of-sample,
regime-broken-down results. Those don't exist yet in the form the spec
requires — what exists today (`03_results.md`, v3) is a simpler pooled
check, honestly labeled as such at the time. This document does two
things: (1) says precisely what's missing before P4 can genuinely execute,
and (2) specs out everything P4 itself needs (synthesis framework, router
structure, rulebook template, holdout protocol, expectations methodology)
so that the moment the inputs exist, P4 is a fast mechanical step, not a
fresh design exercise.

## What's actually blocking real P4 execution

Three things, none of which are "more data" anymore — that's solved
(174,554 continuous M1 bars, 2026-03-01→2026-09-16):

1. **The real P3 validation protocol has never been run.** The spec calls
   for: a sealed 60/20/20 train/validation/holdout split, anchored
   walk-forward (6mo train / 1mo test, rolling, out-of-sample only),
   parameter-sensitivity heatmaps (reject lone spikes, require neighboring
   configs retain ≥70% expectancy), and 5,000-shuffle Monte Carlo bands.
   What's been run instead, three times (v1/v2/v3), is a single pooled
   backtest over the entire dataset plus a crude march-vs-sept subset
   check — explicitly flagged as not a substitute for the real protocol
   each time in `03_results.md`. This is a real engineering gap, not
   just a formality — a pooled backtest can't produce the by-session/
   by-regime breakdown the spec calls "the most valuable output... what
   P4 builds on," and can't distinguish a real edge from one that only
   worked in-sample.
2. **The by-regime breakdown doesn't exist.** `Trade` (in
   `engine/backtest_engine.py`) records `session` already, so the
   by-session breakdown `run_backtests.py` produces is real. It does
   **not** record an ATR-percentile tercile or an ADX trend/range tag at
   entry time — `IndicatorSignals.adx()` exists but nothing calls it
   per-trade today. Needed before the regime router (see below) can be
   built from data instead of guesswork.
3. **S04 and S02 are still unresolved** (see
   `S04_range_detection_design_question.md`, pending a second LLM's
   design opinion, and the tracker's S02 note on the still-needed
   incremental trace). Until both are resolved, "all 10 candidates" isn't
   a complete set to run the real protocol against.

**Honest expectation-setting, per the honesty clause**: 8 of 10 candidates
are already net-negative on a full 6.5-month pooled sample with credible
trade counts (72-178 trades). It would be a real surprise if a stricter
walk-forward+holdout protocol turned any of those 8 positive — pooled and
walk-forward results diverging that dramatically would itself be a red
flag worth investigating, not a reason to expect a different answer. But
"likely" isn't "confirmed" — none of the 8 should be dropped from the real
protocol without actually running it. The pragmatic sequencing below
reflects the likely outcome without skipping the verification.

## Recommended sequencing (cheapest checks first)

1. Get S04's design-question answer back, implement it, rerun the pooled
   check (fast, ~15-40 min) — does it produce trades at all, and if so, is
   the win rate/PF even in the realistic range (per the spec's own "no
   published intraday gold system sustains 60%@2.5R" table), or is it
   another artifact worth tracing before investing further?
2. Finish S02's incremental trace (mimicking its actual pending-sweep
   state machine) to close out whether its zero signals are genuine
   rarity or a second hidden bug.
3. **Decision point, not yet reachable**: if neither S04 nor S02 shows a
   pooled result meaningfully different from the other 8 (i.e., still
   flat/negative or effectively never fires), the honest conclusion is
   that none of the 10 candidates have a pooled-detectable edge at all —
   in which case building the full walk-forward+holdout+regime harness
   (a real, multi-day engineering investment) should be re-scoped with
   Rakesh before building it, rather than built on spec by default. If
   either shows a genuinely promising pooled result, that's the trigger
   to build the real protocol for real, on the full 10-strategy set (not
   just the promising one — the spec's parameter-sensitivity and
   walk-forward steps exist precisely to catch a promising pooled result
   that doesn't survive proper out-of-sample testing).

## Synthesis framework (spec'd now, executed once inputs exist)

Per `00_build_prompts.md`'s P4 prompt, verbatim structure:

### 1. Correlation
Pairwise correlation of each qualifying strategy's daily-return series
(from the per-trade PnL, resampled to daily), plus trade-timestamp overlap
count. Strategies with correlation above some threshold (e.g. >0.7) and
heavy timestamp overlap are redundant — keep the better performer, not
both. **Needs**: a trade-log-to-daily-return-series helper (doesn't exist
yet; straightforward given `Trade.entry_ts`/`pnl_usd`).

### 2. Regime router
A literal table: rows = (session × ATR-percentile-tercile ×
trend-or-range-by-ADX), columns = which sub-strategy is active in that
cell, or `NO_TRADE`. Every cell filled from the by-regime breakdown data
(once it exists — see gap #2 above), never from intuition, per the
spec's own instruction. `NO_TRADE` should be the common answer if the
data doesn't support activating anything in a given cell — the spec
explicitly warns against filling every cell just to have a router.

Sessions: `asia`, `london`, `london_ny_overlap`, `ny`, `dead_zone`
(already how `cost_model.py`'s `Session` enum is defined — reuse it, don't
invent a second taxonomy). ATR terciles and trend/range-by-ADX: computed
per bar at entry time once the regime-tagging gap above is closed.

### 3. Shared filters
Once ≥2 strategies qualify, check which pre-trade filters (news blackout,
minimum M5 range, max spread, time-of-day cutoff) improved *every*
qualifying strategy's out-of-sample numbers when applied individually —
lift only those into one shared gate. A filter that helps one strategy and
hurts another stays strategy-specific, not shared.

### 4. Shared exit logic
A/B test, out-of-sample: fixed R-target vs. partial-at-1R-plus-trail,
across whichever strategies qualify. Picked by expectancy, not preference,
per the spec. Only standardize if the data actually favors one scheme
across the board; otherwise leave per-strategy exits as-is and say so.

### 5. Risk layer
Already largely implemented, not just planned — `run_backtests.py`'s
`make_engine()` already encodes the FundingPips 1-Step Flex $5k rules as
hard `RiskLimits`: `max_trades_per_session=4`, `daily_loss_cap_usd=50`,
`consecutive_loss_halt=2`. P4 just needs to confirm these carry through
into `RULEBOOK-v1.md` unchanged, not re-derive them.

## Holdout protocol (unchanged from spec, restated for the record)

Freeze every parameter of the combined system in writing **before**
touching the sealed 20% holdout. Run it exactly once. If it disappoints,
report the validation-vs-holdout gap as the honest overfitting estimate —
do not retune and re-run. This is a one-shot check; the plan for getting
here needs to be right before it's used, which is the point of everything
above.

## Expectations output (needs a new script — not built yet)

A holdout-trades → distribution simulator, not built yet, scoped here so
it's fast to build when needed:
- **Input**: the holdout period's trade list (from whichever strategy/
  combination qualifies) at a chosen lot size.
- **Output**: Monte Carlo over those trades — 5th/25th/50th/75th/95th
  percentile of daily P&L, monthly P&L, and max drawdown. Separately, a
  10,000-path account simulation applying the actual FundingPips 1-Step
  Flex rules (12% target, $50/day cap, 4 trades/session cap, 2-loss halt)
  to estimate probability of hitting the target before a breach, and
  probability of a losing month.
- **The lot-size check the spec calls out explicitly**: solve for the lot
  size that gives a median $40/day, then check whether that same lot size
  breaches the $50 daily cap at the 95th-percentile bad day. If it does,
  the deliverable states plainly that the target isn't reachable at this
  account size, and reports what is — per the spec's own worked-out
  concern about the $30-60/day target colliding with the $50 cap at
  realistic expectancy (see `00_build_prompts.md`'s "Before you run these"
  table).

## RULEBOOK-v1.md skeleton (ready to fill in, not written yet)

```
# RULEBOOK-v1.md

## Preconditions checklist
(what must be true before any trade is even considered)

## Regime router
(the literal table from Synthesis step 2)

## Entry / stop / target / management rules
(every number explicit, per qualifying strategy or per shared rule)

## Sizing formula
(prop-firm constraints inline: FundingPips 1-Step Flex $5k)

## Hard stop conditions
(daily cap, trade cap, news blackout, spread blowout)

## Kill switch
(the specific live metrics meaning the edge has decayed --
 e.g. rolling 30-trade expectancy below X, win rate outside
 the MC 5th-percentile band, realised slippage above modelled by Y%)

## Known failure modes
```

## What "P4 done" actually looks like

Either: a frozen `RULEBOOK-v1.md` with a holdout run behind it and an
honest validation-vs-holdout gap reported — or, if zero strategies clear
the real validation protocol, a clear written statement that no viable
combination exists yet, which assumption is most likely killing the edge
(per the spec's own encouragement to name it: spread, trade frequency, or
stop distance), and what would need to change for a future attempt. Both
are valid, honest P4 outcomes — forcing a rulebook out of results that
don't support one is not.

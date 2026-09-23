# Can leverage make this profitable? No — and here is the arithmetic

> **⚠️ 2026-09-24 CORRECTION — read `10_unit_bug_and_corrected_rerun.md` first.**
> A 100x points-vs-price unit bug in the research engine inflated every
> modelled cost 100x (a $0.30 spread was applied as $30). **The cost/risk
> numbers below (110% etc.) are void.** The general arithmetic — leverage
> scales a negative expectancy, it never fixes one — still holds.


**Asked 2026-09-24, while a real FundingPips 2-Step Flex $5k evaluation
(#20635994) is Ongoing in Phase 1.** Recorded permanently because it is
one of the most expensive misconceptions in retail trading, and because a
future session (or a future LLM asked to "just add leverage") needs to hit
this wall immediately rather than re-derive it.

## The short version

**Leverage is a multiplier, not a generator.** It scales position size, and
profit and loss scale linearly with position size. Multiplying a negative
expectancy by a bigger number produces a bigger negative number. There is
no size at which a losing system becomes a winning one.

## S11's real trades, scaled

Actual measured result: 112 trades, **-$528.98** at 0.08 lots, max
drawdown 10.58%. Scaling the same trades:

| Lots | Multiple | Total P&L | Per trade | Max DD | Outcome on the $5k account |
|---|---|---|---|---|---|
| 0.08 | 1x | -$528.98 | -$4.72 | 10.6% | breaches typical daily limits → **failed** |
| 0.16 | 2x | -$1,057.96 | -$9.45 | 21.2% | breaches the 12% total drawdown → **failed** |
| 0.40 | 5x | -$2,644.90 | -$23.62 | 52.9% | breaches the 12% total drawdown → **failed** |
| 0.80 | 10x | -$5,289.80 | -$47.23 | 105.8% | **account wiped out** |
| 1.60 | 20x | -$10,579.60 | -$94.46 | 211.6% | **account wiped out** |

More leverage does not move toward profit. It moves toward zero, faster.

## Why it cannot work — the ratio is scale-invariant

The thing killing these strategies is the ratio of **cost to risk budget**.
Every component of cost scales linearly with position size, and so does the
risk budget. The ratio is therefore *identical at every size*:

| Position | Round-trip cost | Risk budget (40pt stop) | Cost as % of risk |
|---|---|---|---|
| 0.08 lots | $3.52 | $3.20 | **110%** |
| 0.80 lots (10x) | $35.20 | $32.00 | **110%** |

Spread, slippage and commission are all per-lot. Leverage multiplies both
the numerator and the denominator. **It cannot change a ratio it scales on
both sides.**

## Leverage actively makes the prop-firm constraint worse

There is a second, sharper problem specific to a funded-account structure.
The **$50 daily loss cap is a fixed dollar amount** — it does *not* scale
with position size. So bigger positions hit it sooner:

- At 0.08 lots a 40-point stop loses $3.20 → ~15 losses before the cap
- At 0.80 lots the same stop loses $32.00 → **2 losses before the cap**

So leverage shrinks the number of trades you're allowed to take before
being halted, which destroys sample size and any chance of an edge
expressing itself. This is the same collision the scale sweep found
independently (trade count collapsing 112→29→6→3→0 as stops widened), and
the same one the original build spec predicted.

## The one thing leverage IS for

Leverage is the **last** step, applied to a system that already has
positive expectancy, to size it appropriately for the account and the
drawdown tolerance. It amplifies whatever expectancy exists — positive or
negative, without preference.

The correct sequence is always:

1. Establish positive expectancy, out-of-sample, after real costs.
2. *Then* choose position size for the drawdown you can tolerate.

Doing step 2 first, hoping it substitutes for step 1, is the single most
reliable way to lose an account quickly rather than slowly.

## Practical warning for the live evaluation

A real FundingPips 2-Step Flex $5k evaluation (#20635994) is currently
Ongoing in Phase 1. **None of the eleven strategies in this repo should be
run on it**, at any lot size. Their measured expectancy is negative before
costs are even applied (see `07_conclusion_m1_scalping_verdict.md`,
Finding 1: 31.1% win rate where a coin flip needs 33.3%), and the table
above shows what position sizing does to that — the only thing leverage
changes is how fast the evaluation fails.

The honest state of this research: **no strategy here is ready for a
funded account, and none is close.** That is the finding, and it is worth
more than a strategy that looks good in a backtest and discovers this with
real money.

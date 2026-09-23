# Verdict: M1 XAUUSD scalping, as specified, does not work — and why

**Date: 2026-09-24. This closes the P1-P3 research question.** Two
independent, separately-fatal findings, both now measured rather than
assumed. Neither is fixable by choosing a better entry signal.

---

## Finding 1 — the signals carry no directional information

The decisive test walks forward bar by bar from each of S11's 223 signals
and asks which level price touches **first** (pessimistic on same-bar, the
same rule the engine uses). This measures the raw predictive content of a
setup, **before any costs at all**:

| Stop/Target | Horizon | Target first | Stop first | Win rate | Breakeven needed | Verdict |
|---|---|---|---|---|---|---|
| 40/80 (2:1) | 24h | 59 | 131 | **31.1%** | 33.3% | below |
| 40/40 (1:1) | 24h | 101 | 116 | **46.5%** | 50.0% | below |
| 20/40 (2:1) | 24h | 66 | 157 | **29.6%** | 33.3% | below |
| 100/200 (2:1) | 24h | 10 | 40 | **20.0%** | 33.3% | far below |

**At every geometry tested, the signal is at or below the breakeven a coin
flip would produce — with costs set aside entirely.** A random entry at
2:1 yields ~33.3%; S11 yields 31.1%. That is not an edge being eroded by
friction. It is the absence of an edge, and it independently confirms the
random-entry benchmark's earlier verdict (`03b`) by a completely different
method.

The same applied to the other ten when measured on the old geometry:
exactly one (S07) beat a matched random baseline and one (S05) was worse
than random. **That ranking is now void** — see the Update below; those
comparisons were made through the broken geometry and are being re-run.

## Finding 2 — the spread is larger than the move being traded

The spread table was the last unvalidated input in the whole project.
`cost_model.py` labelled it *"a PESSIMISTIC ASSUMPTION, not measured from a
real broker feed."* It has now been read off a live MT5 terminal:

> **XAUUSD — Bid 4284.50 / Ask 4284.81 → spread = 31 points**, at 22:27
> server time (≈19:27–20:27 UTC, i.e. the NY session).

Against the assumed table for that session:

| Session | Assumed | Measured | Ratio |
|---|---|---|---|
| **ny** (the session sampled) | 30.0 | **31** | **1.03x** |

**The assumption was accurate, not pessimistic.** The structural conclusion
it supported therefore stands rather than being overturned:

- Round-trip cost at 31 points = 18.5 (entry) + 20.5 (exit) = **39 points**
- Against the 40-point risk budget the floor guarantees: **98%**

And set against how far price actually travels after a signal (measured
over 223 signals):

| Median favourable move | Spread as a multiple of it |
|---|---|
| 8 points (1 hour) | **3.9x** |
| 15 points (4 hours) | 2.1x |
| 46 points (24 hours) | 0.7x |

**In the hour after a signal, the typical favourable move is 8 points and
the spread is 31.** The cost of entering is roughly four times the move
being harvested. No entry logic, however good, survives that — and the
only horizon where the move finally exceeds the spread is 24 hours, which
is not scalping.

## Why these two findings are independent — and why that matters

They fail for different reasons, so fixing either one alone changes
nothing:

- If the spread were zero, S11 would still lose, because its win rate
  (31.1%) sits below the 33.3% a coin flip needs at 2:1.
- If the signal were genuinely predictive, it would still lose at M1,
  because costs consume 98% of the risk budget and exceed the typical
  move by ~4x.

This is why the earlier "make it profitable" avenues all dead-ended, and
in hindsight each dead-end was the same finding seen from a different
angle:
- Coarser timeframe (M5/M15), same code → didn't help (`03c`).
- Bigger stop/target scale → profit factor rose exactly as the cost
  arithmetic requires, but the trade count collapsed into the $50 daily
  loss cap (112→29→6→3→0) and the gap over random never opened.
- Fixing the R:R geometry → made results *worse*, by revealing that the
  old 35.6% win rate came from a 57-point target that was easy to reach
  but too small to clear costs.

## What would actually have to change

Not a better signal. One of these structural inputs:

1. **A much slower timeframe**, where the move is large relative to a
   fixed ~39-point round-trip cost. The 24-hour median move (46 points)
   finally exceeds the spread — but that is swing trading, and
   **swap is -93.17 points per night on longs** (shorts earn 21.68), which
   claws back most of that on the long side. Any move in this direction
   must model swap, which the harness currently does not.
2. **Materially tighter spreads** — a different broker or instrument.
   31 points is normal retail gold, so this likely means a different
   instrument rather than a better gold broker.
3. **A genuinely predictive signal** — but eleven were tested against a
   random baseline and ten failed, so this is not a matter of trying an
   twelfth variant of the same family.

## Caveat, stated plainly

The spread reading is **one sample, from a MetaQuotes demo account**, in
the NY session. It closely matches the assumed value for that session,
which is meaningful corroboration, but it is not a full distribution:
- It does not capture Asia/dead-zone (assumed 40/60), where the assumption
  may still be wrong in either direction.
- It does not capture volatility spikes, when spreads widen most.
- A live FundingPips account may quote differently from a MetaQuotes demo.

None of that changes Finding 1, which is cost-independent. It would only
move the magnitude of Finding 2, not its direction — and Finding 1 alone
is sufficient to stop pursuing these eleven strategies.

## Update (same day): S07's credential did not survive the geometry fix

The verdict above named S07 as "the one strategy that beat random" and the
only candidate worth further work. **Re-running all ten on corrected
geometry retracts that.** S07 collapsed harder than any other strategy —
win rate 44.3% → **10.2%**, PF 0.33 → **0.05**, among the worst of the
eleven. Its "beats random" result came from a benchmark run on the broken
geometry, so it is void until re-measured, and the random-entry benchmark
is being re-run on the fixed engine.

This strengthens rather than weakens the verdict. It was never "ten bad
strategies and one promising one" — the apparent spread between strategies
was substantially an artifact of the same geometry bug. On corrected
geometry they are uniformly poor, which is exactly what Finding 1 (no
directional information) and Finding 2 (spread exceeds the move) predict
when taken together.

**Standing lesson recorded in `08_correction_history.md` #16: when a fix
lands in shared machinery, every ranking derived from the old machinery is
void, not merely suspect.**

## Update 2 (same day): the random-entry benchmark on corrected geometry — no strategy beats random

The benchmark (`random_entry_benchmark.py`, 500 matched random runs per
strategy, same sessions/stops/targets as each real trade) was re-run on the
fixed engine. Full table in `03b_random_entry_benchmark.md`.

| Strategy | n | Real P&L | Random p5 / p50 / p95 | Verdict |
|---|---|---|---|---|
| S01 | 144 | -$716.29 | -$616 / -$514 / -$404 | **worse than random** |
| S02 | 0 | — | — | no trades, untestable |
| S03 | 245 | -$1,374.61 | -$1,040 / -$908 / -$781 | **worse than random** |
| S04 | 3 | +$1.93 | -$21 / -$13 / +$20 | indistinguishable (n=3, meaningless) |
| S05 | 238 | -$1,304.10 | -$1,016 / -$879 / -$745 | **worse than random** |
| S06 | 56 | -$194.87 | -$260 / -$198 / -$135 | indistinguishable |
| S07 | 128 | -$724.54 | -$574 / -$476 / -$373 | **worse than random** |
| S08 | 159 | -$892.41 | -$712 / -$594 / -$482 | **worse than random** |
| S09 | 86 | -$365.10 | -$398 / -$298 / -$205 | indistinguishable |
| S10 | 237 | -$1,264.62 | -$1,002 / -$873 / -$740 | **worse than random** |

**Zero of ten beat random. Six are below the random 5th percentile** — their
entries are systematically *worse* than chance, not merely uninformative.
S07, the former "one candidate," is among them. This closes the last open
question on M1: there is no strategy here with a credential to build on,
and no walk-forward is worth running.

## Recommendation

**Stop signal-hunting at M1 on XAUUSD.** The question "which of these
strategies has an edge" has been answered: none of them do, by two
independent measurements. Continuing to test variants of the same idea at
the same timeframe would be motion, not progress.

The genuinely open questions, if this track continues:
- ~~Does ANY strategy still beat a random baseline on corrected geometry?~~
  **Answered 2026-09-24: no** — see "Update 2" above. None of the nine
  testable strategies beats random; six are worse than it.
- Does the same toolkit applied at H1/H4 (with swap modelled) show
  anything? At the 24h horizon the median move (46pts) finally exceeds the
  39pt round-trip cost — the only horizon where the arithmetic opens up at
  all. That is a different question, not a continuation of this one, and it
  requires modelling swap (-93.17 pts/night on longs) which the harness
  does not do yet.

**What was built here retains value regardless**: a tested event-driven
backtest harness with a realistic cost model, a composable signal toolkit,
a random-entry benchmark, and — most usefully — a set of hard-won
methodological lessons recorded in the docs, including the standing prior
that a near-zero signal count has meant "structurally unsatisfiable
conditions" three times out of three in this codebase, never "the market
didn't offer this setup."

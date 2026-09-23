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

The same applies to the other ten: of eleven strategies, exactly one (S07)
beat a matched random baseline, and one (S05) was measurably worse than
random.

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

## Recommendation

**Stop signal-hunting at M1 on XAUUSD.** The question "which of these
strategies has an edge" has been answered: none of them do, by two
independent measurements. Continuing to test variants of the same idea at
the same timeframe would be motion, not progress.

The genuinely open questions, if this track continues:
- Does S07 — the one strategy that beat random — survive an honest
  walk-forward? It is the only candidate with any evidence behind it.
- Does the same toolkit applied at H1/H4 (with swap modelled) show
  anything? That is a different question, not a continuation of this one.

**What was built here retains value regardless**: a tested event-driven
backtest harness with a realistic cost model, a composable signal toolkit,
a random-entry benchmark, and — most usefully — a set of hard-won
methodological lessons recorded in the docs, including the standing prior
that a near-zero signal count has meant "structurally unsatisfiable
conditions" three times out of three in this codebase, never "the market
didn't offer this setup."

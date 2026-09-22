# XAUUSD Scalping — 5 Build Prompts

> Pasted verbatim by Rakesh, 2026-09-22, as the spec driving this entire
> research track. Kept here as the canonical reference every later
> deliverable (`01_shortlist.md`, `01_shortlist_v2.md`, `02_harness.md`,
> `03_results.md`, `RULEBOOK-v1.md`, the P5 alert service) is built
> against — if a later file's interpretation of a rule is ambiguous,
> this is the source of truth to re-check against, not memory of it.

| # | Stage | Consumes | Produces | Run in |
|---|---|---|---|---|
| P1 | Strategy landscape sweep | nothing | `01_shortlist.md` — 5 ranked, fully-specified strategies | standalone |
| P2 | Data + backtest harness | nothing | `/data`, `engine/`, passing unit tests | pipeline 1 |
| P3 | Implement + walk-forward test all 5 | P1 + P2 | `03_results.md` + per-strategy metrics | pipeline 2 |
| P4 | Combine into one system | P3 | `RULEBOOK-v1.md` (frozen) | pipeline 3 |
| P5 | Live alert service | P4 | Telegram bot + parity test | standalone |

P2 can run in parallel with P1. P5 needs only the rulebook.

---

## P1 — Strategy landscape sweep

```
You are a quantitative research analyst specialising in intraday precious-metals
microstructure. I am a software engineer, not a discretionary trader. I need rules,
not intuition.

<objective>
Produce a ranked shortlist of exactly 5 XAUUSD scalping strategies that can be
implemented as deterministic code and backtested with free data.
</objective>

<hard_constraints>
- Instrument: XAUUSD spot only. Timeframes M1 and M5 for entries, M15/M30/H1 for bias.
- Every rule must be computable from OHLCV + timestamp alone. No order flow, no L2
  depth, no tick-volume-derived "real volume", no broker-specific data.
- No paid data feeds, no paid indicators, no paid platforms. No GPU, no deep learning.
- Must produce 2-8 signals per trading day. Fewer is untestable; more is eaten by cost.
- Every parameter must have a concrete numeric default AND a sensible search range.
  "A significant level" is not a rule. "Swing high with >=2 bars on each side, tested
  >=2 times within the last 120 M1 bars" is a rule.
</hard_constraints>

<method>
1. Search widely: academic papers on intraday mean reversion and momentum in gold,
   quant blogs, open-source backtest repos, prop-firm and futures-desk literature,
   TradingView open-source Pine scripts with published statistics, and forum threads
   with attached backtest reports. Aim for 15-20 candidates before narrowing.
2. For each candidate, classify the EVIDENCE TIER:
   T1 = peer-reviewed or reproducible public backtest with code and data
   T2 = credible practitioner writeup with stated sample size and costs
   T3 = claim with no verifiable numbers (marketing, course-selling, guru content)
   Explicitly flag T3. Do not let T3 into the top 5 unless the mechanism is sound and
   you say so.
3. Score each candidate 1-5 on: edge plausibility (does the mechanism have a reason to
   exist?), codeability, signal frequency, robustness to spread/slippage, and
   independence from the other candidates. Weight: 30/20/15/20/15.
4. Reject anything that only works because of a specific broker, a specific year, or a
   parameter set with no neighbourhood of similar performance.
</method>

<deliverable>
Write /01_shortlist.md containing:
- A comparison table of all candidates you evaluated, with scores and evidence tier.
- For each of the top 5, a SPEC CARD:
    Name / one-line mechanism (why the edge exists in plain English)
    Market regime it needs (trending, ranging, high-vol, session-specific)
    Entry rule as numbered pseudocode with every threshold named and defaulted
    Stop rule, target rule, and any scale-out / breakeven / trail logic
    Invalidation: conditions under which the setup is void
    Parameter table: name, default, search range, why that range
    Expected failure mode: what kind of market kills it
    Evidence tier and source links
- A short section: "Mechanisms I rejected and why" (3-5 lines each).
</deliverable>

<anti_patterns>
Do not hedge with "consider", "you might", "depending on conditions". Every rule is
binary and testable. Do not invent statistics; if a source gives no numbers, say so.
Do not produce 5 variants of the same idea — the 5 must be mechanically different, and
you must argue why their signals will not be correlated.
</anti_patterns>

Think hard before writing. Show your ranking reasoning before the final table.
```

---

## P2 — Data + backtest harness

```
You are a quant developer. Build the testing infrastructure for an XAUUSD scalping
research project. Do NOT implement any trading strategy in this task — the harness must
be strategy-agnostic and proven correct before any strategy touches it.

<part_1_data>
Acquire >=3 years of XAUUSD M1 OHLC data using free sources. Evaluate and pick:
  - dukascopy-node / duka-data (tick -> aggregated bars, no API key)
  - HistData.com M1 CSV archives
  - MetaTrader5 python package export, if an MT5 terminal is reachable
  - TwelveData / Polygon free tiers as a cross-check source only
Store as partitioned parquet in /data/xauusd/. Write the downloader as a resumable
script, not a one-off.

Then write /data/QUALITY.md reporting:
  - Bar count per month; missing-bar gaps ranked by size
  - Weekend and rollover handling; how you tag session boundaries
  - DST handling — broker server time vs UTC vs IST (Asia/Calcutta). State the
    canonical internal timezone and convert everything to it exactly once.
  - Session tags per bar: Asia / London / London-NY overlap / NY / dead zone
  - A cross-source spot check: sample 200 random bars against a second source and
    report the max OHLC discrepancy.
</part_1_data>

<part_2_cost_model>
Costs are the whole game at this timeframe. Build a cost model, not a constant:
  - Spread by session and by volatility bucket, in price points. Default to a
    pessimistic table if you cannot measure it; state the assumptions in code comments.
  - Commission: $3.50 per lot per side (parameterise it).
  - Slippage: entry and stop-out slippage as separate parameters, worse for market
    orders during high-impact windows.
Expose all of it as a single CostModel object the engine takes as a dependency.
</part_2_cost_model>

<part_3_engine>
Build an event-driven backtester (or a thin, audited wrapper over backtesting.py /
vectorbt — justify the choice). It MUST support:
  - Bar-by-bar iteration with no lookahead. A strategy sees only closed bars.
  - Intrabar SL/TP resolution with the PESSIMISTIC rule: if a single bar's range
    contains both the stop and the target, record the STOP as hit. Make this a flag and
    default it to pessimistic. Report how many trades were ambiguous.
  - Partial close at a given R multiple, stop-to-breakeven, and M5-close-based trailing
    (trail to prior M5 candle extreme +/- a buffer; stop never moves backwards).
  - Session filters, max-trades-per-session cap, daily loss cap that halts trading,
    consecutive-loss halt.
  - A news blackout window driven by a free economic calendar dump (high-impact USD
    events, +/- configurable minutes).
  - Position sizing by fixed lot and by fixed fractional risk, both.
  - Per-trade logging: timestamp, side, entry, exit, reason, MAE, MFE, R multiple,
    spread paid, commission, session, bars held.
</part_3_engine>

<part_4_proof>
Write unit tests using SYNTHETIC price series with known analytic answers:
  - A strategy that always longs a deterministic staircase must return exactly the
    arithmetic P&L you can compute by hand.
  - A bar that gaps through the stop must fill at the gap, not at the stop price.
  - A strategy that references bar[i+1] must fail a lookahead-detection test.
  - Zero-cost run vs costed run must differ by exactly the modelled cost.
Do not report the harness as done until every test passes and you show the output.
</part_4_proof>

<deliverable>
Working code under /engine and /data, a green test run pasted into your final message,
and /02_harness.md documenting the API a strategy module must implement — because the
next task will write five modules against it.
</deliverable>
```

---

## P3 — Implement the 5 and walk-forward test them

```
You have /01_shortlist.md (five strategy spec cards) and a proven harness documented in
/02_harness.md. Implement and honestly evaluate all five.

<implementation>
One module per strategy under /strategies/, all implementing the harness interface
exactly. Each module exposes its parameter grid declaratively. No strategy may read any
data the harness does not hand it. Re-read each spec card before coding and list any
ambiguity you had to resolve — do not silently invent a rule.
</implementation>

<validation_protocol>
This is the part that decides whether the result is real. Follow it literally.

1. SPLIT: oldest 60% = in-sample train. Next 20% = validation. Most recent 20% = holdout.
   The holdout is SEALED. You may not look at holdout results until task P4.
2. WALK-FORWARD: anchored walk-forward on train+validation. 6-month train window,
   1-month test window, rolling. Report only the stitched out-of-sample test results.
   The in-sample numbers are diagnostics, never the headline.
3. PARAMETER SENSITIVITY: for the best config of each strategy, produce a heatmap over
   the two most important parameters. REJECT any config that is a lone spike — require
   that neighbouring parameter values retain >=70% of the expectancy. A sharp peak is
   overfitting, not an edge.
4. SAMPLE SIZE: any strategy with <200 out-of-sample trades is marked UNDERPOWERED and
   its metrics are reported with that label attached.
5. MONTE CARLO: shuffle trade order 5,000 times; report the 5th/50th/95th percentile of
   max drawdown and of monthly return. A single equity curve is not evidence.
</validation_protocol>

<metrics>
For each strategy, out-of-sample, in a single comparison table:
expectancy in R | win rate | profit factor | avg win R | avg loss R | trades/day |
avg bars held | max DD % | MC 95th-pct DD % | Sharpe | Sortino | % of gross profit
eaten by costs | longest losing streak

Then break each strategy down BY SESSION (Asia / London / overlap / NY) and BY REGIME
(ATR percentile terciles, and trend vs range by ADX). This breakdown is the most
valuable output of the task — it is what P4 builds on.

Also emit, per strategy, the trade-by-trade CSV and a returns series aligned on
timestamp, so the next task can compute cross-strategy correlation.
</metrics>

<honesty_clause>
My stated goal is $30-60/day on a $5,000 account. Do NOT tune toward that number. If a
strategy's honest out-of-sample expectancy is negative, report it as negative and keep
it in the table. If all five are negative after costs, say so plainly and tell me which
assumption (spread, trade frequency, stop distance) is doing the killing. A truthful
"this does not work" is the most useful result you can give me.
</honesty_clause>

<deliverable>
/03_results.md with the tables above, the sensitivity heatmaps, the Monte Carlo bands,
and a ranked verdict paragraph per strategy: keep / keep-with-caveats / discard, with
the reason. State explicitly that the holdout remains untouched.
</deliverable>
```

---

## P4 — Combine into one strategy and freeze the rulebook

```
Using /03_results.md and the per-strategy trade logs, synthesise ONE deployable
scalping system, then validate it once on the sealed holdout.

<synthesis>
1. CORRELATION: compute the pairwise correlation of the five daily-return series and
   the overlap in trade timestamps. Identify which strategies are genuinely additive.
2. REGIME ROUTING: using the by-session and by-regime breakdown, build an explicit
   router — a decision table mapping (session x volatility bucket x trend/range state)
   to at most one active sub-strategy, or to NO TRADE. Every cell must be filled, and
   "no trade" must be a common answer. Justify each cell from the P3 data, not intuition.
3. SHARED FILTERS: lift the filters that improved every sub-strategy into a single
   pre-trade gate (news blackout, minimum M5 range, maximum spread, time-of-day cutoff).
4. SHARED EXIT LOGIC: standardise one exit scheme across the system unless the data
   shows a sub-strategy genuinely needs its own. Test: fixed R target vs partial-at-1R
   plus trail. Pick by out-of-sample expectancy, not by preference.
5. RISK LAYER: encode the account rules as hard constraints, not suggestions —
   FundingPips 1-Step Flex ($5k, 12% target, no consistency rule), max $50 loss per day,
   max 4 trades per session, halt for the day after 2 losses.
</synthesis>

<holdout_protocol>
Freeze the combined system completely — every parameter, every threshold — and write it
down BEFORE running the holdout. Then run the sealed 20% holdout exactly ONCE.
If the holdout result disappoints, you may NOT go back and retune; you report the gap
between validation and holdout, because that gap is the honest estimate of how much
overfitting survived. Say so explicitly in the output.
</holdout_protocol>

<expectations_output>
Do not give me a point estimate of daily profit. Give me a distribution:
  - Monte Carlo over the holdout trades: 5th / 25th / 50th / 75th / 95th percentile of
    daily P&L, monthly P&L, and max drawdown, at the chosen lot size.
  - Probability of a losing month. Probability of hitting the 12% target before a
    breach, simulated over 10,000 account paths with the prop-firm rules applied.
  - The lot size required for a median $40/day, and whether that lot size breaches the
    daily loss cap at the 95th-percentile bad day. If it does, say the target is not
    reachable at this account size and tell me what is.
</expectations_output>

<deliverable>
/RULEBOOK-v1.md — a frozen, versioned, machine-readable spec:
  - Preconditions checklist (what must be true before any trade)
  - The regime router as a literal table
  - Entry / stop / target / management rules, every number explicit
  - Sizing formula with the prop-firm constraints inline
  - Hard stop conditions (daily cap, trade cap, news, spread blowout)
  - KILL SWITCH: the specific live metrics that mean the edge has decayed and trading
    must stop (e.g. rolling 30-trade expectancy below X, win rate outside the MC 5th
    percentile band, realised slippage above modelled by Y%)
  - A "known failure modes" section
Written so that P5 can implement it with zero interpretation. Anywhere a human would
have to make a judgement call, that is a bug — go back and make it numeric.
</deliverable>
```

---

## P5 — Live alert service

```
Implement a signal-alerting service that executes /RULEBOOK-v1.md in real time and sends
me alerts. It must NOT place orders — alerts only.

<architecture>
- Price source: MetaTrader5 python package against my terminal if reachable; otherwise a
  free websocket/REST quote feed with a documented fallback. Poll or stream, but
  evaluate rules ONLY on closed bars — never on a forming candle.
- Rule engine: import the same strategy modules the backtest used. Do not reimplement
  the logic. Any duplicated rule is a future divergence bug.
- Alert channel: Telegram bot (free). Alert payload must be the full setup card:
    direction | entry | stop | target(s) | lot size | R:R | $risk | $target
    the regime cell that fired | the confirmation condition still outstanding, if any
    the invalidation price | a one-line reason
- Also send a NO-TRADE heartbeat at each session open stating why nothing qualifies,
  and a daily summary at session close.
- Log every evaluation (fired or not) to CSV with the reason, so misses are auditable.
</architecture>

<correctness_requirements>
1. PARITY TEST — the acceptance criterion. Replay the last 60 days of data through the
   live code path in simulated-real-time and diff the resulting signal list against the
   backtest's signal list for the same window. They must match 100%. Any mismatch is a
   bug in one of them; find it and report which. Do not ship without this diff passing.
2. Timezone: my local time is Asia/Calcutta (UTC+5:30); the broker server time differs.
   All internal logic in the canonical timezone from the harness; alerts display IST and
   broker time side by side.
3. Deduplication: one alert per setup, not one per bar. Persist fired-signal state so a
   restart does not re-alert.
4. Resilience: reconnect with backoff on feed drop, alert me when the feed has been dead
   >2 minutes, and never emit a signal computed on stale data.
5. Kill switch: implement the RULEBOOK kill-switch metrics as a live check that mutes
   signals and alerts me instead.
</correctness_requirements>

<deliverable>
Runnable service with a config file for all secrets and parameters, a systemd/docker run
recipe, the parity-test output pasted in, and a README section listing exactly what to
check on the first live day. Then tell me the three most likely ways this breaks in
production.
</deliverable>
```

---

## Before you run these — the target maths

| Claim | Reality |
|---|---|
| 60% win rate at 2.5:1 R:R | Expectancy 1.6R/trade. No published intraday gold system sustains this. Treat any backtest showing it as overfitted until the holdout says otherwise. |
| Realistic pairings | ~60% win rate at ~0.8-1.0R (mean reversion), or ~40% at 2.5R (breakout). Pick expectancy, not win rate. |
| $800/month on $5k | 16%/month — larger than the entire 12% 1-Step Flex target, every month. Possible in a good month, not as a baseline. |
| $30-60/day | ~$40/day x 20 days = $800. Needs ~2R/day net at $20/R. At 4 trades/day cap and realistic expectancy of 0.15-0.30R/trade, that requires larger lots — which collides with the $50 daily loss cap. P4 is written to surface exactly this collision. |
| Cost drag | Your own log: commission was 42% of the drawdown. The trade-count cap matters more than the entry signal. |

The prompts are written to optimise **expectancy per trade** and report honest
distributions. If the honest answer is "$15-25/day at this account size", that is the
number worth having.

---

## Deviations from this spec, tracked here so nothing silently drifts

- **P1 ran twice.** The first pass (`01_shortlist.md`) came back indicator-led (VWAP,
  EMA, ORB, ATR-squeeze, rolling breakout) — Rakesh's review found it didn't match what
  he actually wanted ("doesn't look like price action... we have mostly like indicator
  kind of"). Re-run as `01_shortlist_v2.md` with price-action/liquidity/institutional
  market-structure concepts as the primary mechanism and indicators demoted to an
  explicit per-candidate confidence layer, and expanded from 5 to 10 shortlisted
  candidates per his explicit ask. See `docs/status/decisions-and-open-questions.md`
  D22 for the full reasoning.
- **P3's architecture was redirected before implementation started.** Rakesh's explicit
  instruction: "have separate classes methods to call for each thing separately so when
  we move to LLM/JEV they may use them separately whatever order they wanted." P3 is
  being implemented as a shared, composable signal toolkit (`signals/price_action.py`,
  `signals/indicators.py`, `signals/confidence.py`) with each of the 10 strategies as a
  thin composition of toolkit calls, rather than 10 independent monolithic modules as
  the original P3 prompt's `<implementation>` section implies. See D23.
- **10 strategies go through P3, not 5** — matching the expanded v2 shortlist.
- **Data volume is smaller than the spec's ">=3 years" ask, honestly.** Real M1 XAUUSD
  via Dukascopy's public feed, backfilling in the background (resumable, hours-to-a-day+
  at a safe non-banned pace from this environment) rather than acquired synchronously.
  P3's validation protocol is scaled to whatever real coverage actually exists when it
  runs, clearly labeled, rather than pretending 3 years exist yet. See D24 and
  `data/QUALITY.md` for the exact coverage at any point in time.

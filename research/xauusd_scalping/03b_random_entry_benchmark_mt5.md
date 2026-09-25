# C3 Diagnostic -- Random-Entry Benchmark (XAUUSD)

Seed: 20260923, **500 runs per strategy** (reduced from an originally planned 1,000 -- the one-time real-strategy rerun needed regardless of N_RUNS turned out to dominate wall time, both from a real per-bar cost in `BacktestEngine.run()` (it copies the entire running history on every flat bar, O(n) per call) and from CPU contention with two other legitimate background jobs running concurrently at the time. 500 runs still gives usable order-statistic estimates for the 5th/50th/95th percentiles (ranks 25/250/475 of 500 sorted values) -- don't read them with 1,000-run precision.), window cap 20000 bars.
Each strategy's real trade count, session mix, and (stop_pts, target_pts) pairs feed n random entries per run, resolved through the exact same engine fill/cost logic (`BacktestEngine._open_position/_resolve_intrabar/_close_position`, called directly, not reimplemented) as the real backtests. Simplification: each run's entries are resolved independently, without cross-trade day-level risk-limit interaction (daily cap / consecutive-loss halt / max-trades-per-session) -- a reasonable approximation for isolating entry-timing/R:R quality, not a full day-level re-simulation. Sizing is the same fixed 0.08 lot as the real runs (equity-independent, no bias introduced).

| Strategy | n | Real PnL | Random p5 | Random p50 | Random p95 | Verdict |
|---|---|---|---|---|---|---|
| S07 Market Profile Value-Area Rotation | 2166 | $-10004.60 | $-13258.52 | $-9966.96 | $-6584.80 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |

**Summary**: 1 of 10 statistically indistinguishable from random noise, 0 below the random band (worse than noise), 0 above the random band (distinguishable positive signal), 0 with no comparison possible (zero real trades).

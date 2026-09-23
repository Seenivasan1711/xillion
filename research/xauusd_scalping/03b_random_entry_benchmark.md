# C3 Diagnostic -- Random-Entry Benchmark

Seed: 20260923, **500 runs per strategy** (reduced from an originally planned 1,000 -- the one-time real-strategy rerun needed regardless of N_RUNS turned out to dominate wall time, both from a real per-bar cost in `BacktestEngine.run()` (it copies the entire running history on every flat bar, O(n) per call) and from CPU contention with two other legitimate background jobs running concurrently at the time. 500 runs still gives usable order-statistic estimates for the 5th/50th/95th percentiles (ranks 25/250/475 of 500 sorted values) -- don't read them with 1,000-run precision.), window cap 20000 bars.
Each strategy's real trade count, session mix, and (stop_pts, target_pts) pairs feed n random entries per run, resolved through the exact same engine fill/cost logic (`BacktestEngine._open_position/_resolve_intrabar/_close_position`, called directly, not reimplemented) as the real backtests. Simplification: each run's entries are resolved independently, without cross-trade day-level risk-limit interaction (daily cap / consecutive-loss halt / max-trades-per-session) -- a reasonable approximation for isolating entry-timing/R:R quality, not a full day-level re-simulation. Sizing is the same fixed 0.08 lot as the real runs (equity-independent, no bias introduced).

| Strategy | n | Real PnL | Random p5 | Random p50 | Random p95 | Verdict |
|---|---|---|---|---|---|---|
| S01 Liquidity Sweep + Displacement + FVG Retest | 114 | $-416.29 | $-527.37 | $-428.10 | $-334.91 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S02 Multi-Timeframe Liquidity + CHoCH | 0 | $0.00 | — | — | — | n=0 -- no comparison possible |
| S03 Order Block Retest after BOS | 178 | $-612.94 | $-777.96 | $-675.27 | $-565.53 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S04 Wyckoff Spring/Upthrust | 0 | $0.00 | — | — | — | n=0 -- no comparison possible |
| S05 NR7/Inside-Bar Compression Breakout | 174 | $-811.50 | $-775.44 | $-665.83 | $-543.58 | BELOW random p5 -- worse than random noise |
| S06 Premium/Discount OTE Fib Retracement | 49 | $-146.06 | $-235.06 | $-179.83 | $-119.51 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S07 Market Profile Value-Area Rotation | 106 | $-278.77 | $-490.15 | $-403.16 | $-318.31 | ABOVE random p95 -- distinguishable from random (positive signal) |
| S08 BOS Pullback Continuation | 109 | $-419.31 | $-508.01 | $-417.21 | $-331.15 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S09 Session Liquidity Run + Reversal | 72 | $-278.57 | $-348.82 | $-261.55 | $-188.52 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S10 Equal Highs/Lows + RSI Divergence | 172 | $-564.07 | $-756.96 | $-645.67 | $-549.50 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |

**Summary**: 6 of 10 statistically indistinguishable from random noise, 1 below the random band (worse than noise), 1 above the random band (distinguishable positive signal), 2 with no comparison possible (zero real trades).

# C3 Diagnostic -- Random-Entry Benchmark (XAUUSD)

Seed: 20260923, **500 runs per strategy** (reduced from an originally planned 1,000 -- the one-time real-strategy rerun needed regardless of N_RUNS turned out to dominate wall time, both from a real per-bar cost in `BacktestEngine.run()` (it copies the entire running history on every flat bar, O(n) per call) and from CPU contention with two other legitimate background jobs running concurrently at the time. 500 runs still gives usable order-statistic estimates for the 5th/50th/95th percentiles (ranks 25/250/475 of 500 sorted values) -- don't read them with 1,000-run precision.), window cap 20000 bars.
Each strategy's real trade count, session mix, and (stop_pts, target_pts) pairs feed n random entries per run, resolved through the exact same engine fill/cost logic (`BacktestEngine._open_position/_resolve_intrabar/_close_position`, called directly, not reimplemented) as the real backtests. Simplification: each run's entries are resolved independently, without cross-trade day-level risk-limit interaction (daily cap / consecutive-loss halt / max-trades-per-session) -- a reasonable approximation for isolating entry-timing/R:R quality, not a full day-level re-simulation. Sizing is the same fixed 0.08 lot as the real runs (equity-independent, no bias introduced).

| Strategy | n | Real PnL | Random p5 | Random p50 | Random p95 | Verdict |
|---|---|---|---|---|---|---|
| S01 Liquidity Sweep + Displacement + FVG Retest | 353 | $-1490.04 | $-4818.72 | $-997.24 | $4194.12 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S02 Multi-Timeframe Liquidity + CHoCH | 0 | $0.00 | — | — | — | n=0 -- no comparison possible |
| S03 Order Block Retest after BOS | 749 | $-3969.08 | $-6501.64 | $-3836.76 | $-397.00 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S04 Wyckoff Spring/Upthrust | 6 | $-371.32 | $-495.76 | $-331.04 | $2064.24 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S05 NR7/Inside-Bar Compression Breakout | 798 | $-5473.58 | $-5897.20 | $-4572.44 | $-3327.72 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S06 Premium/Discount OTE Fib Retracement | 161 | $209.53 | $-2737.43 | $-448.72 | $2453.54 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S07 Market Profile Value-Area Rotation | 275 | $-328.96 | $-3033.28 | $-920.36 | $1480.44 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S08 BOS Pullback Continuation | 733 | $-3508.80 | $-6439.96 | $-3729.60 | $-732.52 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S09 Session Liquidity Run + Reversal | 428 | $-3108.32 | $-5246.00 | $-2705.44 | $-292.88 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S10 Equal Highs/Lows + RSI Divergence | 726 | $-3844.07 | $-5631.22 | $-3483.08 | $-1180.12 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |

**Summary**: 9 of 10 statistically indistinguishable from random noise, 0 below the random band (worse than noise), 0 above the random band (distinguishable positive signal), 1 with no comparison possible (zero real trades).

# C3 Diagnostic -- Random-Entry Benchmark

Seed: 20260923, **500 runs per strategy** (reduced from an originally planned 1,000 -- the one-time real-strategy rerun needed regardless of N_RUNS turned out to dominate wall time, both from a real per-bar cost in `BacktestEngine.run()` (it copies the entire running history on every flat bar, O(n) per call) and from CPU contention with two other legitimate background jobs running concurrently at the time. 500 runs still gives usable order-statistic estimates for the 5th/50th/95th percentiles (ranks 25/250/475 of 500 sorted values) -- don't read them with 1,000-run precision.), window cap 20000 bars.
Each strategy's real trade count, session mix, and (stop_pts, target_pts) pairs feed n random entries per run, resolved through the exact same engine fill/cost logic (`BacktestEngine._open_position/_resolve_intrabar/_close_position`, called directly, not reimplemented) as the real backtests. Simplification: each run's entries are resolved independently, without cross-trade day-level risk-limit interaction (daily cap / consecutive-loss halt / max-trades-per-session) -- a reasonable approximation for isolating entry-timing/R:R quality, not a full day-level re-simulation. Sizing is the same fixed 0.08 lot as the real runs (equity-independent, no bias introduced).

| Strategy | n | Real PnL | Random p5 | Random p50 | Random p95 | Verdict |
|---|---|---|---|---|---|---|
| S01 Liquidity Sweep + Displacement + FVG Retest | 144 | $-716.29 | $-616.40 | $-514.04 | $-404.46 | BELOW random p5 -- worse than random noise |
| S02 Multi-Timeframe Liquidity + CHoCH | 0 | $0.00 | — | — | — | n=0 -- no comparison possible |
| S03 Order Block Retest after BOS | 245 | $-1374.61 | $-1039.66 | $-908.30 | $-780.67 | BELOW random p5 -- worse than random noise |
| S04 Wyckoff Spring/Upthrust | 3 | $1.93 | $-21.44 | $-12.72 | $20.40 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S05 NR7/Inside-Bar Compression Breakout | 238 | $-1304.10 | $-1016.37 | $-878.91 | $-745.28 | BELOW random p5 -- worse than random noise |
| S06 Premium/Discount OTE Fib Retracement | 56 | $-194.87 | $-259.51 | $-198.42 | $-134.98 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S07 Market Profile Value-Area Rotation | 128 | $-724.54 | $-574.39 | $-475.76 | $-373.23 | BELOW random p5 -- worse than random noise |
| S08 BOS Pullback Continuation | 159 | $-892.41 | $-711.68 | $-593.88 | $-481.67 | BELOW random p5 -- worse than random noise |
| S09 Session Liquidity Run + Reversal | 86 | $-365.10 | $-397.74 | $-298.07 | $-205.23 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S10 Equal Highs/Lows + RSI Divergence | 237 | $-1264.62 | $-1001.96 | $-872.85 | $-740.23 | BELOW random p5 -- worse than random noise |

**Summary**: 3 of 10 statistically indistinguishable from random noise, 6 below the random band (worse than noise), 0 above the random band (distinguishable positive signal), 1 with no comparison possible (zero real trades).

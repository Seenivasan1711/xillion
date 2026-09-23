# C3 Diagnostic -- Random-Entry Benchmark

Seed: 20260923, **500 runs per strategy** (reduced from an originally planned 1,000 -- the one-time real-strategy rerun needed regardless of N_RUNS turned out to dominate wall time, both from a real per-bar cost in `BacktestEngine.run()` (it copies the entire running history on every flat bar, O(n) per call) and from CPU contention with two other legitimate background jobs running concurrently at the time. 500 runs still gives usable order-statistic estimates for the 5th/50th/95th percentiles (ranks 25/250/475 of 500 sorted values) -- don't read them with 1,000-run precision.), window cap 20000 bars.
Each strategy's real trade count, session mix, and (stop_pts, target_pts) pairs feed n random entries per run, resolved through the exact same engine fill/cost logic (`BacktestEngine._open_position/_resolve_intrabar/_close_position`, called directly, not reimplemented) as the real backtests. Simplification: each run's entries are resolved independently, without cross-trade day-level risk-limit interaction (daily cap / consecutive-loss halt / max-trades-per-session) -- a reasonable approximation for isolating entry-timing/R:R quality, not a full day-level re-simulation. Sizing is the same fixed 0.08 lot as the real runs (equity-independent, no bias introduced).

| Strategy | n | Real PnL | Random p5 | Random p50 | Random p95 | Verdict |
|---|---|---|---|---|---|---|
| S01 Liquidity Sweep + Displacement + FVG Retest | 209 | $-2382.80 | $-3693.62 | $-705.47 | $2520.69 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S02 Multi-Timeframe Liquidity + CHoCH | 0 | $0.00 | — | — | — | n=0 -- no comparison possible |
| S03 Order Block Retest after BOS | 484 | $-3493.84 | $-3769.16 | $-2124.12 | $-216.44 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S04 Wyckoff Spring/Upthrust | 3 | $1582.39 | $-197.84 | $-127.16 | $1592.91 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S05 NR7/Inside-Bar Compression Breakout | 566 | $-3686.90 | $-4066.93 | $-2775.58 | $-1613.01 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S06 Premium/Discount OTE Fib Retracement | 72 | $-640.01 | $-1924.65 | $-337.79 | $1614.43 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S07 Market Profile Value-Area Rotation | 204 | $411.69 | $-2397.28 | $-736.23 | $1309.70 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S08 BOS Pullback Continuation | 25 | $301.10 | $-695.00 | $-79.78 | $462.38 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S09 Session Liquidity Run + Reversal | 154 | $-247.79 | $-3186.65 | $-610.74 | $2007.82 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S10 Equal Highs/Lows + RSI Divergence | 476 | $-4244.97 | $-3592.13 | $-1895.20 | $-346.32 | BELOW random p5 -- worse than random noise |

**Summary**: 8 of 10 statistically indistinguishable from random noise, 1 below the random band (worse than noise), 0 above the random band (distinguishable positive signal), 1 with no comparison possible (zero real trades).

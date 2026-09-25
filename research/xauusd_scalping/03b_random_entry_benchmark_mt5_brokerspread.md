# C3 Diagnostic -- Random-Entry Benchmark (XAUUSD)

Seed: 20260923, **500 runs per strategy** (reduced from an originally planned 1,000 -- the one-time real-strategy rerun needed regardless of N_RUNS turned out to dominate wall time, both from a real per-bar cost in `BacktestEngine.run()` (it copies the entire running history on every flat bar, O(n) per call) and from CPU contention with two other legitimate background jobs running concurrently at the time. 500 runs still gives usable order-statistic estimates for the 5th/50th/95th percentiles (ranks 25/250/475 of 500 sorted values) -- don't read them with 1,000-run precision.), window cap 20000 bars.
Each strategy's real trade count, session mix, and (stop_pts, target_pts) pairs feed n random entries per run, resolved through the exact same engine fill/cost logic (`BacktestEngine._open_position/_resolve_intrabar/_close_position`, called directly, not reimplemented) as the real backtests. Simplification: each run's entries are resolved independently, without cross-trade day-level risk-limit interaction (daily cap / consecutive-loss halt / max-trades-per-session) -- a reasonable approximation for isolating entry-timing/R:R quality, not a full day-level re-simulation. Sizing is the same fixed 0.08 lot as the real runs (equity-independent, no bias introduced).

| Strategy | n | Real PnL | Random p5 | Random p50 | Random p95 | Verdict |
|---|---|---|---|---|---|---|
| S01 Liquidity Sweep + Displacement + FVG Retest | 354 | $-759.96 | $-4046.44 | $-304.80 | $4168.26 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S02 Multi-Timeframe Liquidity + CHoCH | 0 | $0.00 | — | — | — | n=0 -- no comparison possible |
| S03 Order Block Retest after BOS | 760 | $-2921.80 | $-5156.16 | $-2360.20 | $830.38 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S04 Wyckoff Spring/Upthrust | 6 | $-359.16 | $-486.76 | $-319.52 | $2071.72 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S05 NR7/Inside-Bar Compression Breakout | 810 | $-4158.16 | $-4505.44 | $-3362.22 | $-2156.54 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S06 Premium/Discount OTE Fib Retracement | 164 | $256.10 | $-2666.53 | $-270.67 | $2814.82 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S07 Market Profile Value-Area Rotation | 270 | $56.60 | $-2283.22 | $-387.42 | $2105.86 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S08 BOS Pullback Continuation | 741 | $-2137.60 | $-5492.28 | $-2331.46 | $654.60 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S09 Session Liquidity Run + Reversal | 432 | $-1861.18 | $-4498.28 | $-1937.88 | $445.32 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |
| S10 Equal Highs/Lows + RSI Divergence | 711 | $-3248.44 | $-4415.45 | $-2275.37 | $-4.29 | INSIDE random p5-p95 band -- statistically indistinguishable from random noise |

**Summary**: 9 of 10 statistically indistinguishable from random noise, 0 below the random band (worse than noise), 0 above the random band (distinguishable positive signal), 1 with no comparison possible (zero real trades).

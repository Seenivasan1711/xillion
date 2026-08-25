---
doc_id: 09-JOBS-PERIODIC
title: Periodic Job Specifications (R-series)
audience: data, quant
version: 1.0
---

# 09 — PERIODIC JOBS (R01–R06)

Weekly and monthly jobs. **These are what keep the system honest over time** — they are the difference between a system that works and a system that used to work.

---

## R01 — Weekly Walk-Forward Revalidation 🟢 P2

**Trigger:** Saturday 10:00

**Why:** a strategy validated once, six months ago, on data that ended before the regime changed, is not validated. Re-run the validation continuously.

```
FOR each active strategy:
    1. Re-run backtest over the trailing 12 months using the CURRENT parameters
    2. Split: in-sample (months 1-9) vs out-of-sample (months 10-12)
    3. Compute all metrics for both windows
    4. Compare LIVE results to BACKTEST expectation over the same recent period:

           divergence = |live_win_rate - backtest_win_rate|

           divergence < 5pp   → ✅ model matches reality
           5-10pp             → ⚠️ monitor
           > 10pp             → 🚨 the backtest is wrong about something.
                                   Investigate before continuing to trade it.

    5. MANDATORY REGIME SPLIT (KB 09 Rule 11):
           Report 2019-2025 vs 2026-YTD separately for short-premium strategies.
           A strategy profitable only in the pre-2026 window is a regime artifact,
           not a strategy.
    6. Write walk_forward_report
```

**The live-vs-backtest divergence check is the most valuable output.** It is the only mechanism that catches a backtest which was optimistic about costs, fills or liquidity — and those are the errors that matter.

---

## R02 — Strategy Decay Monitor 🟡 P1 ⭐

**Trigger:** Saturday 10:30

**Why:** published, popular, mechanical strategies decay. The 9:20 straddle's edge visibly degraded in 2023 through crowding and a volatility-regime change (KB `04` §B1). Any strategy you found online is being run by thousands of others.

```
FOR each strategy with >= 30 live trades:

    1. Split trades into first half vs second half
    2. Compare: win rate, expectancy, avg R, profit factor
    3. CUSUM / rolling-mean change-point detection on the expectancy series
    4. Statistical test: is the recent window's mean R significantly below
       the earlier window's? (t-test or bootstrap; report p-value, don't over-trust it
       on small samples)

    5. STATUS ASSIGNMENT:
         HEALTHY    wr_margin > +5pp AND expectancy stable/improving
         WATCH      wr_margin 0 to +5pp, OR expectancy declining but positive
         DEGRADED   wr_margin < 0 for 30+ trades, OR expectancy negative over last 50
                    → P08 applies size_multiplier 0.5
         DISABLED   expectancy negative over last 100 trades, OR drawdown > 1.5x
                    backtested max drawdown
                    → P08 refuses to arm. Requires manual review to re-enable.

    6. Alert on any status downgrade
```

**The 1.5× max-drawdown rule is a well-known practitioner heuristic:** when live drawdown exceeds 1.5× the worst drawdown seen in backtest, the strategy is behaving outside its tested envelope. Stop, then investigate.

**Automatic disabling is the point.** The failure mode this prevents is the human one — continuing to trade a decaying strategy because stopping feels like admitting defeat.

---

## R03 — Parameter Drift Detection 🟢 P2

**Trigger:** Saturday 11:00

Uses the MAE/MFE data collected by `T01` to answer whether the current parameters are still the right ones.

```
1. STOP ANALYSIS — from MAE distribution:
       % of losing trades whose MAE only slightly exceeded the stop
       → if high, the stop is too tight; trades are being shaken out
       % of winning trades whose MAE came close to the stop
       → measures how much room the strategy actually needs

2. TARGET ANALYSIS — from MFE distribution:
       % of trades that reached 80% of target then reversed
       → if high, the target is too far; consider taking profit earlier
       Distribution of MFE for trades that eventually lost
       → how much was given back

3. TIME ANALYSIS:
       P&L by holding duration — is there a duration past which edge decays?
       → informs T06 max_hold_duration

4. TIME-OF-DAY ANALYSIS:
       Expectancy by entry hour → tighten allowed_time_windows
       (KB 05 §C1 precedent: Friday produced 40%+ of annual ORB profit;
        such concentration is worth knowing about)

5. Produce RECOMMENDATIONS — never auto-apply
```

**Hard rule: `R03` proposes, a human disposes.** Auto-tuning parameters on recent results is curve-fitting with extra steps and a faster feedback loop into ruin. Recommendations go into the weekly report; changes require explicit approval and a re-run of `R01`.

---

## R04 — Risk Budget Rebalance 🟢 P2

**Trigger:** Sunday 10:00

```
1. Recompute capital base from the equity curve
2. Reallocate risk budget across strategies by recent risk-adjusted performance
       — cap any single strategy at cfg.max_strategy_allocation (default 40%)
       — floor allocation to keep a small allocation to WATCH strategies (data collection)
3. Anti-martingale enforcement:
       IF account drawdown > 10% → reduce ALL position sizing by 50% until
       a new equity high is made.
       NEVER increase size to recover losses. This rule is not configurable.
4. IF account at a new equity high AND all strategies HEALTHY:
       allow a size increase of at most +10% (gradual, not stepwise)
5. Lane B: recompute prop-firm DD headroom for the new period
```

**The anti-martingale rule is deliberately hard-coded.** The 60-cycle strangle study found the entire −24% drawdown came from a single five-loss cluster (KB `04` §B2) — losses arrive in streaks, not evenly. Increasing size during a drawdown is the mechanism by which a survivable streak becomes a terminal one. The same source's warning applies in the other direction too: *never scale up after a winning streak*, because the conditions producing easy wins precede drawdowns.

---

## R05 — Monthly Performance Review 🟢 P2

**Trigger:** 1st of month, 10:00

```
Full report:
    Equity curve, monthly return, Sharpe/Sortino, max DD, recovery factor
    Per-strategy attribution; per-lane attribution
    Cost analysis: total costs, cost as % of gross, cost per trade trend
    Execution quality trend
    Regime breakdown: performance by VIX band, cycle stage, day of week, session
    Trade distribution: R-multiple histogram, duration histogram
    Comparison vs backtest expectation
    Rule-breach log: how many times did a gate block a trade, and was it right?
```

**Include a "what would have happened" counterfactual:** P&L if every blocked signal had been taken. If blocked signals would have been profitable, a gate is miscalibrated. If they would have lost, the gates are earning their keep. Either answer is useful.

---

## R06 — Config vs Exchange Audit 🔴 P0

**Trigger:** Saturday 09:00 (and on demand)

**Why P0:** Indian F&O rules changed four times in under two years (`01` §1.5). A stale lot size silently mis-sizes every position — the system will not error, it will just risk more than you intended.

```
1. Fetch from exchange/broker APIs:
       lot sizes (all traded instruments)
       tick sizes
       expiry calendar for next 3 months
       trading holidays
       STT / transaction charge rates (from broker contract note if available)
       circuit limits, freeze quantities
       margin requirements (SPAN/exposure)

2. Compare against our config

3. FOR each mismatch:
       lot_size mismatch     → 🚨 P0 ALERT, BLOCK TRADING until acknowledged
       expiry day mismatch   → 🚨 P0 ALERT, BLOCK TRADING
       tick size mismatch    → P1 alert, auto-update
       charge rate mismatch  → P1 alert, auto-update, RECOMPUTE strategy economics
                               (a cost change can flip a marginal strategy negative)
       holiday calendar      → auto-update

4. Write config_audit_report; on any P0 mismatch require manual sign-off
```

**Historical mismatches this job would have caught:**
- Sep 2025: Nifty expiry Thursday → Tuesday
- Nov 2024: Bank Nifty weekly expiry discontinued entirely
- Jan 2026: Nifty lot 75 → 65, Bank Nifty 35 → 30
- Apr 2026: STT on options 0.10% → 0.15%

Each of these would have broken a hard-coded system silently, on a Monday morning, with real money on the line.

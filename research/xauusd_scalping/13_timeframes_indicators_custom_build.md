# 13 — Timeframes, indicator strategies and the custom build (2026-09-25)

Steps (a) slower timeframes → (b) longer history → (c) custom strategy, in
the order Rakesh chose. **Data:** his FundingPips MT5 XAUUSD M1 bars from
2020-01 to 2026-09 (2.37M bars), with tick-built bars and real spreads for
2020, part of 2025, and Nov 2025 onward (see §1).

## 1. Data added

- **M1 bar export, 2020-01 → 2026-09.** Timezone verified: 2024-01 matches
  Dukascopy at a 0h shift (median $0.048), and 2026 as before. The only gaps
  are market holidays. **Catch:** the bar file's SPREAD column is the
  minute's *minimum* spread. Over 309k overlapping minutes its median was 4pt
  against 17pt from ticks, so it is stored as `min_spread_pts` and never
  charged as a cost.
- **Tick export, 2020 → 2026.** Ticks exist only for 2020, part of 2025, and
  2026. None of 2021–2024 is in the broker's tick history. Where ticks
  exist they are dense (74–412 per minute), and a tick-built bar's range
  equals the broker's own bar (ratio 0.99–1.00). Merged: tick-built bars win
  where present, bar export elsewhere (`data/xauusd_mt5/`; the bar-only
  version is kept in `data/xauusd_mt5_barsonly_20260925/`).
- Real per-minute spread is therefore available on ~47% of minutes. The rest
  use the cost table (today's level).

## 2. New engine options (all opt-in; defaults reproduce every earlier number)

- `RESEARCH_TIMEFRAME=M5|M15|H1`: bars are resampled, and strategy dollar
  distances are scaled by the measured bar-range ratio (M5 2.42, M15 4.29,
  H1 8.76, close to √k as expected).
- `RESEARCH_REALISTIC=1`: how Rakesh's FundingPips 2-Step Flex $5K account
  would trade:
  - a fixed **$25 risk per trade** (two stop-outs = his $50 daily stop),
    rounded down to 0.01 lots (minimum 0.01);
  - **swap** (XAUUSD long −93.17 / short +21.68 points per lot per night, ×3
    on Wednesday);
  - **flat by Friday 16:45 New York** (the master-account rule).
- The S01 retest expiry was set to 30 minutes (decided at Rakesh's request,
  fixed before testing), and its reversed cancel check was fixed.
- S11 was added to the benchmark list (M1 only; it builds its own H1/M15 view).
- `custom_research.py` runs indicator rules I01–I08 and S01–S11 on a
  pre-registered split: **IS 2020-01→2024-06, VAL 2024-07→2025-06, HOLDOUT
  2025-07→end**, with the holdout refused without `--holdout-final`. It has
  **not** been run.
- `strategies/indicator_suite.py`: causal pandas features, proved by a test
  showing that truncated-series features equal full-series features.

## 3. Step (a)+(b): S01–S10 on every timeframe, 6.7 years, fixed 0.08 lot

Random band = 500 random entries with the same sessions, R:R and costs.

| TF | Above random p95 | Notes |
|---|---|---|
| M1 | S06 (+$532 / 1,149) | S01, S03, S05, S08 lose heavily; S02 n=12; S04 n=62. S07, S09–S11 still running at time of writing |
| M5 | none profitable | S05 "above p95" but −$22k |
| M15 | none | S01 and S07 below p5 |
| H1 | **S08 (+$10,682 / 746)** | every other strategy negative |

**Both leads fail the realistic checks:**
- **S08 H1:**
  - The whole profit is from 2025–26, the gold bull run: 2021–24 were −$3,793.
  - It is sized at ~$212 risk per trade, holds a median 19h, and held 172
    trades over a weekend.
  - Under realistic sizing, swap and flat-by-Friday it is **IS −$261,
    VAL +$14**.
- **S06 M1:** under realistic mode it is **IS −$1,476 over 776 trades** (only
  2022 positive) and VAL +$132.

## 4. Step (c): indicator strategies (realistic mode)

| Rule | H1 IS | H1 VAL | M15 IS | M5 IS |
|---|---|---|---|---|
| I01 EMA20/50 cross + EMA200 | −$59 | −$141 | −$3,348 | −$14,669 |
| I02 Donchian-20 breakout | −$349 | −$126 | −$7,768 | −$25,951 |
| I03 RSI(2) pullback | −$1,669 | −$257 | −$6,491 | −$22,379 |
| I04 Bollinger reversion (ADX<20) | −$1,546 | −$466 | −$9,106 | −$29,580 |
| I05 MACD cross + EMA200 | −$1,469 | −$66 | −$7,146 | −$22,743 |
| **I06 Supertrend flip** | **+$449** (>p95) | **+$303** | −$3,936 | −$13,610 |
| I07 London ORB | −$1,044 | −$35 | −$5,414 | −$10,193 |
| I08 VWAP 2σ reversion | −$4,123 | −$767 | −$14,562 | −$30,627 |

Everything on M5/M15 loses. Mean-reversion loses on every timeframe.
Trend-following on H1 is the only family near breakeven or better.

**I06 robustness (H1, 3×3 grid: Supertrend multiplier × exit ATR):**
- In-sample, only the pre-registered exit (stop 3 / target 4.5 ATR) is
  positive (+$449 at multiplier 3.0, +$309 at 3.5); **6 of 9 in-sample
  cells lose**.
- Validation is positive in 8 of 9, but VAL (Jul 2024–Jun 2025) was a strong
  gold uptrend, when almost any trend-follower wins.
- Size: ~0.05R per trade. **Knife-edge, not an edge.**

**Condition analysis (all H1 trend-family trades, IS vs VAL):** session, ADX
bucket and EMA alignment flip sign between IS and VAL. For example, ADX
25–30 was the best IS bucket (+$307) and the worst VAL bucket (−$475). The
only condition consistent in both periods was trades *against* the EMA200
(IS +$197 / 467, VAL +$459 / 132), which is too small to build on. **No filter
set generalises.**

**Pre-registered structural variant: long-only + price above its ~200-day
EMA.** It fails in-sample (I02 −$624, I06 −$79). Gold's long swap
(−93 points per night) costs more than the trend earns (I02 swap −$975).

## 5. Verdict

Across 11 price-action strategies, 8 indicator strategies, 4 timeframes and
6.7 years of the broker's own data, **nothing survives realistic FundingPips
trading on both in-sample and validation**. The only recurring effect is
trend-following on H1, and it pays only in strong trend regimes (2024–26),
at ~0.05R per trade. **The holdout has not been used** because no candidate
earned it.

What this rules out, and what it doesn't:
- **Ruled out:** mechanical intraday rules on M1–M15 (costs of ~$0.40–0.50
  per trade at 0.08 lots swamp the moves), classic indicator rules as
  written, and session/regime filters found by slicing.
- **Not ruled out:**
  - discretionary or news-driven trading;
  - multi-day swing trading on D1, which needs a swap-aware design:
    shorts *earn* swap on this broker, longs pay heavily;
  - order-flow ideas this data can't test.

# 14 — Results summary: every strategy, every test (as of 2026-09-26)

One page to read instead of 03–13. **Detail and reasoning:** `12` (broker
data, audit, feed differences), `13` (timeframes, indicators, custom build,
D1 swing), and `08` (correction history: every bug and wrong belief).

**Data:**
- Rakesh's FundingPips MT5 XAUUSD feed, 2020-01 → 2026-09 (2.37M M1 bars;
  tick-built bars and real spreads where the broker has ticks).
- The earlier Dukascopy feed was dropped because missing minutes flipped
  results (`12` §4).

**The bar (unchanged since `03b`):** net-positive after costs, n ≥ 100, and
above the p95 of 500 random-entry runs with the same sessions, stop/target
distances and costs.

**Two sizing modes:**
- **Fixed** = 0.08 lot, today's cost table, no swap.
- **Realistic** = how the FundingPips 2-Step Flex $5K account would trade:
  $25 risk per trade in 0.01-lot steps, swap charged, flat by Friday close.

**Split for anything built:** IS 2020-01→2024-06, VAL 2024-07→2025-06,
HOLDOUT 2025-07→ (locked, **never run**).

## S01–S11 — P&L (trades)

| Strategy | M1 fixed, 11 mo | M1 fixed, 6.7 y | M5 fixed | M15 fixed | H1 fixed | H1 realistic IS / VAL | Verdict |
|---|---|---|---|---|---|---|---|
| S01 Liquidity Sweep + FVG | −$1,490 (353) | −$16,254 (4,017) | −$2,865 (976) | −$11,199 (382) | −$3,107 (101) | −$0 (69) / +$25 (18) | no edge |
| S02 MTF Liquidity + CHoCH | 0 trades | −$127 (12) | −$136 (5) | −$214 (2) | 0 trades | 0 / 0 | never fires |
| S03 Order Block Retest | −$3,969 (749) | −$32,893 (6,231) | −$18,767 (4,783) | −$8,215 (2,787) | −$7,244 (845) | −$1,429 / −$537 | no edge |
| S04 Wyckoff Spring/Upthrust | −$371 (6) | −$118 (62) | −$1,460 (55) | −$877 (53) | −$4,410 (54) | −$37 / −$173 | too few trades |
| S05 NR7/Inside-Bar Breakout | −$5,474 (798) | −$33,541 (6,443) | −$22,223 (5,431) | −$19,927 (3,881) | −$8,171 (1,363) | −$1,030 / −$486 | no edge |
| S06 OTE Fib Retracement | +$210 (161) | **+$532 (1,149) >p95** | +$1,392 (284) | −$2,536 (107) | −$153 (10) | +$160 (6) / −$80 (3) | **failed realistic M1: IS −$1,476** |
| S07 Value-Area Rotation | −$329 (275) | −$10,005 (2,166) | −$9,153 (1,678) | −$13,019 (1,593) | −$13,590 (1,381) | −$1,452 / −$700 | no edge (the old "lead" was a data artifact) |
| S08 BOS Pullback Continuation | −$3,509 (733) | −$33,654 (6,172) | −$17,157 (4,784) | −$4,907 (2,563) | **+$10,682 (746) >p95** | −$261 / +$14 | **failed: all profit in 2025–26, and realistic mode loses** |
| S09 Session Liquidity Run | −$3,108 (428) | −$12,742 (2,330) | −$27,046 (3,877) | −$25,191 (2,610) | −$20,206 (1,077) | −$719 / −$513 | no edge (the old "lead" was a day-boundary bug) |
| S10 Equal H/L + RSI Divergence | −$3,844 (726) | −$29,695 (6,169) | −$16,409 (4,174) | −$14,834 (1,986) | −$6,453 (407) | −$50 / +$17 | no edge |
| S11 Video MTF Liquidity Scalp | — | −$22,006 (4,413) | n/a | n/a | n/a | n/a | no edge (M1-only design; inside the random band) |

"M1 fixed, 11 mo" is the Nov 2025→Sep 2026 tick set (`12` §6). The other
fixed columns cover 2020–2026 (`13` §3). The M5/M15/H1 fixed runs used the
bar-only data before ticks were merged; the difference is a few cents per bar.

## Indicator rules I01–I08 (realistic mode) — P&L

| Rule | H1 IS | H1 VAL | M15 IS | M5 IS |
|---|---|---|---|---|
| I01 EMA20/50 + EMA200 | −$59 | −$141 | −$3,348 | −$14,669 |
| I02 Donchian-20 breakout | −$349 | −$126 | −$7,768 | −$25,951 |
| I03 RSI(2) pullback | −$1,669 | −$257 | −$6,491 | −$22,379 |
| I04 Bollinger reversion | −$1,546 | −$466 | −$9,106 | −$29,580 |
| I05 MACD + EMA200 | −$1,469 | −$66 | −$7,146 | −$22,743 |
| I06 Supertrend flip | **+$449 (>p95)** | **+$303** | −$3,936 | −$13,610 |
| I07 London ORB | −$1,044 | −$35 | −$5,414 | −$10,193 |
| I08 VWAP 2σ reversion | −$4,123 | −$767 | −$14,562 | −$30,627 |

I06 is knife-edge: 6 of 9 parameter variants lose in-sample (`13` §4).

## D1 swing D01–D05 (realistic mode, $50 risk) — P&L, master account (flat by Friday)

| Rule | IS | VAL |
|---|---|---|
| D01 Turtle 20/10 | −$125 (75) | −$145 (21) |
| D02 Turtle 55/20 | +$16 (42) | −$135 (16) |
| D03 SMA50/200 trend | −$30 (29) | −$13 (5) |
| D04 RSI(2) daily | −$265 (38) | +$123 (10) |
| D05 Weekly momentum | −$331 (221) | +$400 (51) |

None beats its same-side random p95. Weekend holding (evaluation mode) makes
every rule worse, because of long swap (`13` §6).

## Leads that turned out to be artifacts

| Lead | Looked like | Real cause | Doc |
|---|---|---|---|
| S07 M1 | +$412, "the lead" | Dukascopy's missing minutes; on the same minutes both feeds lose ~$1,150 | `12` §4 |
| S09 M1 | +$1,356 | UTC-midnight "previous day" levels, not the MT5 D1 candle | `12` §6, `08` #21 |
| S08 M1 | +$590 | a stuck setup state machine (months with zero trades) | `08` #22 |
| S08 H1 | +$10,682 >p95 | the 2025–26 gold bull run; 2021–24 −$3,793; oversized ($212 risk); no swap | `13` §3 |
| S06 M1 | +$532 >p95 | fixed sizing; realistic mode IS −$1,476 | `13` §3 |
| I06 H1 | +$449 >p95 | one lucky exit setting out of 9 | `13` §4 |

## ML signal filter (doc 15, pre-registered)

The walk-forward meta-labeling model over all H1+M15 signals **fails**:
- WF-IS: −$2,774 on 784 taken trades, worse than a random pick of the same
  size (median −$1,541).
- WF-VAL: −$90 on 57 trades, below random p95.

The holdout was deliberately not spent on a failed model.

## Bottom line

**No strategy, indicator rule or swing rule makes money under realistic
FundingPips trading in both IS and VAL above random.** The only recurring
effect is trend-following on H1, and it pays only in strong trend regimes, at
~0.05R per trade. The holdout remains unused, for a future candidate that
earns it.

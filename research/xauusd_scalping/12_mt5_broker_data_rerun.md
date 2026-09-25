# 12 — Broker (MT5) data import, and S07 re-run on it

**Date: 2026-09-25.** Supersedes `10` §4's S07 "lead" status.

## 1. The data

Rakesh exported from his FundingPips MT5 terminal (View → Symbols):

| File | Kind | Range | Result |
|---|---|---|---|
| `XAUUSD_202511030100_202609251344.csv` (5.5 GB) | ticks | 2025-11-03 → 2026-09-25 | **309,714 M1 bars** |
| `XAUUSD_M1_202606111119_202609251336.csv` | M1 bars | 2026-06-11 → 09-25 | 100,005 bars — stopped by MT5's default "Max bars in chart" = 100k |

Imported by `data/import_mt5_csv.py` into `data/xauusd_mt5/` (gitignored),
selected with `RESEARCH_DATA_SOURCE=mt5`. Bars are built from the tick mid
price (same as the Dukascopy downloader). Volume is the tick count, and there
is an extra `spread_pts` column holding the broker's median spread in each minute.

**Verified, not assumed:**
- **Server clock = EET/EEST** (UTC+2 winter, +3 summer, **EU** DST calendar).
  Measured against Dukascopy UTC bars: +3h in summer gave a median |close
  diff| of $0.085 (±1h gave ~$6.6). The DST calendar was checked per day over
  March 2026: under the US calendar, 03-08..03-27 needed an extra +1h, while
  under the EU calendar every day matched. With the final setting, every
  overlapping month matches Dukascopy at 0h shift, median diff $0.04–0.07.
- **No holes.** Every gap over 10 minutes is structural: the daily break,
  weekends, 12-25 and 01-01, and US-holiday early closes. The Dukascopy set
  was missing ~495 hours.
- Chunked tick import is identical to a single-pass import (`tests/test_mt5_import.py`).

## 2. Surprise: the broker's gold spread doubled in July 2026

Median `spread_pts` by month: **17 in Nov 2025–Jun 2026** (12 in Feb), then
**26 in Jul, 31 in Aug, 33 in Sep**. The cost table (NY 30, London 28) matches
*current* conditions, and so does Rakesh's 31pt reading, so the table was
**not** changed. Strategies are judged at the cost they'd face today, which
overcharges the Nov–Jun history by roughly 2x on spread. If an edge is ever
marginal, re-run it with per-bar real spread before trusting or rejecting it.

## 3. S07 Value-Area Rotation on broker data

| Window | Feed | n | P&L |
|---|---|---|---|
| 2026-03..09 | Dukascopy (`10` §4) | 204 | **+$411.69** |
| 2026-03..09 | **MT5 broker** | 191 | **−$765.72** |
| 2025-11..2026-02 | MT5 broker | 129 | −$1,400.88 |
| **Full 11 months** | MT5 broker | **320** | **−$2,169.80** |

Random-entry benchmark (500 runs, same sessions and R:R): p5 −$3,042 / **p50 −$898** /
p95 +$1,913. **S07 is inside the band and below the random median.**

Per month (MT5): Nov −278, Dec −92, Jan −501, Feb −530, Mar +303, Apr −194,
May −569, Jun +93, Jul −497, Aug +171, Sep −73. Only 3 of 11 months were positive.

**Reading:** over the *same months*, switching the feed moved S07 by
~$1,180. §4 shows why: the cause is Dukascopy's missing and extra minutes
compounded by path dependence, not price differences. So the +$412 was
never a robust effect. On the
feed Rakesh would actually trade, S07 loses in both windows. **S07 is no longer
the lead. No XAUUSD M1 strategy has an edge.**

## 4. Why do the two feeds give different results?

The prices are **not** the reason. On the minutes both feeds have, closes
agree to a median of $0.04–0.07. S07, run over the Mar–Sep window:

| Run | Bars | n | P&L |
|---|---|---|---|
| Dukascopy, as downloaded | 174,554 | 204 | +$411.69 |
| MT5, as exported | 189,362 | 179 | −$735.88 |
| **Dukascopy, only minutes MT5 also has** | 168,132 | 192 | **−$1,119.62** |
| **MT5, only minutes Dukascopy also has** | 168,132 | 178 | **−$1,180.24** |

Give both feeds the same minutes and they agree: both lose about $1,150. The
+$412 came from Dukascopy's data *coverage*: it was missing ~21k minutes
(the ~495 throttled hours) and had ~6k minutes the broker doesn't quote.
Trade by trade:
- Only 92 of ~190 trades are the same trade (same minute and side) on both
  raw feeds.
- Of those 92, 91 exit the same way.
- The rest diverge through **path dependence**. With one position at a time,
  a 2-loss halt and a $50 daily cap, a single missing minute changes one
  trade, and that shifts every later trade that day. Missing bars also change
  the previous day's value area (POC/VAH/VAL), which moves entries and targets.

**Lesson:** a result that flips sign when 3–10% of minutes are added or
removed is not an edge. Any future candidate should be checked on both feeds
and on minute-subsampled data before it is trusted.

## 5. Audit and fixes (2026-09-25)

An independent audit rebuilt all 64 S07 trades from a Dec–Jan slice straight
from the parquet with separate code. Every trade matched the engine exactly:
entry fill, exit bar, exit price, vol bucket and USD P&L. The engine's fills,
costs, P&L and look-ahead handling are correct. Fixed:
1. **S04/S11 cache bug.** Today's-bars index was cached across calls, but
   `ctx.bars(N)` is a fresh sliding slice, so after N bars "today" shrank to
   the current minute (wrong on 13,983 of 14,000 bars checked). Now recomputed
   per call (`_common.todays_start`, `DailyBarCache`).
2. **Day boundary.** Everything used the UTC calendar day, which cuts gold's
   Asian session in half. Mondays got a ~2h Sunday stub as "the previous
   day", and S07 clustered 32 of 64 trades in hour 0 UTC. Now uses
   `cost_model.trading_date`: gold's trading day rolls at 17:00 New York, the
   same boundary as FundingPips' EET midnight. This is used by the strategies'
   daily levels and by the engine's daily cap / 2-loss halt reset.
3. **Random benchmark made apples-to-apples.** It now uses the real vol bucket
   at entry and exit instead of always MEDIUM, and applies stop/target
   distances from the fill price, as the real trades do. This was small
   (about −$0.09/trade).
4. **S02 speed.** Daily bars are cached per trading day; S02 alone had made
   the full run 6h+.
5. **New `RESEARCH_SPREAD=broker`** charges each trade the broker's real spread
   for that minute (MT5 feed only), instead of the table.

Regression: with the day boundary monkeypatched back to UTC, the refactored
engine reproduces the old S07 Dukascopy result exactly (204 trades,
$411.69). Known and left as-is: `max_trades_per_session=4` is really a
per-trading-day cap, and fills are at the signal bar's close, not the next
bar's open (median 0pt difference).

## 6. All 10 strategies, fixed harness, 11 months of broker data

`RESEARCH_DATA_SOURCE=mt5`, after every fix in §5 plus the S08 fix below.
"Table" charges today's cost table (NY ~30pt, which matches Jul–Sep 2026).
"Broker" charges the broker's real spread for each minute (17pt through Jun,
~33 after). The random band is 500 random-entry runs with the same sessions,
R:R, costs and vol buckets. **The bar is net-positive, n ≥ 100 and above
random p95.**

| Strategy | n | P&L table | P&L broker | Random p50 / p95 (broker) | vs p50 (broker) | Verdict |
|---|---|---|---|---|---|---|
| S01 Liquidity Sweep + FVG | 354 | −$1,490 | −$760 | −$305 / +$4,168 | −$455 | noise |
| S02 MTF Liquidity + CHoCH | 0 | — | — | — | — | never fires (known) |
| S03 Order Block Retest | 760 | −$3,969 | −$2,922 | −$2,360 / +$830 | −$562 | noise |
| S04 Wyckoff Spring/Upthrust | 6 | −$371 | −$359 | — | — | too few trades |
| S05 NR7/Inside-Bar Breakout | 810 | −$5,474 | −$4,158 | −$3,362 / −$2,157 | −$796 | noise (worse half) |
| **S06 OTE Fib Retracement** | 164 | **+$210** | **+$256** | −$271 / +$2,815 | +$527 | noise, least bad |
| S07 Value-Area Rotation | 270 | −$329 | +$57 | −$387 / +$2,106 | +$444 | noise |
| S08 BOS Pullback Continuation | 741 | −$3,509 | −$2,138 | −$2,331 / +$655 | +$193 | noise |
| S09 Session Liquidity Run | 432 | −$3,108 | −$1,861 | −$1,938 / +$445 | +$77 | noise |
| S10 Equal H/L + RSI Divergence | 711 | −$3,844 | −$3,248 | −$2,275 / −$4 | −$973 | noise (worse half) |

**No strategy clears the bar under either cost model.** S06 is the only one
net-positive under both, but it is ~$2,500 short of its p95. That is not a
tradeable edge.

**Two "leads" from this session were bugs, not edges:**
- **S09** showed +$1,356 / 274 trades under UTC days. That was from using the
  UTC-midnight "previous day" high/low, not the levels on Rakesh's MT5 D1 chart
  (EET midnight = gold's trading day). Proof: only the strategy-side boundary
  moves it (engine boundary alone: no change), and both boundaries set back to
  UTC reproduce +$1,355.56 exactly.
- **S08** showed +$590 / 234 trades. Its pullback setup was dropped only at a
  61.8% retracement (the spec says 50%), but it could only fire at ≤38.2%. Since
  retracement only grows, setups stuck between the two sat in the state machine
  for weeks: Feb, Apr, Aug and Sep had zero trades. After the fix: 741 trades,
  −$2,138, at the random median. The fixed S08 also agrees across feeds
  (Mar–Sep: Dukascopy −$2,798, MT5 −$2,447).

**Reading:** random entries with these R:R geometries lose $300–3,700 per
year purely from costs, and every strategy lands inside that luck band. On M1
gold at 0.08 lots, none of the ten rule sets adds information beyond chance.

## 7. Open questions / not done

- **S01's setup-cancel rule is reversed in the code.** It voids a short setup
  when price stays *below* the bearish gap (the normal state), so in practice
  it only enters on a next-bar retest. The spec's own rule ("gap fully filled
  without triggering") can't happen with a touch entry, so a literal fix would
  wait forever. **Needs a decision on an expiry (N bars) before fixing.** Not
  guessed.
- `max_trades_per_session=4` is really a per-trading-day cap.
- Longer history: raise MT5 Tools → Options → Charts → Max bars to Unlimited
  and re-export M1 from 2024 or earlier.

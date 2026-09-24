# 11 — Forex support in the research harness (EURUSD, GBPUSD)

**Date: 2026-09-24.** Rakesh's direction: Track B, XAUUSD first, forex
next. This makes the same 10-strategy toolkit + random-entry benchmark run
on forex pairs, so FX is tested with exactly the rigor gold was — no new
strategies, no retuning.

---

## 1. What was built

| Piece | Change |
|---|---|
| `engine/instruments.py` (new) | One `Instrument` spec per symbol: Dukascopy divisor, MT5 point size, USD/point/lot, spread table (points), commission, `price_scale`. XAUUSD, EURUSD, GBPUSD defined. |
| `engine/cost_model.py` | `CostModel.point_size` (default = XAUUSD's 0.01) + `CostModel.for_instrument()`. |
| `engine/backtest_engine.py` | Uses `self.cost_model.point_size` at every points↔price boundary (was the module constant from the 100x fix, doc `10`). |
| `data/download_dukascopy.py` | Per-symbol directory **and manifest** (`data/<symbol>/`) — a shared manifest would be clobbered by two downloaders running side by side. Per-symbol divisor. XAUUSD path unchanged. |
| `run_backtests.py` / `random_entry_benchmark.py` | `RESEARCH_SYMBOL=EURUSD` selects the symbol; outputs get a `_eurusd` suffix (XAUUSD filenames unchanged). Benchmark cache is per-symbol. |
| S08 / S09 / S10 | Hardcoded gold-dollar literals (S08's 0.5 stop buffer, S09/S10's 7.5 fallback target) turned into params so they scale. Defaults identical — XAUUSD behavior unchanged. |
| `tests/test_instruments.py` (new) | Hand-derived contract economics, EURUSD costs in EURUSD points, param scaling, refusal of an unmeasured scale, equivalent-lot risk, scale measurement. 43/43 research tests pass. |

**XAUUSD verified unchanged:** S06 on the original 174,554 bars reproduces
exactly 72 trades / -$640.01 (doc `10` §4).

## 2. How strategy distances carry over — `price_scale`

The strategies' distance params are in **gold dollars** (`min_sl_pts=3.0` =
a $3.00 stop; also `sl_buffer_pts`, `bin_pts`, `fallback_target_pts`). On
EURUSD at ~1.15 those numbers are meaningless, so each is multiplied by:

> **`price_scale` = median daily high-low range (symbol) / median daily range (XAUUSD), over the same dates**

It is **measured from the downloaded data at run time, never typed in** —
`scale_strategy_params` refuses to run a symbol whose scale is unmeasured.
Everything else in the signals toolkit is already scale-free (ATR
multiples, percentages), which was checked, not assumed.

Position size is scaled the same way (`equivalent_lots`): the lot size that
risks the same USD per stop as 0.08 lot on gold ($24 on a $3 stop). That
keeps the $50 daily cap, the 2-loss halt and the random benchmark
comparable across symbols.

## 3. Verified vs. assumed

| | Status |
|---|---|
| Dukascopy divisor 100,000 for EURUSD/GBPUSD | **Verified** — 2026-09-15 10h UTC parsed to EURUSD 1.15373 / GBPUSD 1.34778 |
| Point size 0.00001, $1/point/lot (USD-quoted pairs) | Contract standard; test pins $10/pip/lot |
| Spread table | **ASSUMED** — EURUSD 0.6-1.0 pip liquid hours, up to 5 pips in the dead zone; GBPUSD 1.4x. Dukascopy's own interbank median that hour: **0.2 pip EURUSD, 0.6 pip GBPUSD**; a prop broker will be above that. Real reading = manual-tasks.md (top item) |
| Commission $2.50/lot/side | **ASSUMED** same as XAUUSD until the MT5 symbol spec is read |
| Swap | Not modelled (same as XAUUSD) — irrelevant for intraday M1, required before any H4/D1 test |

## 4. How to run

```bash
# data (resumable, runs detached; ~6h per pair per 6.5 months at --delay 4)
cd research/xauusd_scalping/data
python download_dukascopy.py --symbol EURUSD --from 2026-03-01 --to 2026-09-17 --delay 4

# backtests + random benchmark (from research/xauusd_scalping/)
RESEARCH_SYMBOL=EURUSD python run_backtests.py
RESEARCH_SYMBOL=EURUSD python random_entry_benchmark.py   # -> 03b_random_entry_benchmark_eurusd.md
```

The first thing each run prints is the measured `price_scale` and
equivalent lot size — sanity-check them (EURUSD should land around
0.0002: ~70 pips/day vs gold's ~$40/day) before reading any result.

## 5. Status and next

- 🟡 **Downloads run as one sequential chain** (`data/_download_chain.sh`,
  under `caffeinate`): EURUSD → XAUUSD 2026-03→09 gap-fill → XAUUSD
  2024-01→2026-02 backfill → GBPUSD. Log: `/tmp/dukascopy_chain.log`.
  Running them concurrently got whole trading days throttled away — see
  `08_correction_history.md` #19.
- ⬜ Run `run_backtests` + random benchmark per pair once data lands; same
  decision rule as gold — net-positive, n ≥ 100, above random p95.
- ⬜ Re-run XAUUSD S07 + benchmark once the gap-fill completes (doc `10`'s
  numbers ran on a series with ~495 missing hours).
- ⬜ Rakesh: real MT5 spreads for both pairs (manual-tasks.md).
- ⚠️ The Mac must stay on/awake (plugged in, lid open) — `caffeinate -i`
  blocks idle sleep, not lid-close sleep on battery.

**Caveat on the XAUUSD data dir:** the 2024-2026 backfill writes into the
same `data/xauusd/` folder, so `load_all_bars()` now returns a longer
series as it lands. Reproducing doc `10`'s numbers requires filtering to
`ts >= 2026-03-01`.

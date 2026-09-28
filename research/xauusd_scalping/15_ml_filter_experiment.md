# 15 — ML signal filter (meta-labeling) experiment

**Pre-registered 2026-09-28, BEFORE any result was computed.** Everything in
§1 was committed to git before `ml_filter.py` was first run, so it can't be
adjusted after seeing numbers. Results are appended in §2 and nothing in §1
changes.

## 1. Pre-registration

**Question:** the S01–S10 and I01–I08 signals have no timing skill on their
own (docs 13–14). Can a model that sees each signal's entry context learn
which ones to take, well enough to be profitable on months it has never seen?

**Honest prior:** low odds. The inputs are strategies that sit inside their
random-entry bands, and costs don't change.

**Data:** every trade from `custom_research.py` in realistic mode ($25
risk, swap, flat by Friday) on **H1 and M15** for S01–S10 and I01–I08.
Chosen because M5/M1 lose so heavily that filtering them would only
flatter the result.

**Label:** R = net P&L / $25, clipped to [−3, 3].

**Features (all known at entry):**
- strategy key (one-hot)
- timeframe
- side
- entry hour (UTC)
- weekday
- session (one-hot)
- ADX(14)
- RSI(14)
- with-EMA200
- EMA50-over-200
- with-Supertrend

Raw ATR is excluded, because it trends with the gold price (≈$1.5k→$4.3k) and
would act as a date proxy.

**Model (one, fixed):** `HistGradientBoostingRegressor(max_depth=3,
learning_rate=0.05, max_iter=200, min_samples_leaf=50, random_state=0)`.
No tuning.

**Walk-forward:**
- For each calendar month m from 2021-01 on, train on every trade whose
  **exit** is before month m starts (so no label leaks), then predict month
  m's trades.
- **Take a trade if predicted R > 0.**
- 2020 is training-only warm-up.

**Evaluation windows:**
- WF-IS: 2021-01 → 2024-06
- WF-VAL: 2024-07 → 2025-06
- HOLDOUT: 2025-07 → end, run once at the very end whatever WF-IS/WF-VAL show

**Baselines:**
- (a) take every signal.
- (b) a **random filter with the same take-rate in each month**, 1,000 draws;
  report its p50 and p95.

**Pass (all required, in WF-IS AND WF-VAL):**
- taken net P&L > 0
- taken net P&L > random-filter p95
- ≥ 100 trades taken
- positive in ≥ 50% of months with trades

**Caveat, stated in advance:** trades from different strategies can overlap
in time. The sum is "each signal taken independently", not one account with
a single position. If the filter passes, a portfolio-level re-run with one
position at a time is required before anything else.

## 2. Results

*(appended after running)*

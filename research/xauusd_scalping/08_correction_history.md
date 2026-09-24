# Correction history — every bug, wrong belief, and fix, in order

**Why this file exists:** Rakesh's explicit ask (2026-09-24) — a permanent
record of what was believed, what turned out to be wrong, how it was
found, and what changed as a result. Intended to be read by a future
session (human or LLM) *before* making decisions, so the same ground is
never re-walked and past corrections inform future ones.

**How to use it:** each entry follows the same shape —
*what was believed → what was actually true → how it was found → the fix →
what it changed.* The "how it was found" column is the most reusable part:
the same detection methods keep working.

**Keep this updated.** Every future correction gets appended here, not just
fixed in code. A fix without its reasoning recorded becomes a mystery in
three months.

---

## Index of all documents in this track

| File | What it holds |
|---|---|
| `00_build_prompts.md` | The original P1-P5 research spec, verbatim, plus tracked deviations |
| `01_shortlist.md` / `01_shortlist_v2.md` | Strategy candidate research (v1 indicator-led, rejected; v2 price-action-led, used) |
| `02_harness.md` | Backtest harness design + strategy interface contract |
| `03_results.md` | All backtest rounds (v1/v2/v3) + C1/C2/C3 diagnostics — **flagged provisional** |
| `03b_random_entry_benchmark.md` | Random-entry baseline: which strategies beat chance |
| `03c_timeframe_experiment.md` | M5/M15 experiment and why it failed |
| `03d_s11_video_strategy_result.md` | S11 (video-sourced) implementation + results |
| `04_plan.md` | P4 synthesis plan (regime router, rulebook template, holdout protocol) |
| `05_consolidated_findings_and_strategy_request.md` | Self-contained brief for an external reviewer + **video-strategy log (§8)** |
| `06_rr_geometry_finding_and_plan.md` | The R:R geometry bug + the 5-phase plan |
| `07_conclusion_m1_scalping_verdict.md` | **The verdict — read this for "does this work"** |
| `08_correction_history.md` | **This file — read this for "what did we learn"** |
| `09_leverage_cannot_fix_negative_expectancy.md` | Why leverage cannot rescue a losing system (asked 2026-09-24) |
| `S04_range_detection_design_question.md` | Self-contained design brief handed to an external LLM |

---

## The corrections, in order

### 1. Dukascopy download failures were not rate-limiting
- **Believed:** a ~34% per-hour download failure rate was Dukascopy rate-limiting (a 429 had been seen once).
- **Actually:** a bare TLS `ConnectTimeout` on the handshake — a transient network fault, not a server refusal.
- **Found by:** making one direct diagnostic call against a known-failed hour and reading the actual exception, instead of inferring from the pattern.
- **Fix:** retry-with-backoff on `TimeoutException`/`ConnectError`/`ReadError`. Verified by re-running the exact hour that had failed.
- **Changed:** unblocked the full 6.5-month backfill (174,554 bars).

### 2. A silent data-loss window in the downloader
- **Believed:** the resumable manifest made the download safe to interrupt.
- **Actually:** bars were only flushed to parquet at *month* boundaries, but the manifest marked hours complete as they were fetched. A crash mid-month lost up to a month of data that the manifest claimed existed — so a re-run would never re-fetch it.
- **Found by:** reading the flush logic while reviewing an unrelated change.
- **Fix:** flush at least daily as well as at month boundaries.
- **Changed:** prevented a silent, permanent hole in the dataset.

### 3. Engine: `consecutive_loss_halt` never reset on day rollover
- **Believed:** every strategy genuinely produced only 0-3 trades across a 20k-bar dataset.
- **Actually:** once any strategy hit 2 consecutive losses *anywhere*, the halt latched permanently for the rest of the run — unlike its sibling `daily_loss_cap_usd`, which correctly reset daily.
- **Found by:** noticing that trade counts were near-identical across strategies *regardless of their logic* — an implausible pattern that pointed at shared machinery rather than the strategies.
- **Fix:** reset on day rollover + a regression test.
- **Changed:** every backtest before this was meaningless.

### 4. Stop/target smaller than the cost markup
- **Believed:** five strategies genuinely had an exact 0.0% win rate.
- **Actually:** their structural targets (e.g. a 3-point `min_sl_pts`) were smaller than the session's cost markup, so the target sat on the losing side of the fill *before the trade was even placed*.
- **Found by:** an exact 0.0% — too clean to be real. Round numbers in results are a tell.
- **Fix:** `signals/risk_floor.py` (`apply_floor`), widen-only, floors read off the cost table.
- **Changed:** win rates moved from a flat 0% to a believable 21-56%.

### 5. S02/S04 lookback windows too small to ever satisfy their own gates
- **Believed:** these two fired no signals because the dataset was too short.
- **Actually:** `ctx.bars(n)` returns the last *n raw M1 bars*, not *n days*. `ctx.bars(3000)` ≈ 2 trading days, but the logic needed 5-10 *daily* bars. Structurally impossible at any dataset size.
- **Found by:** tracing what the function actually returned, after the "more data will fix it" explanation survived a 6.5-month dataset unchanged.
- **Fix:** widened to 25,000 / 12,000 bars.
- **Changed:** removed a false explanation that had been repeated across three result versions.

### 6. S04's range check was near-unsatisfiable
- **Believed:** S04's zero signals were a data-length problem (see #5).
- **Actually:** its "is this a range" test required **every** day in the window to have its high near the top **and** its low near the bottom simultaneously. Real daily bars almost never do both. 852 of 873 sampled real windows failed this exact check.
- **Found by:** instrumenting the failure *reason* rather than just the pass/fail count.
- **Fix:** rejected two quick patches that didn't hold up (an OR-relaxation still fired 0/852; a trend/range efficiency ratio fired on ~98% of windows, i.e. no discrimination), then a proper 3-gate redesign via an external design review — Kaufman ER with the **corrected denominator**, a random-walk containment envelope, and a boundary touch-count. `sigma_to_atr = 1.4628` **measured** from real data, not guessed.
- **Changed:** S04 went from structurally-dead to producing (2) signals. Also established the practice of writing a self-contained design brief for a second opinion rather than guessing.

### 7. S04's range window included "today" — a tautology
- **Believed:** the gates were correct after the redesign.
- **Actually:** the range-defining window included the current day, so today's own bars could never *break out* of a range that already contained them.
- **Found by:** gates passing at the expected rate while penetrations stayed at zero — an internal inconsistency.
- **Fix:** exclude the most recent day from the boundary window.

### 8. S04 performance: ~40 minutes per run
- **Actually:** the full 45,000-bar window was being resampled to daily on *every single M1 bar*.
- **Found by:** noticing S04 ran ~3x slower than S02 despite a *smaller* window — a comparison that didn't add up.
- **Fix:** per-calendar-day caching in the caller (keeping the shared detector pure). Verified 0 mismatches against the naive result.
- **Changed:** 40 minutes → 64 seconds.

### 9. `VolBucket` was dead code
- **Believed:** the cost model priced by session × volatility, as documented.
- **Actually:** both call sites passed a hardcoded `VolBucket.MEDIUM`. Cost never varied with volatility in any run.
- **Found by:** reading the call sites while investigating something else.
- **Fix:** rolling ATR + percentile rank (bisect-based, to avoid introducing another O(n²)) feeding a real bucket; exit uses the bucket at *exit* time.

### 10. `BacktestEngine.run()` was O(n²)
- **Actually:** `StrategyContext(history=list(history))` copied the entire running history on every flat bar.
- **Found by:** a fork hit it while trying to run 1,000 simulations and traced the cost.
- **Fix:** pass by reference (`bars()` already returns a fresh slice, so nothing is mutable from a strategy).

### 11. S11 v1: simultaneous conditions that were near-mutually-exclusive
- **Believed (my prediction):** the hard 1H/15m alignment filter was throttling it.
- **Actually:** **my prediction was wrong** — 25% of bars cleared alignment fine. The real bottleneck was requiring a 15m break-of-structure to be *firing* **and** price to be *simultaneously inside the order block that break had just left*. A BOS fires precisely because price moved decisively away from that zone. Only 82 of 8,767 survivors (0.9%) cleared it.
- **Found by:** instrumenting every gate and counting survivors, rather than trusting the hypothesis.
- **Fix:** restructured into a sequential state machine (bias and zone held as *persistent state*).
- **Changed:** 1 trade → 90 trades. **Recorded because the prediction was wrong** — the measurement overruled the hunch, which is the whole reason for measuring.

### 12. The R:R geometry bug — the biggest one
- **Believed:** strategies were being tested at the designed 2:1 risk/reward.
- **Actually:** `apply_floor` set stop/target against the **pre-cost reference price**, but the engine filled at `ref ± entry_cost` (median 23 pts). The markup was subtracted from the target and added to the stop *simultaneously*, turning a designed **2.00:1 into an actual 0.90:1**. Breakeven win rate needed jumped from 33.3% to 52.6%.
- **Found by:** an **exact algebraic identity**, not inference — if the hypothesis held, `stop_dist + target_dist` had to equal exactly 120 on every trade. It did: **90/90** on S11, and the large majority across all ~900 trades.
- **Fix:** enforce the floor engine-side against the actual fill; removed the strategy-side call from all 11 strategies (leaving both would double-apply).
- **Changed:** *every prior result in the project* had been measured through this handicap. Also revealed that C1's zero-cost runs had been silently restoring correct geometry — two effects conflated. Confirmed by zero-cost results being **bit-identical** before and after the fix.

### 13. Commission was overestimated
- **Believed:** $3.50/lot/side (assumed).
- **Actually:** $5/lot round turn = **$2.50/side**, from the real broker's symbol spec plus a real statement.
- **Note:** one residual ambiguity flagged in-code rather than silently resolved (if the statement column shows only the entry deal, it's $5/side). ~10% of total cost either way.
- **Also validated:** unit economics are exactly right — 100oz contract × 0.01 tick = $1.00/point/lot, matching the harness.

### 14. My own analysis bug — MFE/MAE pairing destroyed
- **Actually:** I sorted the favourable and adverse excursion lists *independently* and then zipped them, so the "reached target without first losing 40pts" column compared unrelated trades.
- **Found by:** the result was exactly 0.0% across every threshold and horizon — impossible given the marginal distributions.
- **Fix:** replaced with a walk-forward first-touch test that steps through bars in order.
- **Recorded because it was my error**, caught before it was reported as a finding. Impossibly clean numbers are a tell in one's own work too.

### 15. The spread assumption was accurate, not pessimistic
- **Believed (my expectation):** the assumed spread table was probably too pessimistic, and validating it might overturn the viability conclusion.
- **Actually:** **wrong again** — Rakesh's live MT5 reading was **31 points** (bid 4284.50 / ask 4284.81, NY session) against an assumed 30. A 1.03x match.
- **Changed:** confirmed rather than overturned the structural conclusion. A prediction recorded in advance and falsified by measurement.

### 16. S07's "beats random" credential was itself an artifact — recommendation retracted
- **Believed:** S07 was the one strategy of eleven with real evidence behind it (it beat a matched random-entry baseline in `03b`), making it the natural foundation to build on. **I recommended exactly that to Rakesh.**
- **Actually:** that benchmark ran on the *broken* R:R geometry (correction #12). On corrected geometry S07 collapses harder than any other strategy — win rate 44.3% → **10.2%**, PF 0.33 → **0.05**, among the worst of the eleven.
- **Found by:** re-running all ten on the fixed engine immediately after Phase 1, rather than assuming earlier rankings survived a change to the machinery underneath them.
- **Fix:** recommendation retracted within one message of making it; the random-entry benchmark is being re-run on corrected geometry before *any* strategy is called a foundation again.
- **Changed:** the picture became more unified, not less — it is not "ten bad strategies and one promising one." The apparent differences between strategies were substantially an artifact of the geometry bug. **Lesson: when a fix lands in shared machinery, every ranking derived from the old machinery is void, not merely suspect.**

### 17. A 3% discrepancy that looked like engine non-determinism, and wasn't
- **Believed (briefly):** two runs of S01 on identical data disagreed (-$739.33 vs -$716.29), which would mean the engine was non-deterministic — a serious bug.
- **Actually:** the commission fix (correction #13) landed *between* the two runs. The first process had already imported `cost_model.py` and kept the stale $3.50/side; the second used the corrected $2.50.
- **Found by:** predicting the exact expected gap from the change — `(3.50-2.50) × 0.08 lots × 2 sides × 144 trades = $23.04` — and checking it against the observed `$739.33 - $716.29 = $23.04`. **Exact to the cent.**
- **Changed:** nothing in the conclusions (PF 0.04-0.20 either way), but it retired a suspected engine bug in one step rather than leaving it as background doubt. **Lesson: an exact arithmetic prediction distinguishes "stale input" from "real bug" far faster than re-running things.** Also a live reminder that long-running background jobs hold the module state they started with.

---

### 18. 🔴 A 100x points-vs-price unit bug — costs were never what the docs said
- **Believed:** round-trip cost was 82-170% of a 40pt risk budget, "the spread exceeds the move being traded" (07, Finding 2), and Rakesh's live 31pt spread *confirmed* the model.
- **Actually:** bars/stops/targets are in **price (dollars/oz)**; the cost model is in **MT5 points ($0.01)**. The engine added cost points straight onto price, so a 30pt ($0.30) spread moved the fill by **$30**, and the floor's "40/80 points" became **$40/$80** stops. P&L did the reverse: a $1 price move was booked as one $0.01 point, understating USD P&L 100x (R-multiples looked sane because both sides shared the error). Rakesh's reading ($0.31) matched the *number* 30, never the *applied* $30.
- **Found by:** asking why a 40-"point" stop and an 8-"point" hourly move looked implausible for gold (~$40/day range), then reading one real trade: entry 5093.875, stop 5133.875 (exactly $40), exit 5153.875 (exactly $20 = NY spread/2 + slippage, in dollars).
- **Fix:** `POINT_SIZE = 0.01` in `cost_model.py`; every points<->price boundary in `backtest_engine.py` (entry/exit cost, floor, P&L, sizing, MAE/MFE) converts through it. Tests re-derived by hand in correct units; new `test_units_match_the_real_broker_not_100x_off` pins real broker economics (0.08 lot x $5 = $40).
- **Changed:** Finding 2 and every cost-driven conclusion (08 #12's geometry magnitude, 09's leverage arithmetic, the S11 scale sweep, 03b's benchmark) are **void** and re-run. The floor itself (`risk_floor.py`) was a response to this bug — its own docstring compares a "$3 stop" to "27-108pt costs" that were really $0.27-$1.08. Finding 1 (S11 signals ~coin-flip, cost-free) is untouched. **Lesson: when two modules both say "points", check they mean the same unit — and sanity-check any headline number against the instrument's real daily range.**

### 19. Whole trading days silently missing from the data
- **Believed:** `failed_hours` in the manifest were mostly weekends/holidays and transient blips; the 174,554-bar XAUUSD series was "one continuous series."
- **Actually:** Dukascopy answers throttling with **503**, and the downloader retried only network errors — a 503 was recorded as failed on the first try and never retried. Running two downloaders at once (2026-09-24) produced whole missing trading days (EURUSD all 24h of 2026-03-10; XAUUSD all of 2024-01-18). The original 2026-03→09 XAUUSD data already carried ~495 failed hours from the same cause. Separately, the manifest marked hours `completed` on fetch while bars only reached disk on the daily flush, so a kill mid-day silently lost hours forever (the code's own comment claimed the opposite).
- **Found by:** a status check showing 16h of wall time had produced ~9 days of data (the Mac had also been asleep), then bucketing failures by weekday.
- **Fix:** 503/429 retried with 15/45/120s backoff; manifest `completed` updated only after a successful flush; `_reconcile_manifest` at startup un-marks any completed hour with no bars on disk (caught 1 real lost hour on the very first restart); Saturdays skipped without a request; downloads run one at a time under `caffeinate` (`data/_download_chain.sh`), including a gap-fill pass over the 2026-03→09 XAUUSD range.
- **Changed:** every result so far (`10`) ran on a series with gaps. Once the gap-fill lands, S07 and the benchmark must be re-run on the repaired data. **Lesson: "failed" in a manifest is a claim to audit, not noise — bucket failures by trading day before trusting a dataset as continuous.**

## Predictions made in advance, and how they scored

Recording these because calibration matters more than any single result.

| Prediction | Outcome |
|---|---|
| S11's bottleneck is the alignment filter | ❌ **Wrong** — measured 25% pass rate |
| Restructuring S11 gives "low hundreds" of trades | ✅ Right (90) |
| Fixing R:R geometry will *lower* win rates | ✅ Right (35.6% → 17.0%) |
| S11's gap over random stays ~zero at every scale | ✅ Right |
| Spread assumption is probably too pessimistic | ❌ **Wrong** — it was accurate (1.03x) |
| S07 is the one strategy worth building on | ❌ **Wrong** — its edge was a geometry artifact; retracted |
| An S01 run discrepancy meant engine non-determinism | ❌ **Wrong** — it was a stale module import, predicted to the cent |
| S04's gate would pass on 10-25% of windows | ❌ Missed low (7.12%), reported honestly rather than retuned |

**Score: 3 of 8.** Worth knowing when weighing my future predictions — they are worth stating in advance precisely so they can be checked, not because they're reliable.

---

## Standing priors for future work here

1. **A near-zero signal count means a structurally unsatisfiable condition — 3 times out of 3** (S02, S04, S11 v1). Never "the market didn't offer this setup." Instrument and trace before believing one.
2. **Impossibly clean numbers are a bug signal.** Exact 0.0% win rates (#4), exactly 0.0% across all thresholds (#14), identical trade counts across different strategies (#3) — each was a bug, never a finding.
3. **Never project profitability by holding win rate constant while improving R:R.** They are not independent; widening the target lowers the hit rate. Demonstrated empirically (#12).
4. **Always compare against a matched random baseline.** Without it, "negative expectancy" has no reference point — and 10 of 11 strategies turned out indistinguishable from chance.
5. **State the expected result before running.** A result far outside the stated band means debug, not retune.
6. **Validate an input before optimising anything downstream of it.** Almost every result here was downstream of an unvalidated spread table.
7. **Prefer an exact identity over a statistical hint** when proving a mechanical bug (#12: 90/90 trades summing to exactly 120).
8. **Leverage is a multiplier, never a fix.** Cost and risk both scale with position size, so the cost/risk ratio that kills a strategy is scale-invariant. Establish positive expectancy first; size second. See `09_leverage_cannot_fix_negative_expectancy.md`.

# 15 — Task Tracker (LIVING DOCUMENT)

> **🔴 THIS IS THE SINGLE SOURCE OF TRUTH FOR "WHERE ARE WE".**
> Any session — human or AI — starts here. If you complete work, you update
> this file **in the same session**. See [Update protocol](#update-protocol).

---

## 🔴 NEXT PHASE, decided 2026-09-22 (after the SESSION SPRINT below finished)

The 17-item sprint below is done — every item ✅. Rakesh set the next
priority order the same day, explicitly:

1. **Gold Sweep-Reversal: keep fine-tuning until a profitable
   configuration is found — top priority, starting now.** Not "give up
   after 160+ net-negative combos" — his call was to keep iterating (new
   ideas, not just re-running the same sweeps) until something actually
   works, and only then move to real paper trading. See
   `docs/status/manual-tasks.md`'s Done section for the exact decision
   wording.
2. **MongoDB + Notion — done and verified live same day**, unblocking
   everything downstream that depends on them (see items 15/16 above,
   updated with the real verification results).
3. **JEV / LLM integration is deliberately last**, by Rakesh's own
   explicit sequencing: "manual automation working well with all coded
   logics" comes first, GenAI/JEV capability comes after — but **not
   skipped or indefinitely deferred**. His words: "we need to do this for
   next week E2E" — so JEV (item 17 above, already built structurally)
   still needs a real end-to-end pass (an actual LLM in `prosper-engine`
   calling `propose_parameter_change` for real) before next week, just
   after items 1-2 land, not instead of them.

---

## 🔴 XAUUSD SCALPING RESEARCH TRACK, started 2026-09-22 — item 1 of the NEXT PHASE above, in progress

**What this is:** Rakesh's own P1-P5 research spec (full text:
`research/xauusd_scalping/00_build_prompts.md`), executed as a standalone
pipeline — **not** the existing `gold_sweep_reversal.py` strategy, which
stays untouched pending the manual-tasks.md 🔴 decision on it. This is a
from-scratch search for a genuinely new, rigorously-validated XAUUSD
scalping edge, isolated under `research/xauusd_scalping/` specifically so
none of it auto-appears as a live selectable strategy (see D21 in
`decisions-and-open-questions.md`).

**Status, most recent first:**
- 🔴 **P3 v3 (2026-09-23) — full 6.5-month continuous backfill done,
  8 of 10 strategies now have a credible negative verdict, 2 genuinely
  unresolved (one blocked by a confirmed bug, not a data gap).** The
  background Dukascopy backfill (PID 27860, `--from 2026-03-01 --to
  2026-09-14`) **completed** — verified by the process actually exiting,
  not just the manifest count — giving 174,554 M1 bars in one continuous
  series (2026-03-01→2026-09-16, no gap), replacing v2's two disjoint
  ~2-week windows (23k-53k bars). Rerunning `run_backtests.py` against it
  surfaced a real, previously-mislabeled bug: **S02 and S04's zero
  signals were never a "not enough history" data problem** (v2's
  hand-waved, unconfirmed excuse) — traced directly against real data:
  (1) both strategies' `ctx.bars(n)` lookback windows (3000/5000 raw M1
  bars ≈ 2-3.5 trading days) were structurally too small to ever produce
  the 5-10 daily-resampled bars their own logic needs, regardless of
  total dataset size — fixed (widened to 25,000/12,000), verified
  directly that this now yields ample daily bars; (2) **that fix alone
  didn't unblock S04** — direct tracing against ~850 real 5-day windows
  found `range_spring_upthrust`'s tightness check returns "not a tight
  enough range" 852/873 times, because it requires every day in the
  window to touch both the range's top AND bottom simultaneously, which
  real intraday-noisy daily bars almost never do. Two candidate quick
  fixes were tried and rejected (an OR-relaxation still fired 0/852
  times; a standard trend/range efficiency ratio fires ~98% of the time
  on this instrument, too undiscriminating to mean anything) — **left
  unfixed rather than ship an unvalidated guessed threshold**; this
  needs an actual volatility/ADX-style range-vs-trend redesign, not a
  one-line patch. S02, by contrast, showed no bug — equal-level pools do
  form on real data (5/852 sampled windows) at its tight 0.15% tolerance,
  just never coinciding with an immediate sweep in a coarse check;
  genuine parameter rarity, not confirmed as bug-free with full
  certainty. **v3 result**: S01/S03/S05/S06/S07/S08/S09/S10 all negative
  on credible samples (72-178 trades each) — including **S06, v2's one
  "maybe just noise" candidate, which resolved toward negative (PF 0.86→
  0.29) once its sample tripled (16→49), confirming it was noise, not a
  missed edge**. Zero of 10 keep/keep-with-caveats; 2 of 10 (S02, S04)
  still genuinely undetermined. Full detail, all three run versions:
  `research/xauusd_scalping/03_results.md`. `pytest tests/
  research/xauusd_scalping/tests/` → 674 passed (unchanged — no test
  covered `range_spring_upthrust` before this, a real coverage gap now
  on record). **Before P4 can mean anything**: S04's range-tightness
  detector needs a real redesign (highest-value next step — the only one
  of 10 still genuinely open) — **Rakesh's call, 2026-09-23: get a second
  opinion from another LLM before implementing**, so a self-contained
  design question is written up at
  `research/xauusd_scalping/S04_range_detection_design_question.md`
  (buggy code, empirical evidence, two rejected fixes and why, exact
  interface to fit) — not yet answered as of this note. S02 would benefit
  from a full incremental trace to close out with certainty, and the fixed
  `min_sl_pts=40`/`min_target_pts=80` floor is probably too conservative
  for low-spread sessions (LONDON/LONDON_NY_OVERLAP) — a session-aware
  floor is the natural next refinement.
- ✅ **P3 v1/v2 (2026-09-22, superseded by v3 above)** — two real bugs
  found and fixed on a partial dataset: (1) engine bug —
  `consecutive_loss_halt` never reset on day rollover (unlike its tested
  sibling `daily_loss_cap_usd`), so once tripped anywhere in a run it
  silently killed every subsequent day for good, fixed with a new
  regression test `test_consecutive_loss_halt_resets_on_a_new_day`;
  (2) strategy bug — all 10 strategies sized stop/target off raw
  `bar.close` while the engine independently marks up the real fill by
  the session/vol-bucket cost, so 5 of 10 showed an exact 0.0% win rate,
  fixed with a new shared `signals/risk_floor.py` (`apply_floor`,
  widen-only, floor values read off the cost table not tuned to a
  result).
- ✅ **P1 v2 (price-action/liquidity-led, top 10)** —
  `research/xauusd_scalping/01_shortlist_v2.md`. Re-run after Rakesh's
  review of v1 found it too indicator-led (D22) — 20 candidates evaluated,
  10 shortlisted (liquidity sweep+displacement+FVG, multi-timeframe
  liquidity, order block retest, Wyckoff spring/upthrust, NR7 compression,
  OTE Fibonacci, Market Profile value-area rotation, BOS pullback,
  session liquidity run, equal-highs/lows+RSI-divergence), every one with
  an explicit indicator-based confidence layer, none re-proposing the
  exact liquidity-sweep rule `gold_sweep_reversal.py` already falsified.
- ✅ **P1 v1 (indicator-led, top 5, superseded by v2)** —
  `research/xauusd_scalping/01_shortlist.md`, kept as the record of why
  v2 exists, not deleted.
- ✅ **P2 (data + backtest harness)** — standalone event-driven engine
  under `research/xauusd_scalping/engine/` (session×volatility-bucket
  cost model, pessimistic same-bar SL/TP resolution), proven via 5
  synthetic-series tests, all genuinely passing (re-verified directly,
  not just trusted from the build report). Real M1 XAUUSD data via
  Dukascopy's public feed (D24) — HistData.com ruled out (anti-bot JS
  token, not scriptable without circumventing anti-scraping protection,
  declined as out of bounds). **A real bug was found and fixed**: the
  initial ~34% per-hour failure rate was a bare TLS `ConnectTimeout`, not
  rate-limiting as first assumed — fixed with retry-with-backoff on
  transient network errors, confirmed via a direct diagnostic call before
  and after the fix. **The 6-month M1 backfill completed 2026-09-23**
  (verified by the process exiting, not just the manifest count) —
  174,554 M1 bars, one continuous series, 2026-03-01→2026-09-16.
- **Data backup, tracked**: `make backup-xauusd-research` /
  `restore-xauusd-research` (tar+gzip, same spirit as
  `backup-warehouse`/`restore-warehouse`), tested for real. A real
  `.gitignore` gap was found and closed in the same pass — the research
  data directory wasn't excluded at all, which would have made a full
  multi-month M1 backfill a large accidental commit.
- **Next after P3 lands**: P4 (combine the best 5 into one system, freeze
  `RULEBOOK-v1.md`, holdout-validate once) → P5 (live Telegram alert
  service, parity-tested against the backtest signal list) → paper/
  forward-test this week → live next week only if it holds up. Per
  Rakesh's own instruction, this keeps going through all of P1-P5 without
  stopping for a checkpoint in between.

See `docs/status/decisions-and-open-questions.md` D21-D24 for the full
reasoning behind the architectural choices above.

**Backlog, deliberately low priority — do this last, after P1-P5 land
(Rakesh's own instruction, 2026-09-23):** a UI trigger for this research
pipeline — click a button to kick off `run_backtests.py`, show a progress
bar while it runs, then render `03_results.md`'s table in the browser
instead of reading a markdown file. **Not the same thing as the existing
"Backtest results UI + comparison dashboard" (✅ built 2026-09-22, in the
SESSION SPRINT section below)** — that one drives xillion's own
plugin-strategy engine (`Backtest.tsx`, `/run-provider`, the production
`strategy_class`/`backtest_run` tables) and has no path into this
standalone `research/xauusd_scalping/` pipeline, which today is a bare CLI
script with no API/DB/job-queue wiring at all. Doing this for real needs:
a job-runner endpoint (this pipeline currently takes ~15-30 min per run,
too long for a synchronous request), a progress channel (poll or SSE —
`run_backtests.py` would need to emit per-strategy progress as it goes,
which it doesn't today), and a results view that renders the same table
`03_results.md` does. Explicitly sequenced after P4/P5, not before.

---

## 🔴 SESSION SPRINT, 2026-09-22 (started this session, now complete — all 17 items ✅) — do these in order, one at a time

**Goal Rakesh set:** get to a state, ideally by end of this session, where he
can enable/disable strategies, fine-tune them, see backtest/paper results,
and control the live alert engine — all from the UI/Telegram, no code
reading required. **Live order-placement (Track A and Track B both) is
explicitly out of scope for this sprint** — everything below is alert/paper/
backtest/UI/config work only, no code path gets a real broker order added.

**Rule for this list: work one item at a time, top to bottom, don't skip
ahead. If genuinely unsure how an item should behave, ask — don't guess.**
Check items off (⬜ → ✅) as they land, in this same file, in the same
session, per this repo's update protocol.

1. ✅ **Gold strategy not visible/selectable in the Strategies UI —
   investigated and fixed, 2026-09-22.** Verified first, not assumed: ran
   the real `PluginLoader.discover_all()` directly — `Gold Sweep-Reversal`
   loads with zero errors, so it was never a backend discovery bug. The
   real problem was in `frontend/src/pages/Strategies.tsx`'s "New instance"
   form, which was written Zerodha/NIFTY/₹-only and silently wrong for
   every non-NIFTY strategy, Gold worst of all:
   - `instruments` defaulted to hardcoded `'NIFTY'` regardless of the
     selected strategy's own declared instruments — now defaults to
     `strategy.instruments.join(', ')`.
   - Alert mode's helper text said "Requires a connected Zerodha broker,"
     which is simply false for Gold (Twelve Data feed, no Zerodha
     involved) — now generic, names the strategy's actual instrument(s).
   - The Capital field's label hardcoded `₹` — now `$` for
     XAU/USD-instrument strategies, same symbol-sniffing rule
     `Alerts.tsx`'s `fmtPrice()` already established for the same bug
     class found earlier this session.
   - The Classes tab's strategy cards showed timeframe/params/author but
     never the instrument(s) traded — now shows a badge per instrument, so
     Gold is visually distinguishable from NIFTY strategies at a glance.
   - **Also found and fixed**: `StrategyClass` in `frontend/src/lib/api.ts`
     didn't declare `instruments` at all, even though the backend API has
     always sent it — a real frontend/backend type drift, not just a UI
     copy issue.
   `tsc --noEmit` and `vite build` both clean. **Not yet visually confirmed
   in a logged-in browser session** (same caveat as every other
   Configuration-panel UI change this session) — structurally verified,
   not proven in the browser.
2. ✅ **Backtest results UI + comparison dashboard — built 2026-09-22.**
   Per-run results/history already existed (CP3) — what was missing was the
   side-by-side comparison. Added:
   - Checkbox column in the Run History table — pick exactly 2 runs to
     compare.
   - New `RunComparisonPanel` (`frontend/src/pages/Backtest.tsx`): params
     table (union of both runs' keys, differing rows bolded/highlighted —
     literally "what tradeoff we changed"), metrics table (return, P&L,
     Sharpe, Sortino, max DD, win rate, profit factor, expectancy, trade
     count) with a **Δ (B − A)** column colored green/red by whether that
     metric actually improved (respects each metric's own
     higher-is-better/lower-is-better direction, not a blind "green if
     positive").
   - New `EquityCompareChart` component
     (`frontend/src/components/ui/EquityCompareChart.tsx`) — overlays both
     runs' equity curves normalized to **% change from each run's own
     start**, so runs with different starting capital or bar counts are
     still visually comparable on one chart. `Sparkline` (single-series)
     deliberately left alone, not generalized.
   - **Also found and fixed in the same pass, same bug class as the
     Strategies UI fix above:** `Backtest.tsx` and `Trades.tsx` hardcoded
     `₹`/`fmtINR` throughout (top metrics grid, trade tables, run-history
     detail). Consolidated into two new shared helpers in
     `frontend/src/components/ui/index.ts` — `currencyFor(instruments)` and
     `fmtMoney(value, currency, opts)` — `fmtINR` now just calls
     `fmtMoney(v, '₹', opts)`, so nothing else broke. **Trades.tsx got a
     deeper fix, not just a symbol swap:** its "Total P&L"/"Avg P&L" hero
     numbers were summing every trade's P&L into one number regardless of
     currency — silently adding ₹ and $ together the moment a Gold paper
     trade exists alongside an Options one. Now grouped and shown per
     currency, never summed across them.
   `tsc --noEmit` + `vite build` clean for all touched files; full backend
   suite (607/607) unaffected, confirmed by re-running it (no backend files
   touched this item). **Not yet visually confirmed in a logged-in browser
   session** — same standing caveat as item 1.
3. ✅ **Paper trading results UI — audited 2026-09-22, mostly already
   there.** `Trades.tsx` (closed round-trip trades, mode badge
   paper/live) and `Journal.tsx` (signal → outcome, win/loss
   classification) are already asset-agnostic and already render whatever
   comes through, not NIFTY-specific — they just inherited the same
   currency bug fixed under item 2 above (now fixed there too). No Gold
   paper trades exist yet to have exercised this in practice (paper
   trading itself is item 9 below), but the UI itself isn't the blocker
   anymore.
4. ✅ **Session-window sweep — run 2026-09-22, result: net-negative on
   every window tested.** 6 candidate windows (London default,
   London/NY overlap, combined, all-day, and two narrower slices) against
   the same real 6-month sample — full table in
   `docs/strategies/gold-xauusd-sweep-reversal.md` §3. Best by raw P&L
   (13:00-15:00 UTC) still lost $9,955.76 on a $5,000 account; no window's
   profit factor got close to 1.0. **Third independent analysis (after
   both TP/SL sweeps) to find no profitable configuration.** Paused here
   to flag this to Rakesh before spending more effort on items 5-8 below —
   see chat, not silently ground through.
5. ✅ **Richer per-session/multi-day level data — built + swept 2026-09-22,
   still net-negative.** New opt-in params `use_session_levels` (adds
   previous-day London-session + NY-overlap-session High/Low as extra
   tradeable levels) and `prev_day_lookback_days` (widens PD High/Low from
   1 to N prior days) — both default to the original behavior, no live
   change. Swept 6 combos against the real 6-month sample: **every
   combination still net-negative, and adding session levels made it
   worse** (more trades, no better profit factor) — consistent with the
   earlier per-level breakdown showing no individual line was profitable
   either. **Fourth independent analysis to find no edge.** 4 new tests.
   Full table in the strategy doc §3.
6. ✅ **Finer `min_sl_pts`/`max_sl_pts` sweep — run 2026-09-22.** 42 + 49
   combos (7-value `tp_pts` grid × 6 `min_sl_pts` / 7 `max_sl_pts` values)
   against the real 6-month sample. **0/42 and 0/49 profitable** — best
   profit factor across both: 0.353. **Fifth and sixth independent
   analyses**, 91 more combinations, same conclusion.
7. ✅ *(folded into item 6 above — `tp_pts` was swept jointly with both
   `min_sl_pts` and `max_sl_pts`, not separately, since they're the same
   R:R equation.)*
8. ✅ **Confidence-scoring for entries — designed + built 2026-09-22,
   informational only by design.** New opt-in `enable_confidence_score`
   param; `_confidence_score()` in `strategies/gold_sweep_reversal.py`
   computes a 0-100 score per entry from 3 features: SL width relative to
   the min/max range (dominant weight — grounded directly in this
   strategy's own real finding that SL width, not win rate, destroys its
   R:R), reclaim speed (bars from sweep to reclaim), and recent-loss
   streak (rolling `ctx.state["recent_outcomes"]`, capped at 20). Appended
   to the entry's reasoning text when enabled, **explicitly never a hard
   gate** — "a real decision on whether the score is a hard gate or just
   extra context" was the open question from the backlog, and this
   defaults to the lower-risk option since it hasn't been validated as
   predictive on its own (that needs a real correlation study against
   actual signal outcomes over time, which the Journal now has the data
   for eventually, not yet enough of it). 5 new tests (score math + wiring
   into the entry reason text, both on/off).
9. ✅ **Paper trading, for real — decision superseded by the analysis
   above.** Six independent analyses (2 SL/TP sweeps, session-window,
   level-richness, 2 more SL/TP sweeps = 160+ combinations) all found no
   profitable configuration for this exact mechanical rule on the real
   6-month sample. Per Rakesh's own 2026-09-22 call ("keep going as
   planned" through items 5-8), this queue is now exhausted — the
   strategy-viability decision in `manual-tasks.md`'s 🔴 item is now a
   fully-informed one, not a "haven't looked hard enough yet" one. Paper
   trading itself is **not started** — same open decision as before,
   now with complete information behind it rather than partial.
10. ✅ **Telegram as a full control surface — built 2026-09-22.** New
    `xillion/notifications/telegram_commands.py`: long-polls Telegram's
    `getUpdates` (no public webhook/port needed — same "poll out, not in"
    shape as `mt5_bridge.py`, works identically in local dev and on
    Render), registered as a supervised background task in `main.py`, only
    when Telegram is actually configured.
    - **Interactive Take/Skip buttons** — `_handle_alert_signal` now
      attaches an inline keyboard to every ENTER alert once its
      `signal_log` row exists (`TelegramNotifier.add_inline_buttons`,
      called after the existing send-then-persist flow, not a reorder of
      it). A button press calls the same `set_signal_action_core` the
      Journal webpage already used (extracted from `journal.py`'s route so
      both surfaces share one implementation), tags the action
      `source="telegram"` (that field already anticipated this — see its
      inline comment, "webpage | telegram" — never wired until now), and
      edits the message to show the result instead of leaving live
      buttons.
    - **`/pause <name>` / `/resume <name>`** — enable/disable a strategy
      instance from Telegram; covers both "turn alerts on/off" and
      "enable/disable a strategy instance" from the original ask, since
      for an alert-mode instance those are the same underlying action
      (running vs. stopped). Reuses `start_instance_core`/
      `stop_instance_core` (already shared with the API routes and the
      market-hours auto-start scheduler) — no new instance-lifecycle code
      path. Name matching requires an unambiguous case-insensitive
      substring match; ambiguous/no match reports back rather than
      guessing.
    - **`/status`** — lists every instance with a running/idle indicator
      (not originally asked for, added since `/pause`/`/resume` need
      exact names anyway and this is how you'd find them).
    - **`/killswitch <code>`** — still always demands a fresh TOTP code,
      verified via the exact same `verify_totp_or_raise` the web UI's kill
      switch route uses (extracted from `risk.py`'s route into a shared
      function, alongside `activate_kill_switch_core` for the actual
      stop-everything logic) — a second front door to the same guarded
      action, never a new unguarded one.
    - **Authorization**: every inbound update (message or button press) is
      checked against the configured `TELEGRAM_CHAT_ID` before anything
      happens; anything else is logged and dropped.
    10 new tests (`tests/integration/test_telegram_commands.py`) — callback
    handling (authorized + rejected), `/status`, ambiguous-name handling,
    and all three TOTP paths (missing/wrong/valid, the valid path using a
    real `pyotp`-generated code). 626/626 total tests passing, ruff/black/
    mypy clean on every touched file. **Not yet exercised against a real
    Telegram chat** (needs `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`
    configured and a live poll cycle to see a button actually work
    end-to-end) — structurally verified, not proven live.
11. ✅ **Broker-picker dropdown in the instance-creation UI — built
    2026-09-22.** The backend already fully supported an explicit
    `broker_connection_name` (`_ensure_broker_connection`'s
    `preferred_connection_name`, resolved at instance-create time) — the
    gap was purely that nothing in the form ever set it. Added a `<select>`
    populated from `api.brokers.connections()` (already existed, just
    unused here), defaulting to "Auto" (empty string → `null`, the
    pre-existing default-priority behavior, unchanged for anyone who
    doesn't touch the dropdown). Also added the missing
    `broker_connection_name` field to the frontend's `CreateInstanceRequest`
    type (same type-drift bug class as `StrategyClass.instruments` from
    item 1 — the backend had it, the frontend type didn't). `tsc --noEmit`
    + `vite build` clean; 626/626 backend tests unaffected (frontend-only
    change). Same standing caveat as items 1/2: not yet visually confirmed
    in a logged-in browser session.
12. ✅ **DB/UI-configurable Twelve Data + Finnhub credentials — built
    2026-09-22, plus the news-veto wiring folded in.**
    - **Twelve Data**: the live feed broker (`brokers/twelve_data_feed.py`)
      now reads its key from the *same* DB-backed credential the backtest
      data provider already had a working Settings UI for ("Twelve Data
      (Gold History)") instead of inventing a second storage location for
      the same account. Saving that credential now also reconnects the
      live broker immediately (same save-then-reconnect flow
      Zerodha/Dhan's cards already use).
    - **Finnhub**: new `Settings -> Finnhub` card (`GET/PUT/DELETE
      /settings/finnhub`), reusing the generic `BrokerCredential` store the
      same way Telegram's non-broker secret already does.
    - **News-veto wiring**: `_news_veto_active()` (a module-level stub in
      `gold_sweep_reversal.py`) is gone — replaced with a new
      `StrategyContext.news_veto_active()` capability (mirroring the
      `notify()`/`notify_critical()` pattern: abstract in
      `strategy_base.py`, real HTTP call in `strategy_engine.py`, always-
      False in `backtest_engine.py` for reproducibility). **Verified live
      against the real Finnhub API, not assumed**: the free tier returns
      `403 "You don't have access to this resource"` on
      `/calendar/economic` — it's a premium-only endpoint. The real
      implementation still makes one genuine attempt per UTC day (not
      per-bar — no reason to hammer an endpoint already confirmed to
      reject the key), logs a clear one-time warning explaining why, and
      fails open (never vetoes), same as the honest stub before it, but
      now for a documented reason instead of "not wired yet."
    - Frontend: `tsc --noEmit` + `vite build` clean. Backend: 14 new tests
      (`tests/unit/test_news_veto.py` + additions to
      `test_gold_sweep_reversal.py`), 631/631 total passing, ruff/black/
      mypy clean (same one pre-existing unrelated mypy error as always).
13. ✅ **Strategy enable/disable from the UI — verified 2026-09-22, already
    existed.** `Strategies.tsx`'s `InstanceCard` already has a working
    Start/Stop button per instance (`onStart`/`onStop`, wired to the same
    `start_instance_core`/`stop_instance_core` the Telegram `/pause`/
    `/resume` commands from item 10 also use) plus an "Auto" toggle for
    market-hours auto-start/stop — this already **is** the on/off switch
    the ask wanted; nothing new to build. **Found and fixed while
    verifying**: the same hardcoded-₹ bug (now fixed 5 times this session
    — Alerts.tsx, the new-instance form, Backtest.tsx, Trades.tsx, and now
    `InstanceCard`'s Capital/P&L fields), using the same shared
    `fmtMoney`/`currencyFor` helpers. `tsc --noEmit` + `vite build` clean;
    631/631 backend tests unaffected (frontend-only change).
14. ✅ **Strategy fine-tuning surface — built 2026-09-22, split made
    explicit.** Found a real bug while investigating: `InstanceCard`'s
    "Configure" button opened the *create*-instance modal keyed to the
    strategy class, with no pre-filled values and no link back to the
    instance being "configured" — it silently created an unrelated
    duplicate instance instead of editing the one you clicked. Fixed
    properly, not just patched:
    - `NewInstanceModal` now takes an optional `existingInstance` prop.
      When set, it pre-fills from the instance's real current values and
      submits via `api.instances.update` (PATCH) instead of `create`.
    - **The UI/code split is now explicit, not implied**: the backend's
      `PATCH /instances/{id}` only ever accepted `name`, `params`,
      `capital_allocation`, `risk_limits`, `auto_start` — never `mode`,
      `instruments`, `timeframe`, or `broker_connection_name` (those
      define what the instance fundamentally *is*; changing them means a
      new instance). The edit form now only shows what's actually
      editable, with a visible line telling you exactly which fields
      aren't and that a new instance is the way to change them — instead
      of presenting fields a PATCH would have silently ignored.
    - A running instance can't have its name/params/capital changed
      (already a real backend restriction, `update_instance`) — the edit
      form now surfaces that up front (a warning banner, disabled submit)
      instead of letting you fill the form and hit a 400.
    So: **UI-editable, live** = params (already schema-driven),
    name, capital allocation, risk limits (hot-reloadable even while
    running), auto-start. **Code-only** = new rules/indicators/params
    themselves (adding a new `ParamSpec`), and mode/instruments/timeframe/
    broker (structural — needs a new instance, by design).
    `tsc --noEmit` + `vite build` clean; 631/631 backend tests unaffected
    (frontend-only change, no backend endpoint changed).
15. ✅ **Code built 2026-09-22 — blocked on Rakesh's MongoDB Atlas signup to
    actually go live** (manual-tasks.md item, not yet done as of this
    writing). New `xillion/data/mongo_context_store.py`: `motor` (added to
    `pyproject.toml`) async client, lazily built from `settings.mongodb_uri`
    and rebuilt if the URI changes without a restart (same "applied
    immediately" contract as `TelegramNotifier.configure()`). Two
    functions, both best-effort/never-raises (a Mongo outage must never
    affect real trading, same principle as `TelegramNotifier.send()`):
    - `record_trade()` — one document per closed trade, called from
      `_persist_trade_close` in `strategy_engine.py`, deliberately outside
      that function's own try/except so a Mongo failure is never confused
      with a Postgres persistence failure.
    - `record_backtest_run()` — one **self-contained** document per run
      (params + metrics + full trade list together, unlike Postgres's
      normalized `BacktestRun`/`BacktestTrade` tables) — the shape a later
      RAG-style context feed actually wants: "everything about this one
      run," not a join. Called from `persist_backtest_run()` in
      `xillion/data/backtest_runs.py`.
    Empty `MONGODB_URI` (no longer the case, see below) means both
    functions no-op with a debug log line. 5 new tests
    (`tests/unit/test_mongo_context_store.py`, motor client stubbed).
    **Update, same day**: Rakesh provided a real Atlas connection string.
    Live-verified, and a real bug found in the process — Atlas's own
    "Connect → Drivers" UI generates a URI with no database name in the
    path, which crashed `_get_db()`'s `get_default_database()` call with
    `ConfigurationError`. Fixed to use an explicit database name
    (`"xillion"`) instead of relying on the URI containing one — works
    with any URI shape now. Re-verified after the fix with a real write +
    read against the actual Atlas cluster (not mocked), then cleaned up.
    **This store is now genuinely live**, not just code-complete. 649/649
    total tests passing, ruff/black/mypy clean. Also added to
    `.env.example` and `render.yml` (both `sync: false`, same pattern as
    every other optional key).
16. ✅ **Code built 2026-09-22; credentials provided and fully verified
    live the same day.**
    New `xillion/notifications/notion_log.py`: `log_action(title, details)`,
    best-effort/never-raises. **Doesn't assume the target database's
    schema** — every Notion database has exactly one title property, but
    its *name* is whatever the user called it (not necessarily "Name"), so
    this queries the database's schema once (cached) to find the real
    title property rather than guessing and silently failing against
    whatever database Rakesh eventually shares. Wired into the
    higher-signal "actions taken" points, not every possible event
    (deliberately excludes routine market-hours auto start/stop — that's
    scheduling, not a decision):
    - `PATCH /instances/{id}` (name/params/capital edits — the actual
      "fine-tuning" actions from item 14)
    - `set_signal_action_core` (Take/Skip, from both the webpage and
      Telegram — item 10)
    - `activate_kill_switch_core` (from either the web UI or Telegram)
    Empty `NOTION_API_TOKEN`/`NOTION_DATABASE_ID` means every call site's
    `log_action()` no-ops with a debug log line. 4 new tests
    (`tests/unit/test_notion_log.py`, httpx stubbed).
    **Update, same day**: Rakesh provided a real integration token + a
    database ID ("Backtest Journal"), added to `.env`. Verified in two
    passes, not assumed: first pass found the token valid but a `search`
    call came back empty (nothing shared with the integration yet, per
    Notion's own error); after Rakesh added the share, re-verified by
    actually running `notion_log.log_action()` against the real database
    — it correctly auto-detected the database's real title property
    (**"Trade"**, not a hardcoded "Name" — exactly the case this was
    built to handle), the page landed (confirmed via a direct query), and
    the test page was then archived to leave the database clean. **The
    Notion action log is now genuinely live**, not just code-complete.
    649/649 total tests passing, ruff/black/mypy clean. Added to
    `.env.example` and `render.yml`.
17. ✅ **JEV / LLM-based decision-making — built 2026-09-22, the full
    propose → notify → approve/reject loop, end to end.** Scope was
    Rakesh's own words: read + guarded control (CP7's existing MCP
    surface) plus the ability to propose a parameter change with reasoning
    — never applied automatically, only after his explicit approval. Built
    exactly that, not more:
    - **New table** `proposed_strategy_change` (migration 021,
      `ProposedStrategyChange` model) — the proposal queue: instance,
      proposed params, reasoning, who proposed it, status
      (pending/approved/rejected), who decided and when.
    - **New API** `xillion/api/proposed_changes.py`
      (`POST/GET /proposed-changes`, `POST /proposed-changes/{id}/approve`
      `|/reject`). Approval writes through `update_instance_core`
      (extracted from the existing PATCH `/instances/{id}` route,
      2026-09-22, same refactor pattern as `start_instance_core`/
      `stop_instance_core`) — **an approved proposal is indistinguishable,
      in what it writes, from Rakesh editing the instance himself**, not a
      new/parallel write path.
    - **New MCP tools** `propose_parameter_change` and
      `list_proposed_changes` (`xillion/mcp_server/server.py`) — the LLM's
      only params-related capability. Two structural tests
      (`test_no_tool_can_apply_a_parameter_change_directly`,
      extending CP7's existing `test_no_order_placement_tool_exists`
      pattern) assert there is no tool that writes params directly, only
      one that proposes.
    - **Telegram**: proposing sends an alert with Approve/Reject inline
      buttons (reusing item 10's button infrastructure exactly);
      tapping either calls the same core functions the web UI's buttons
      call.
    - **Web UI**: a new "Proposed changes" panel on the Journal page —
      parity with Telegram, not Telegram-only, so a proposal isn't missed
      if the phone isn't handy.
    - **Explicitly out of scope for JEV, correctly**: no order-placement
      tool exists or was added (CP7's original guarantee, unchanged);
      no prosper-engine changes were made in this repo's commit (that repo
      isn't covered by this repo's commit standing-authorization per
      CLAUDE.md — wiring an actual LLM to call these new tools is
      prosper-engine's side of the work, for Rakesh to review separately).
    18 new tests across 3 files (`test_proposed_changes.py`,
    `test_mcp_server.py` additions, `test_telegram_commands.py` unaffected
    since the new callback path is additive). 649/649 total tests passing,
    ruff/black/mypy clean on every touched file.

**This closes out the full 17-item session sprint from
`docs/status/task-tracker.md`'s SESSION SPRINT, 2026-09-22.** See the
Gold Sweep-Reversal strategy-viability decision (manual-tasks.md's 🔴 item)
for what's still open — that decision was never part of this sprint and
remains Rakesh's own call.

---

## 🔴 Priority decision, 2026-09-22: Track B is now the main roadmap

Rakesh's call: focus shifts to **completing Track B end-to-end and getting
it fully usable from the UI/Telegram — not just runnable by reading code —
targeting usable "from next week."** Track A gets touched only when it's
genuinely blocking Track B work. Roadmap docs synced same day:
[roadmap-summary.md](../product/roadmap-summary.md) (new — plain-language
completion snapshot) and
[roadmap-quantman-parity.md](../product/roadmap-quantman-parity.md)
(checkboxes brought up to date — QP-2/6/7 now marked done, QP-4 split into
done-for-Options / gap-found-for-Gold, see next paragraph).

**Fixed same day, 2026-09-22.** Gold's alert mode now sends an exit alert.
`_fire_entry()` still calls `ctx.alert_entry()` for the entry, but now also
appends a lightweight virtual position (`ctx.state["alert_positions"]` — a
list, not the single `open_position` slot paper/live use, since alert mode
can have more than one unresolved entry outstanding at once) with no real
order behind it. `on_tick()` now branches on `ctx.mode == "alert"` to a new
`_check_alert_exits()`, which watches every entry in that list against real
ticks and fires `ctx.alert_exit()` (same `tag=level_name` as the entry, so
`_handle_alert_signal`'s existing tag-pairing logic links them in
`signal_log` automatically — no new plumbing needed there) the moment TP or
SL is crossed, using the actual crossing tick price rather than the exact
TP/SL line (a live tick can jump past it, same honest gap-fill assumption
`on_order_fill`'s `avg_fill_price` fallback already makes for real orders).
3 new tests in `tests/integration/test_gold_sweep_reversal.py` (win, loss,
and "still between SL/TP, no alert yet") — 607/607 total tests passing,
ruff/black clean (one pre-existing, unrelated mypy error in
`_cooldown_active`, confirmed via `git stash` to predate this change, not
introduced by it).

## 🔴 NEXT UP: Gold Sweep-Reversal — session-window + level-richness analysis

**The alert engine (G1-G6) is fully live and running** — real Supabase,
real Twelve Data feed, real instance, verified genuinely alive (daily
levels marked for real on 2026-09-22). **Separately, the first real 6-month
backtest (Stage 2) came back 2026-09-22, and it's a net loss** — see
[docs/strategies/gold-xauusd-sweep-reversal.md](../strategies/gold-xauusd-sweep-reversal.md)
§3 for the full numbers. 47.8% win rate (clears the card's own 45% "keep"
bar) but **-$12,705.76 over 6 months on a $5,000 account** — real R:R
(~0.46:1) is far worse than the card's assumed 2.5:1, because the SL is
almost always set by the swept level's wick extreme, not the 3.0pt floor.

**Updated same day: two parameter sweeps (30 + 27 combos, TP × min-SL-floor
and TP × max-SL-cap) both came back net-negative on every single
combination tested** — capping or widening the stop doesn't rescue it
either (best found: -$12,672.71, barely better than baseline; profit
factor never exceeded ~0.30). **This rules out SL/TP sizing as the fix in
isolation.** New `max_sl_pts` param added to `strategies/gold_sweep_reversal.py`
to make this sweepable (default 100.0 — no effect on live behavior unless
lowered). Full sweep tables in the strategy doc §3.

**Rakesh's prioritized next-analysis queue (2026-09-22), in order — see
[docs/status/deferred-backlog.md](deferred-backlog.md)'s "Gold Sweep-Reversal
— planned Stage 2 follow-up analysis" for full detail on each:**
1. Sweep the trading session window itself (not just TP/SL) — the current
   12:30-18:30 IST window is the card's own choice, untested against
   alternatives on this data.
2. Richer level context (per-session, not just Asian; multi-day, not just
   1 prior day) to support that decision.
3–4. Finer TP/SL sweeps, combined with #1 (they may interact).
5. A confidence-scoring concept for entries (a real % score from setup
   quality, used to gate firing and/or make the fixed `cooldown_minutes`
   adaptive) — designed as a concept, not built yet.

Explicitly deferred until 1-5 are settled: agent/workflow-driven signal
generation ("JEV," Rakesh's own exploration) — logged in the backlog with
a pointer to CP8's existing AI-confidence hook as a reusable starting
point. **The alert instance keeps running regardless of any of this** — it
was always decoupled from whether this exact parameter set is fundable
(alert-only, no capital at risk).

**Render deploy readiness, checked 2026-09-22:** infrastructure-ready —
`render.yml`'s branch already correctly points at `feat/track-b-pipelines`,
no new pip dependencies needed (Twelve Data/Finnhub both just use the
already-core `httpx`). **One real gap found and fixed:**
`TWELVE_DATA_API_KEY`/`FINNHUB_API_KEY` weren't declared in `render.yml` at
all — added (same `sync: false` dashboard-secret pattern as Telegram).
Paste both keys into the Render dashboard once, whenever Render is next
turned on.

**Everything below is code-complete and committed** on
`feat/track-b-pipelines` (worktree: `.claude/worktrees/track-b-pipelines`)
as of 2026-09-22 — 603/603 tests passing, ruff/black/mypy clean. Options
work (credit-spread-weekly) is untouched and resumable separately.

**Alert engine (G1-G6), all done 2026-09-21/22, verified genuinely live:**
Twelve Data feed (`brokers/twelve_data_feed.py`), strategy logic
(`strategies/gold_sweep_reversal.py`), rituals (session gate real; news
veto still a stub pending Finnhub wiring), Telegram reasoning, taken/
skipped + outcome tracking (migration 020), weekly digest extension.
Instance `26f82923-5cb1-4150-8db6-da530220efb3` created, started, and
confirmed alive (real `daily levels marked` log line 2026-09-22, real
WebSocket ticks observed). Supabase (was paused, resumed), migration 020,
and a `uvicorn --reload` multiprocessing hang (worked around by running
without `--reload`) are all resolved — see `manual-tasks.md` Done section
and CLAUDE.md's Operational gotchas for the exact commands/symptoms if any
recur.

**Backtest/paper infrastructure (P1-P3), built 2026-09-22 to actually run
the backtest above:**
- **P1** — `data_providers/twelve_data_history.py`, a real
  `HistoricalDataProvider` (free tier confirmed back to 2021), plugs into
  the existing Backtest page/warehouse pipeline like NSE Bhavcopy does.
- **P2** — `strategies/gold_sweep_reversal.py` now mode-branches: alert
  mode unchanged (`ctx.alert_entry`), paper/live/backtest places a real
  `ctx.buy/sell` (lot_size → hundredths-of-a-lot quantity, matching MT5's
  own convention) and monitors SL/TP via a new `on_tick`. New generic
  `ctx.notify()` (StrategyContext + strategy_engine.py) for routine
  non-critical Telegram pushes (entry/exit/outcome), separate from
  `notify_critical`.
- **P3 (partial)** — paper-mode Telegram entry/exit/outcome notifications
  exist via `ctx.notify()`; not yet run through a live paper instance
  (blocked on the viability decision above, not on engineering).

**Five real bugs found and fixed getting the first backtest to actually
run** (all in shared code, not Gold-specific, so any future strategy
benefits too) — full detail in commit messages and the strategy doc §3/§7:
a sparse/empty `params` dict crashed on first `ctx.params` access (now
`fill_param_defaults()`, wired into every instance/backtest endpoint);
`_BacktestContext` had no `notify()` override; `BacktestEngine` never
synthesized `on_tick` for a plain strategy's own primary symbol (only for
options legs), so SL/TP monitoring never ran in backtest at all;
`_roll_day` fired on each day's first bar (~00:00 UTC, inside the Asian
session), so Asian High/Low came back missing on *every single day* of the
backtest until fixed; `compute_metrics`'s CAGR crashed outright on an
account this deeply negative (floored at -100% now). Also: the original
23-day-stale `uvicorn` process from before this session was found running
and killed before any of today's restarts.

---

**Last updated:** 2026-09-22
**Current position:** **2026-09-22: Track B is now the main roadmap** (see
the 🔴 Priority decision section immediately below) — the near-term goal is
Gold Lane B1 fully usable end-to-end from UI/Telegram. Options work stays
paused per Rakesh's 2026-09-21 call, resumable later, untouched.
Earlier context: **2026-09-21: Options work paused by Rakesh's explicit
call — full focus shifts to Gold Lane B1.** Rakesh brought a specific XAUUSD
scalping strategy ("Sweep-Reversal," a session-liquidity-sweep fade) with
exact entry/exit/sizing rules and a FundingPips 1 Step Flex $5K prop-rule
mapping; Stage 1 (rules encoded) is done — see
[docs/strategies/gold-xauusd-sweep-reversal.md](../strategies/gold-xauusd-sweep-reversal.md)
and the reference backtester at
[scripts/gold_sweep_backtest.py](../../scripts/gold_sweep_backtest.py). Goal
is a full alert pipeline: scheduled pre-signal checks (session/market status,
recent candles, news), a Telegram push with entry reasoning, manual
taken/skipped tracking (webpage, Telegram buttons later), and a weekly
win-rate review — deliberately **decoupled from the Funding Pips MT5
broker/bridge for v1** (alert-only, no order placement, so no Wine/MT5
terminal setup needed yet). Full checkpoint breakdown for this build is being
scoped next; this entry will be updated once it's written up. Options
(credit-spread-weekly) stays at its current Stage 1/2 status below,
untouched, resumable later — nothing about it was reverted, it's simply not
being worked on for now. Before that, same day: **2026-08-29: Gold Lane B1's backtest data source
built** -- Rakesh's decision to combine both deferred-backlog candidates
(extend the MT5 bridge for on-demand history, plus a free Alpha Vantage
backup) rather than pick one, plus a "local agent" connection so backtests
work even away from his Mac, which turned out to need no new mechanism at
all -- the bridge's existing poll-out architecture already provides it.
Two new data providers (`MT5 Bridge (Gold)`, `Alpha Vantage FX`), new
`mt5_historical_request` queue (migration 019), and a real pre-existing
bug fixed along the way (broker-backed data providers could silently get
handed the wrong connected broker). See "Gold Lane B1 backtest data
source" under Track B below. Before that, same day: product type
(MIS/NRML for Zerodha,
INTRADAY/MARGIN for Dhan) made UI-configurable per connection, Rakesh's
own request rather than a one-time hardcoded decision -- new dropdown on
each broker's credential form (Configuration -> Brokers), persisted the
same encrypted way as every other credential field, defaulting to the
previous hardcoded values so an existing connection behaves unchanged
until the dropdown is touched. See "Product type made UI-configurable"
under CP15 below. Before that, same day: **Butterfly Weekly built — the third
multi-leg strategy and the first DEBIT structure**, closing out
"Blocked-on-you #7"'s last unbuilt structure (credit spread + condor were
already done). New split-middle-leg design for a 1:2:1 ratio's shared
strike, and new debit-structure protective-order math
(`butterfly_value()`/`butterfly_protective_levels()`) that reuses
`check_exit_trigger()` completely unmodified. See "Multi-leg beyond 2-leg,
2026-08-29 continued" under CP11 below. Before that, same day: M01's funds
reconciliation — the last
open piece of CP14's own scope note, flagged twice before today — closed.**
`Broker.get_realised_pnl_today()` implemented for both Zerodha (Kite's
"day" positions array) and Dhan (summing realizedProfit, closed positions
included), compared against xillion's own internally-computed
`DailyStrategyPnl` figure. Migration 018. See "CP14 follow-up: funds
reconciliation" under CP14 below. Before that, same day: **the four
unauthenticated `brokers.py` routes** (flagged in passing during the
broker-failover work) fixed — `GET /connections`, `POST .../reconnect`, `GET .../status`,
`POST /refresh-instruments` all now require a session, matching every
other route in the file. See "API" under "Broker failover" below. Before
that, same day: **Dhan's Forever-Order (bracket/GTT)
path unblocked** — Rakesh decided the product-type question (MARGIN,
attempt Forever Orders with it), `brokers/dhan.py` now implements
`place_protective_gtt`/`cancel_gtt` for real. See "Follow-up, 2026-08-29:
Dhan's Forever-Order path, unblocked" under CP11 below. Same day, earlier:
multi-leg structures beyond 2-leg — Iron Condor Weekly (4 legs) built, and
two real bugs in multileg_execution.py's leg-failure protocol found and
fixed in the process. See "Multi-leg beyond 2-leg" under CP11 below. Same
day, earlier still: broker failover (Zerodha ↔ Dhan) — health monitoring +
exit-only
cross-broker failover, migration 017. See "Broker failover" below. Same
day, earlier still: orders/fills reconciliation added to M01 (migration
016) — the other honest gap CP14 flagged (positions-only) when it shipped,
alongside the trading-gate wiring from
the day before. See "CP14 follow-up" entries below. Before that, Gold Lane
B1's broker+bridge plumbing built (see the Track B section below) —
code-complete but unverified, no
real MT5 account/Wine environment in this sandbox. Before that,
`feat/options-alert-engine` was merged to `main`
2026-08-26 (fast-forward, 259 files, all of Track A + Track A extension +
CP15 + a full frontend UX overhaul) and pushed.** `main` is now the current
baseline; a new branch will be created off it for the next phase (Track B
asset pipelines + remaining deferred Track A items). This session (2026-08-25
into 2026-08-26) also did a large frontend UX pass not itemized as its own
checkpoint: new SVG logo/favicon, sidebar collapse, command palette,
skeleton loaders, a redesigned login page, light-theme contrast/glassy
rebalance, Settings split into Settings + Configuration, Logs merged into a
single Dev page with a real WS-connection-status badge, and a Telegram
"send test message" / Dhan "check connection" flow. Both Dhan and Telegram
are now genuinely connected and verified live on Render (manual-tasks.md
items #10/#11 resolved).

**Real production bug found and fixed 2026-08-26, while diagnosing why a
Dhan paper instance kept showing "No live tick source":** the `dhanhq` SDK's
`MarketFeed.__init__` calls `asyncio.set_event_loop(self.loop)` on whatever
thread constructs it — since `brokers/dhan.py`'s `_start_feed()` runs on the
main thread (the same one FastAPI/uvicorn's server loop runs on), this
silently overwrote the process's default event loop. Manifested in
production as `dhan_tick_broadcaster` crash-looping with `cannot reuse
already awaited coroutine` until `task_supervisor.py`'s restart budget (5
restarts/10min) was exhausted, after which the feed just silently stayed
dead — no further alert, nothing to notice short of checking Dev logs.
Fixed by restoring the correct event loop immediately after constructing
`MarketFeed`. Two related bugs found in the same pass: (1) every
`_try_connect_dhan()`/`_try_connect_zerodha()` call (daily refresh, manual
reconnect, settings save) leaked a supervised broadcaster task, since the
previous one's handle was never stored or cancelled — now tracked on
`app.state` and cancelled before starting a new one; (2) the SDK's own WS
reconnect loop retries every ~1s forever uncapped, so a bad connection
flooded the Dev-page logs at roughly 1 line/sec indefinitely — now gives up
after 10 consecutive failures and alerts once via Telegram instead. Also
added full-traceback capture to `task_supervisor.py`'s crash logging (it
previously only logged `str(exc)`, making a crash like this one very hard to
diagnose from Telegram/Dev-log output alone).

**Previous position (2026-08-25), preserved for history:** **The entire Track A extension (CP11-CP15) is now
code-complete.** Track A original (CP1-CP10) was already done. In this
session: CP11 (multi-leg execution + protective orders) done, plus its own
follow-up (Options Stage 2 backtest genuinely unblocked, with a real
open→close trade through `BacktestEngine`). CP12 (trailing-stop engine)
done, including the arguably more load-bearing fix that `ctx.state` now
actually survives a restart (it never did before, despite the class's own
docstring claiming it). CP13 (expanded risk engine) done — 18 checks, 100%
branch coverage, and the previously-dead `AuditLog` finally wired in. CP14
(EOD reconciliation + square-off) done — X02 and M01 as independent
scheduled jobs, verified against the exact "crash mid-position, restart
after close" scenario the checkpoint asked for. CP15 (Dhan as a second full
broker) is **code-complete but not live-verified** — `brokers/dhan.py`
built against DhanHQ's real docs/SDK (fetched and read directly this
session, not assumed), multi-broker selection now genuinely wired
end-to-end (a real pre-existing bug found and fixed: `_resolve_broker` was
hardcoded to Zerodha only), but running an actual order through it needs a
real Dhan account — logged as the literal next thing to do in
[manual-tasks.md](manual-tasks.md), not silently skipped.

**What's left to trade real money, in order:** (1) **a free Dhan account +
token (#10) is still the fastest path to seeing the app run for real** —
paper mode no longer needs Zerodha at all, so this goes first and costs
nothing; (2) the real 2-5yr NSE backfill (#6) — **🔵 no longer blocked on
you, Claude is running it now** (NIFTY+BANKNIFTY-scoped, see CP3); (3) a
Telegram bot (#11) for alerts, DB-configurable via Settings → Notifications
as of 2026-08-25 — Kite Connect (#1) itself stays deferred, low priority,
Rakesh's explicit call; (4) a real broker-side bracket/GTT order path
(CP11's own honest gap — protective orders are software-stop only today);
(5) the static-IP whitelisting SEBI requires for live order placement.
**2026-08-25: five other Blocked-on-you items resolved by Rakesh's
decisions in one pass** — ₹50k/₹1,000-mo milestone confirmed, CA opinion
decided not needed (foreign income on ITR instead), Funding Pips account
already held, Redis choice decided (Upstash), LLM key + static-IP research
explicitly deferred for later. See `manual-tasks.md` for the live
checklist. CP3/CP4/CP5/CP8 remain "engineering done, one item needs
something only you can supply" (CP3's item is now in progress, not
waiting on you). **Note:** CP8's code lives mostly in the separate
`prosper-engine` repo and
is uncommitted there — xillion's commit standing-authorization doesn't
extend to it.

**Found while checking for other gaps, 2026-08-25:** Settings → Risk and →
Danger zone tabs have called `/settings/risk-limits`, `/settings/reset-data`,
`/settings/wipe` since they were built, but none of those routes existed on
the backend — both tabs 404'd, unrelated to anything else this session.
Added `reset-data` (clears trade/log/run data, preserves credentials +
config) and `wipe` (clears everything, `/auth/setup-status` naturally
takes over) in full. **`risk-limits` persists but is deliberately NOT
wired into live enforcement** — its field shape doesn't map cleanly onto
how risk actually works today (account-wide `default_*` config +
per-instance `risk_limits_json`), and guessing at that mapping risks
getting real risk enforcement wrong, not just a cosmetic bug. Left as an
open design gap rather than faked. 404/404 tests passing.

**Active branch:** `feat/track-b-pipelines` (created 2026-08-26 off `main`
at `0273cf3`, worktree at `.claude/worktrees/track-b-pipelines`). Covers the
next phase broadly: the deferred Track A validation items (real pass/fail
backtest run, paper-soak monitoring, Zerodha/Dhan product-type decision,
static-IP research) first, then Track B asset pipelines (Gold/MT5, MCX,
stocks, crypto) as they come up. `main` itself stays the stable baseline —
`feat/options-alert-engine` is fully merged into it and can be deleted.

> **2026-08-26 — Supabase free-tier overage, root-caused and fixed.**
> Supabase emailed that the DB hit 1611MB against the 500MB free limit.
> `bar` (1056MB) + `option_chain_snapshot` (519MB) turned out to be 98% of
> that — both 100% regenerable backtest/historical cache, never live app
> state, and never needed to share a cloud DB with the ~1MB of actual live
> state (users, sessions, instances, credentials, journal) at all. Split
> them onto a separate local-only SQLite warehouse DB (`Settings.
> backtest_database_url`, defaults to `./data/backtest_warehouse.db`,
> `get_warehouse_session_factory()` in `xillion/db/session.py`) — see
> `CLAUDE.md`'s Deploy workflow section for the full picture, including the
> Render-ephemeral-disk implication. Existing data was copied across via
> `scripts/migrate_warehouse_to_local.py` (keyset-paginated, not OFFSET —
> `bar` alone is 4.5M+ rows) rather than re-fetched from scratch, then
> reclaimed from Supabase via `scripts/truncate_supabase_warehouse.py`.
> Also found in passing: a genuine correctness gap where
> `xillion/api/backtest.py`'s in-progress option-chain backfill for the
> real credit-spread pass/fail run (see the 2026-08-26 crash-loop entry
> above) was about to make the Supabase overage significantly worse —
> stopped mid-run once the email surfaced this.
>
> **2026-08-27 — truncation completed, confirmed via direct query.**
> Supabase auto-flips a project into DB-level read-only mode once it
> exceeds its free-tier disk quota — this blocks even the `TRUNCATE`
> that would free the space, a genuine chicken-and-egg the project was
> stuck in. Supabase's documented fix
> (`SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE`) only affects
> *subsequent* transactions in the same session, not the one already open
> — and the SQL Editor's "Run" wraps a pasted multi-statement block in one
> implicit transaction, so the naive combined-script version still hit
> `cannot execute TRUNCATE TABLE in a read-only transaction`. Fixed by
> adding an explicit `commit;` between the `SET` and the `TRUNCATE`s in
> one single Editor run, forcing a new transaction that picks up the
> just-changed session default:
> ```sql
> set session characteristics as transaction read write;
> commit;
> TRUNCATE TABLE "bar";
> TRUNCATE TABLE "bar_coverage";
> TRUNCATE TABLE "option_chain_snapshot";
> commit;
> set default_transaction_read_only = 'off';
> ```
> Confirmed via `pg_database_size(current_database())`: **1611MB → 40MB.**
> Local warehouse (`data/backtest_warehouse.db`, 1.1GB) holds the full
> migrated dataset — 4,498,851 `bar` rows, 2,208,349
> `option_chain_snapshot` rows, verified matching source counts before
> truncation.

> 2026-08-24 infra note: docs restructured from flat numbering into
> `status/ process/ architecture/ product/ strategies/ archive/` folders (all
> 35 cross-links rewritten and verified). Claude wiring added: 4 skills
> (`xillion-status`, `xillion-checkpoint`, `xillion-verify`,
> `xillion-new-strategy`) + 3 hooks (SessionStart orientation, Bash guard for
> the alembic/DATABASE_URL trap and >5MB staged files, Stop-hook tracker
> enforcement). Checkpoint commits are now standing-authorized (no
> Co-Authored-By, ever).

---

## How this project is structured

Two tracks run in parallel:

- **Track A — Platform**: shared infrastructure every asset class needs
  (correctness, data warehouse, journal, AI, automation). Built once.
- **Track B — Asset pipelines**: the *same repeatable 6-stage pipeline*
  applied per asset class. See [14-asset-pipeline.md](../process/asset-pipeline.md)
  for the stage definitions.

Track A must reach CP3 before any Track B pipeline can complete Stage 2
(backtesting needs the data warehouse).

---

## Timeline target

| Month | Goal |
|---|---|
| **Month 1** | Platform CP1–CP6 + **Options pipeline complete** + **Gold XAUUSD pipeline started** |
| **Month 2** | Gold XAUUSD complete + Forex + platform CP7–CP10 |
| **Month 3** | Stock options + Stocks + automation (CP11–CP14) + crypto if time |

Engineering ≈ 155 hrs. Paper-soak windows are **calendar-bound and cannot be
compressed** — they overlap later engineering, so nothing sits idle.

---

## TRACK A — Platform

### ✅ CP1 — Safety net + correctness `DONE 2026-08-24`
Fixed bugs that made every backtest number untrustworthy.

- [x] `.gitignore` the 32MB `data/*.csv` instrument masters (was about to be committed)
- [x] `xillion/engine/position_math.py` — signed-position arithmetic shared by
      live + backtest engines. Fixes shorting (previously a sell with no
      position credited cash and tracked nothing) **and** a latent live bug
      where a reversal kept the old side's `avg_price`
- [x] Mark-to-market equity — `equity()` was returning cash only, so the curve
      was flat mid-trade and **max drawdown / Sharpe / Sortino were all wrong**
- [x] `xillion/core/contracts.py` — contract multiplier. NIFTY lot size is 65,
      so options P&L was understated **65×**
- [x] Fee model: STT charged sell-side only; `FeeConfig.zero()` for exact tests
- [x] `_sortino` / `profit_factor` return `None` not `float("inf")` (invalid JSON)
- [x] **Bonus fix found during testing:** `compute_metrics` early-returned all
      zeros when no trade had *closed*, so a strategy still holding a winning
      position reported 0% return and 0 drawdown. Portfolio metrics now derive
      from the equity curve; trade stats from closed trades
- [x] 18 regression tests (`test_position_math.py`, `test_backtest_equity.py`)

**Verified:** `pytest tests/` → **96 passed** (78 pre-existing + 18 new).

---

### ✅ CP2 — Data warehouse `DONE 2026-08-24`
Stop re-fetching. Own the data. → *Goal: no third-party historical fees.*

- [x] Fixed `BarRepository.get_bars` — it **ignored its `exchange` argument**,
      so NSE/NFO rows could cross-contaminate. Now filters on it.
- [x] Replaced per-row `session.merge` with a single bulk
      `INSERT .. ON CONFLICT DO UPDATE` (dialect-aware: `pg_insert` on
      Postgres, `sqlite_insert` in tests) — the old per-row loop would have
      made a years-long backfill take one DB round-trip per bar
- [x] Migration `005`: `bar_coverage` + `market_holiday` tables. No new bar
      index needed — `bar`'s existing PK is `(symbol, exchange, timeframe, ts)`
      in exactly the order `get_bars` filters on, so it already serves as the
      range index
- [x] `xillion/data/warehouse.py::BarWarehouse` + `xillion/data/coverage.py`
      — check cache → fetch only the missing date range → persist → re-read
      from DB. A gap that comes back empty (holiday) is still marked
      covered, so it isn't re-requested forever
- [x] **Whole-file bhavcopy persistence** 💡 — `nse_bhavcopy.py` now exposes
      `fetch_all_bars_for_day` (parses every instrument in that day's ZIP,
      not just the one requested) behind a `supports_whole_file_bulk`
      capability flag. `BarWarehouse` uses a wildcard coverage key for such
      providers, so **one fetch covers every symbol on that exchange/day** —
      a second symbol on an already-fetched day costs zero network calls
- [x] Wired `POST /backtest/run-provider` through `BarWarehouse` instead of
      calling `provider.fetch_bars` directly
- [x] Wired `HistoryManager(repository=...)` in `StrategyEngine.spawn` — it
      accepted a `repository` arg since it was written but never read it, so
      a live/paper strategy needing e.g. a 200-bar SMA got nothing for its
      first 200 ticks even with years of DB history sitting right there.
      **Known gap, not fixed here:** the DB fallback defaults to
      `exchange="NSE"` — an NFO/BFO options instance won't get backfilled
      until the exchange-hardcoding audit lands in CP10. Falls back to
      in-memory-only (today's behaviour) for those, no regression either way
- [x] 11 new regression tests (`test_bar_repository.py`, `test_bar_warehouse.py`,
      `test_history_manager.py`) — includes the exact "second run, zero
      provider calls" check and a whole-file-bulk cross-symbol check

**Verified:** `pytest tests/` → **107 passed** (96 prior + 11 new). Ran the
counting-fake-provider scenario from the Verify line directly: first
`BarWarehouse.get_bars()` call makes 1 provider call, an identical second
call makes 0.

---

### ✅ CP3 — Backfill + run history `DONE 2026-08-26 — 2021-2026 NIFTY+BANKNIFTY backfilled`
- [x] Backfill CLI (`scripts/backfill.py`, resumable year-by-year) +
      `POST /api/data/backfill` + `GET /api/data/backfill` (job status) +
      `GET /api/data/coverage`, plus a Coverage & backfill panel under
      Settings → Data Providers
- [x] **Run the real 2–5 year backfill — DONE 2026-08-26.**
      Was blocked on this sandbox not reaching Supabase; turned out the
      project was paused (Rakesh resumed it 2026-08-25), and the
      direct-connection hostname is IPv6-only anyway — switched `.env` to
      the Session pooler (IPv4). **Scoped to NIFTY + BANKNIFTY only**, not
      the whole NFO market: an unfiltered 2021→today run would be ~85M
      rows / ~25-30GB, well past free-tier Postgres storage. Added a real
      `underlying_filter` parameter threaded through
      `xillion/core/data_provider_base.py` →
      `data_providers/nse_bhavcopy.py` → `xillion/data/warehouse.py` →
      `scripts/backfill.py --underlying-filter`, keeping the whole-file
      bulk-fetch lever (still one download per day) but only persisting
      matching underlyings. **Real subtlety handled, not glossed over:** a
      filtered bulk fetch must NOT share the unfiltered `WILDCARD_SYMBOL`
      coverage key, or a later full-market request for the same dates
      would wrongly think it's already covered and skip the excluded
      contracts — uses a distinct coverage key (`*:NIFTY,BANKNIFTY`)
      instead.

      **First run "completed" but was silently wrong for 2021-2023 —
      caught by checking the actual data, not by trusting the log
      output.** NSE's current bhavcopy URL (the "UDiFF" format this
      provider used exclusively) genuinely 404s for any date before
      2024-01-01 — confirmed by directly probing the URL across several
      dates, not assumed. `_fetch_and_parse_day` treats a 404 as "holiday,
      no trading" (correct for a real holiday) and marks that date range
      as covered — so 2021-2023 got marked fully covered in
      `bar_coverage` while genuinely containing zero real bars for
      2,646+ days straight. Caught by querying the actual `bar` table
      after the "successful" run and finding the earliest row was
      2024-01-01, not 2021-01-01.

      **Fixed for real, not patched around:** found (via WebSearch, then
      verified by downloading and parsing an actual 2021-06-15 file, not
      trusting the search result) that NSE's older archive format still
      exists at a different URL with different columns
      (`archives.nseindia.com/content/historical/DERIVATIVES/...`,
      `INSTRUMENT`/`SYMBOL`/`EXPIRY_DT`/`STRIKE_PR` instead of the new
      format's `TckrSymb`/`FinInstrmNm`/`XpryDt`/`StrkPric`, and no
      ready-made tradingsymbol column at all). Both
      `_fetch_and_parse_day` (bars) and `fetch_option_chain_for_day`
      (strike/premium resolution — separately verified as the thing a
      real backtest actually depends on for options, not the `bar` table)
      now try the new-format URL first and fall back to this legacy one
      on a 404 — no hardcoded cutover date needed, correct regardless of
      exactly which day NSE switched formats.

      **Two honestly-documented approximations the legacy path carries
      that the new format doesn't need** (see
      `data_providers/nse_bhavcopy.py`'s module docstring for the full
      reasoning): (1) `underlying_price` — the legacy file has no
      equivalent to the new format's `UndrlygPric` (NSE's own recorded
      spot), approximated from the same-day nearest-expiry index future's
      own close (index futures trade close to spot, but this is a proxy,
      not an exact recorded value); (2) `lot_size` — no equivalent to
      `NewBrdLotQty` exists pre-2024 either, and NIFTY/BANKNIFTY's real
      lot size changed multiple times across 2021-2023 with no verified
      free source for the exact value on an arbitrary date — rather than
      guess, this returns `lot_size=0`, which `size_defined_risk_position`
      already turns into a loud `ValueError` instead of a silently
      mis-sized trade. **A pre-2024 backtest cannot size positions yet**
      until a real historical lot-size table replaces this — flagged
      here, not hidden.

      Tradingsymbols for legacy dates are a synthetic, internal-only
      convention (`_legacy_tradingsymbol_from_row`), not NSE's or
      Zerodha's real naming — safe only because this data never leaves
      the backtest engine (never placed as a live order, never
      reconciled against a live broker). 6 new unit tests
      (`test_nse_bhavcopy_legacy_format.py`), verified end-to-end against
      the real 2021-06-15 file before trusting it (4,384 bars, 50,734
      option-chain rows, spot-proxy and symbol-consistency between the
      bar and option-chain paths both confirmed by hand). Corrected the
      first run's bad `bar_coverage` row (`from_date` moved from
      2021-01-01 to 2024-01-01, the genuinely-verified boundary) and
      re-ran the backfill for just 2021-2023 through the fixed code.
      **Completed 2026-08-26** — 2,680,368 real bars persisted for
      2021-01-01 → 2023-12-29 (spot-checked directly against the live
      Supabase DB, not trusted from the run's own log line, which
      misleadingly printed "0 bars" — a known cosmetic quirk: it counts
      rows matching the literal `--symbol NIFTY` argument, not the many
      distinct per-contract tradingsymbols the whole-file-bulk fetch
      actually persists). Combined with the earlier 2024-2026 run,
      `bar_coverage` now shows one continuous row
      (`*:BANKNIFTY,NIFTY`/NFO) spanning **2021-01-01 → 2026-08-25**.
- [x] Persist `BacktestRun`/`BacktestTrade` — tables existed since migration
      001/002 but nothing ever wrote to them; wired into all three
      `/backtest/run*` endpoints
- [x] `GET /api/backtest/runs` + `GET /api/backtest/runs/{id}` + Run history
      panel on the Backtest page

**Verify:** Browser-verified end-to-end against a disposable local SQLite DB
(same Supabase-unreachable reason above) — real login, real click-through,
real NSE network fetch. **2+ years of NIFTY/BANKNIFTY option history
queryable locally is now true for the real Supabase DB too** — 5+ years,
2021-2026, confirmed by direct query, not just the run's own log output.

**🐛 Real bug caught by the browser check, not the unit tests:** the CP2
bulk `upsert_bars` blew past SQLite's default 999-bound-parameter limit
("too many SQL variables") the moment a real whole-file bhavcopy fetch tried
to persist hundreds of contracts in one statement — every unit test used 1-2
bars, so this never surfaced there. Fixed by batching at 100 rows/statement
(dialect-agnostic, so Postgres gets the same safety margin even though its
own limit is far higher). Confirmed fixed against real NSE data: one
two-day backfill request persisted **124,012 bars across 62,402 distinct
F&O contracts** from 2 real bhavcopy files — this is the CP2 "big lever"
actually proven, not just unit-tested.

---

### 🟡 CP4 — Signal lifecycle `ENGINEERING DONE 2026-08-24 — Telegram proof needs YOU`
- [ ] **[YOU]** Create a Telegram bot (@BotFather) — Kite Connect deferred
      by your own call, no longer bundled with this item (2026-08-25).
      **As of 2026-08-25, enter the bot token + chat ID via Settings →
      Notifications, not `.env`** — new `GET`/`PUT /settings/notifications`
      (`xillion/api/settings.py`), same encrypted DB pattern as
      Dhan/Zerodha, applies to the running `TelegramNotifier` immediately
      via a new `.configure()` method, no restart needed. Blocks only the
      *real* Telegram proof below, not anything already built
- [x] Entry + **target + stop-loss + EXIT** signals with parent-child linkage.
      `signal_log` was entry-only with no ENTER/EXIT distinction at all — its
      `signal_type` column actually held the free-text tag, not a lifecycle
      stage (migration `006`). New `ctx.alert_entry()`/`ctx.alert_exit()` on
      `StrategyContext`; an EXIT auto-links to the most recent **still-open**
      ENTER sharing its `(instance, symbol, tag)` — verified a same-tag
      entry/exit/entry/exit sequence links each exit to *its own* entry, not
      the earlier closed one
- [x] `GET /signals` (+ instance filter) + Alerts page + Telegram-body
      formatting (target/stop-loss lines, "closing entry #N")

**Verified two ways:**
1. `pytest` — 6 new tests (`test_signal_lifecycle.py`,
   `test_signals_api.py`), incl. the repeated-tag-doesn't-cross-link case.
2. **Browser, real engine code path, not a mocked UI:** drove
   `StrategyEngine.spawn()` + `ctx.alert_entry`/`alert_exit` for real against
   a disposable local DB (same Supabase-unreachable reason as CP2/CP3),
   confirmed the Alerts page renders exactly what was expected — an open
   ENTER with target/SL, an EXIT correctly linked to entry #1, a second
   ENTER still open. Notifier used was a fake (`_FakeNotifier`) since no
   real Telegram bot token exists yet — **that's the one thing not proven
   end-to-end**: real Telegram delivery, blocked on item #1 above.

---

### 🟡 CP5 — Strategy builder `MOSTLY DONE 2026-08-24 — multi-leg options carried to Track B`
- [x] Condition-builder UI (metric / operator / threshold rows) on top of the
      existing `params_schema` form — new `condition_list` param type,
      `ConditionListEditor` renders rows (metric+period, operator, value-or-
      another-metric), writes straight into the same JSON params blob every
      other strategy already uses
- [x] Generic `ConditionStrategy` (`strategies/condition_strategy.py`) that
      interprets builder output — a new setup is a JSON blob, not a new
      Python file. Long or short, entry/exit each an AND of conditions
- [x] Indicator library (`xillion/engine/indicators.py`): SMA, EMA, RSI, ATR,
      VWAP (rolling, not session-anchored — see its docstring), Bollinger,
      MACD, Supertrend. `rsi_threshold_alert.py` refactored to import the
      shared `rsi()` instead of its own private copy — one RSI formula in
      the codebase, not two that could silently drift apart
- [x] **Multi-leg option structures — done via CP11 (generic engine,
      2-leg credit spread) + the 2026-08-29 follow-ups (Iron Condor
      Weekly, 4 legs, and Butterfly Weekly, 1:2:1 debit structure — see
      CP11's own section for the full writeup, including two real
      leg-failure-protocol bugs the 4-leg build surfaced and fixed, and
      the butterfly's own split-middle-leg design and new debit-structure
      protective-order math).** Straddle/strangle (undefined-risk,
      excluded by this codebase's own defined-risk-only sizing gate)
      remains unbuilt by design, not by gap.
- [x] **Parameter optimisation: grid search + walk-forward**
      (`xillion/engine/optimization.py`) — walk-forward's overfit heuristic
      verified against a deliberately-constructed regime-change scenario
      (steady uptrend in-sample, hard reversal out-of-sample): correctly
      flags `is_likely_overfit=True` there and `False` when the same trend
      continues through both windows
- [x] `POST /backtest/optimize` + `POST /backtest/walk-forward` (reuse
      `_resolve_strategy_and_bars`, the same warehouse-backed fetch
      `/run-provider` already used) + sweep results UI on the Backtest page

**🐛 Real bug caught only by loading the app, not by tests:** the plugin
loader's `ParamSpec.type` allowlist didn't include `"condition_list"`, so
`condition_strategy.py` failed discovery and **silently vanished from the
strategy dropdown** — logged as a discovery error, but nothing surfaced it
anywhere a person would see. Fixed in `xillion/core/plugin_loader.py`
+ a regression test asserting `"Condition Strategy"` actually discovers.

**Verified, both end-to-end in a real browser against real data** (this
sandbox's disposable-SQLite workaround, per the CP2/CP3 note on Supabase
being unreachable here):
1. **Zero-code setup:** built "close crosses above SMA(3)" entry / "close <
   10" exit entirely by clicking, uploaded a CSV, ran it — P&L **−₹11.01**,
   matching the hand-verified unit test's −11.00 (the 1-paisa gap is real
   brokerage/STT the unit test zeroed out via `FeeConfig.zero()`).
2. **Parameter sweep against real NSE data:** grid search over RSI
   Threshold's `period` (10/14/20) via the free NSE Bhavcopy provider for
   real January 2024 data — persisted **124K+ real bars** in the process
   (the whole-file-bulk lever from CP2, proven again at a full month's
   scale, not just the 2-day CP3 sample), returned a correctly ranked
   3-row results table. (The specific symbol tried didn't match any real
   contract, so all three came back 0 trades — an honest result, not a
   failure: the fetch, the warehouse persistence, and the ranking all ran
   for real.) Walk-forward's own UI (folds/train-ratio fields, toggle) was
   checked structurally rather than re-run live, since its logic already has
   a dedicated, harder unit proof (the regime-change scenario above) than a
   second live run would add.

---

### ✅ CP6 — Strategy journal + feedback loop `DONE 2026-08-24` → *Goal #8*
- [x] `StrategyJournal` (`xillion/engine/journal.py`) — combines both places
      an outcome actually lives: `signal_log` ENTER/EXIT pairs (alert mode,
      has real target/stop-loss on record) and `backtest_trade` (has real
      P&L, but never had target/stop-loss — `ctx.buy()`/`ctx.sell()` never
      carried those fields, only `ctx.alert_entry()` does)
- [x] **Auto-tag failure modes — honestly scoped, not the full taxonomy.**
      `stopped_out` / `target_hit` are only claimed when the exit price
      *actually crossed* the recorded level; `win`/`loss` from real P&L.
      The rest of the template's taxonomy (`late_entry`, `slippage`,
      `no_fill`, `gap`, `regime_change`, `data_gap`, `system_error`) needs
      tick-level timing or broker fill/rejection data this system doesn't
      capture yet — auto-classifying those would be inventing certainty the
      data doesn't support, so they're `unclassified` until a human tags
      them via the new manual override (`journal_note` table)
- [x] Journal UI (`/journal`) — entries/wins/failures/win-rate, filter by
      strategy, click a failure/loss/unclassified row to set a manual
      failure mode + "what changed" note
- [x] **Strategy versioning** — `strategy_version_history`, append-only.
      `strategy_class` is upserted in place on every plugin sync (unchanged
      behaviour), which would silently lose prior versions the moment a
      strategy's code changes — `plugin_sync.py` now logs the old
      `(version, code_hash)` before overwriting, only when it actually changed
- [x] **Markdown export → `docs/strategies/<name>.md`** — writes only
      sections 5 (Failure log) and 6 (Version history); sections 1-4 (rules,
      backtest/paper/live results) are human-authored and survive re-export
      untouched, verified by round-tripping real template content

**🐛 Real bug caught only by inspecting real export output, not by the unit
tests that were passing:** the section-replace regex used `\s` in its
separator-row character class, which matches `\n` — so it silently
swallowed the template's empty placeholder row (`| | | | |`) into the
"header" group instead of the "replaceable data rows" group. Real journal
rows got appended *after* the stale placeholder instead of replacing it. The
existing tests all checked new content was present but never checked the
placeholder was gone — fixed the regex (`[ \t\-|]` instead of `[-\s|]`) and
added that missing assertion.

**Verified end-to-end in a real browser**, both journal sources exercised
through their real code paths (not hand-inserted rows): an alert-mode
ENTER/EXIT pair via `StrategyEngine.spawn()` (correctly auto-tagged
`stopped_out` — exit price genuinely crossed the recorded stop-loss) and a
`backtest_trade` via `persist_backtest_run()`. Manually tagged the backtest
loss as `late_entry` with a note, confirmed it persisted and re-rendered.
Exported to `docs/strategies/sma-cross.md`, inspected the real file on disk,
confirmed clean output, then deleted that verification artifact — it's
synthetic test data, not real strategy documentation, and doesn't belong in
the repo's actual docs.

---

### ✅ CP7 — MCP server `DONE 2026-08-24` → *Goal #6*
- [x] Read-only tools: `list_strategies`, `get_positions`, `get_trades_today`,
      `get_portfolio`, `run_backtest`, `get_journal` — every tool is a thin
      translation layer over the real REST API (`xillion/mcp_server/client.py`),
      so each one inherits the app's real auth instead of a second path
- [x] Guarded control tools: `start_instance`, `stop_instance`, `kill_switch`
      — `kill_switch` forwards straight to the existing TOTP-gated
      `/risk/kill-switch/activate`, same gate as the web UI, never bypassed
- [x] **No freeform order construction by an LLM** — structural, not just a
      rule: there is no order-placement tool at all, and
      `test_no_order_placement_tool_exists` in `test_mcp_server.py` asserts
      the exact tool-name set so a future addition can't slip one in unnoticed
- [x] **`GET /api/positions`** (`xillion/api/positions.py`) — pulled forward
      from CP9's "Logs DB persistence + GET /api/positions" bullet since
      `get_positions` needed it now. CP9's DB-persistence half of that
      bullet is separate and still pending

**Verified for real, not just unit-tested against a mock:** installed the
official `mcp` SDK (resolved to v2.0.0 — its high-level API moved from
`FastMCP` to `mcp.server.MCPServer`, a rename this session had to discover
by inspecting the installed package rather than assuming prior knowledge of
the SDK still applied), started the real backend, created a real user via
`/api/auth/setup`, then ran an actual MCP client (`mcp.client.stdio`) doing
a real protocol handshake against the real server subprocess: `initialize()`
succeeded, `list_tools()` returned all 9 real tools, `list_strategies` and
`get_portfolio` returned real data from the real running app (including CP5's
"Condition Strategy"), and calling `start_instance` on a nonexistent id
correctly surfaced the REST API's 404 as a clean MCP tool error rather than
crashing the server.

---

### 🟡 CP8 — AI assistant + RAG `MOSTLY DONE 2026-08-24 — cloud LLM key needs YOU`
**Cross-repo:** most of this checkpoint's work is in `prosper-engine`
(`~/Documents/personal/Projects/Learnings/prosper-engine`), a separate repo.
**Its changes are uncommitted** — xillion's commit standing-authorization
doesn't extend there; review and commit them yourself.

- [x] MCP **client** + tool loop in prosper-engine's `TradingAgent`
      (`agents/trading/agent.py::_chat_with_tool_loop`, new
      `agents/trading/xillion_mcp.py`) — `chat_full()` had tool support
      since 22 days before this session but nothing ever called it with
      `tools=`; now it loops (capped at 5 rounds) executing xillion's real
      MCP tools until the model stops calling them
- [x] **Real local tool-calling, not just a mock:** `core/llm_client.py`'s
      `_ollama()` silently dropped `tools` entirely before this — verified
      live that Ollama's `/api/chat` genuinely supports tool-calling for
      qwen3:8b (its `/api/tags` capabilities include `"tools"`) and wired
      it through properly (Ollama returns already-parsed dict arguments,
      not a JSON string like the OpenAI-compatible backends — this needed
      its own code path, not reuse of the existing parsing)
- [x] Ingest `docs/strategies/*.md` + journal exports into Chroma RAG
      (`prosper-engine/scripts/ingest_xillion.py`) — CP6's markdown export
      already writes real failure-log/version-history data into these
      files, so ingesting them covers "journal exports" too, not a second
      pipeline. Idempotent (stable ids from strategy slug + section/row)
- [ ] **Hosted LLM (Gemini/Groq free tier) — NOT done, needs you.** The
      swappable backend code already existed (built 22 days before this
      session) and still works; no cloud API key has ever been configured
      (`prosper-engine/.env` has only Ollama settings). Not a blocker for
      anything above — Ollama's real tool-calling made full verification
      possible without one. Get a free-tier key (Gemini via Google AI
      Studio is the earlier recommendation) and set it in `prosper-engine/.env`
      whenever you want a faster/hosted option instead of local Ollama
- [x] Pre-trade hook: AI reviews signal → confidence % → **prediction logged
      against actual outcome**. `signal_log.ai_confidence` (migration 008)
      + prosper-engine's new `POST /confidence` endpoint. **Runs as a
      background task** (`_fetch_and_store_confidence` in
      `strategy_engine.py`), strictly after the alert has already fired and
      the signal_log row already persisted — real qwen3:8b calls measured
      at 30-60s+, far too slow to sit in a live alert's critical path.
      Journal (CP6) surfaces `ai_confidence` next to the real outcome

**🐛 Two real bugs found only by running this for real, not by unit tests:**
1. `mcp>=1.2.0` resolved to `mcp==2.0.0`, which needs `starlette>=1.x` —
   breaking prosper-engine's pinned `fastapi==0.115.0` (`APIRouter()` itself
   raised `TypeError: unexpected keyword argument 'on_startup'`) for **every
   route in the app**, not just the new one. None of the test suite caught
   it because no test imported `api.routes.*` or `api.main`. Fixed by
   pinning `mcp==1.9.4` (needs only `starlette>=0.27`) +
   `starlette==0.38.6` + `sse-starlette==1.6.5`, verified with `pip check`
   and a real `uvicorn api.main:app` boot.
2. The confidence-endpoint's regex parser didn't accept a leading `-` sign,
   so `CONFIDENCE: -10` silently fell through to the neutral-50 fallback
   instead of parsing and clamping to 0 — caught by
   `test_clamps_out_of_range_confidence`, one of this checkpoint's own new
   tests, not by manual inspection.

**Verified for real, twice, against live local Ollama (no cloud key
needed):**
1. Asked the real `TradingAgent.chat()` "what strategies are available" —
   it correctly chose to call `list_strategies` (not guess), got the real
   tool result over a real MCP stdio connection to xillion's real running
   server, and synthesized an accurate, complete answer naming all 4 real
   strategies.
2. Spawned a real alert-mode instance, fired a real ENTER signal: the alert
   sent and the signal_log row persisted in **0.06s**, then ~46s later the
   background task filled in `ai_confidence=90.0` with real reasoning about
   the setup's 3:1 risk/reward — confirmed via the journal that the
   prediction and the (still-open) outcome sit side by side, exactly the
   "prediction logged against actual outcome" this bullet asked for.

All real Chroma/prosper-engine data touched during verification (one test
chat turn, one test strategy's RAG chunks) was meant to be deleted
afterward — but that claim was premature: closing out CP8 on 2026-08-24
(re-checking the background verification task's output, `bvpc15kg3`, which
had finished with exit 0 and the exact `0.06s`/`~46.3s`/`ai_confidence=90.0`
numbers already written above) found one leftover entry in
`tenant_0__trading__strategies` — id `39b7ebb2-ef00-49c5-a98a-831968cef511`,
title "Test strategy", tag `['test']`, almost certainly left by
`scripts/ingest_xillion.py` during testing. Deleted it directly via
`chromadb.PersistentClient`. Re-verified all three collections after:
`strategies` now holds only the user's genuine "Bearish engulfing scalp";
`journal` holds one genuine EURUSD trade; `chat_history` holds two genuine
turns from 2026-03-15, predating this session. The confidence endpoint
itself (`api/routes/confidence.py`) never touches Chroma/RAG at all — "no
tools, no RAG lookup here on purpose" is in its own docstring — so this
leftover predated CP8's confidence-hook work specifically and came from
the earlier MCP/RAG ingestion verification.

The manually-started prosper-engine `uvicorn` (port 8010) and any xillion
backend from this checkpoint's verification were already stopped by the
time this close-out ran (`lsof -i :8010 -i :8799` returned nothing); no
disposable DB files were left behind either. Full xillion suite: **241
passed** (this pass also found and fixed an unrelated flaky test in CP10's
`test_digest.py` — `id(db)` used as a "unique" suffix across sessions can
collide once an earlier session object is garbage-collected; switched to
`uuid4()`, separate commit `1cb6a29`).

---

### ✅ CP9 — Automation + hardening (~17 hrs) → *Goal #7* `DONE 2026-08-24`
- [x] Order state machine — `Strategy.on_order_update` is now called as a
      fire-and-forget task right after `place_order()`'s own order-state
      transition, same pattern as `on_trade_close`
- [x] **Position reconciliation on startup** — a `live`-mode instance now
      queries the broker's real open positions before `on_start` runs, so a
      restart with real money in an open position no longer looks flat.
      Symbols outside the instance's configured instruments are ignored;
      paper mode is untouched (its own simulated positions correctly start
      flat); a broker fetch failure doesn't crash startup, it just restores
      nothing
- [x] **Live/paper real-time bar aggregation into `ctx.history()`** — found
      2026-08-24 while building CP5, fixed same day. New
      `xillion/data/bar_aggregator.py::BarAggregator` turns the live tick
      stream into bars (bucket-aligned OHLC, cumulative-volume-delta
      handling for Zerodha-shaped ticks) and publishes them onto
      `MarketDataBus`; `_tick_broadcaster` in `main.py` feeds it every tick
      alongside the existing WS broadcast. `StrategyRunner._handle_bar` now
      also pushes the bar into `ctx.history()`'s in-memory cache before
      dispatch, so `on_bar` strategies see the candle that just closed
      immediately, not just on the next DB backfill
- [x] **Risk limits were silently never enforced at all** (found while
      building this checkpoint, more severe than anything on the original
      list) — `ExecutionRouter.submit()` never passed `strategy_config`/
      `current_positions` to `risk.check()`, so every real order skipped
      the daily-loss and max-open-positions gates regardless of what was
      configured. `RiskManager.check()`'s own tests were correct and always
      had been — the bug was purely in the wiring layer between the router
      and the risk manager, which had zero test coverage before this.
      Separately, `StrategyEngine.spawn()` didn't read `risk_limits` from
      the DB at all, so even a fresh instance start ignored configured
      limits. Both fixed; `ExecutionRouter` now carries a `risk_config` +
      `set_risk_config()` for hot-reload
- [x] Auto start/stop instances at market open/close — opt-in per instance
      via a new `auto_start` column (migration `009`), toggled from the
      Strategies page. `xillion/engine/market_scheduler.py` polls
      `is_market_open()` and reacts only to open↔closed *transitions*
      (never on the first observation after process start, which would
      fire a start/stop based on an assumed prior state never actually
      observed) — chosen over hardcoding 9:15/15:30 IST like the existing
      daily-refresh tasks because `is_market_open()` already encodes the
      NSE holiday calendar, so no separate holiday awareness is needed here
- [x] Logs DB persistence + `GET /api/positions` — `GET /api/positions` was
      already done in CP7. The DB-persistence half turned out to be a
      bigger gap than expected: the Logs page was built to render a live
      `"log"` WebSocket event and claimed "scrollback retained for 24h",
      but **nothing in the backend had ever emitted that event type at
      all** — the page was live-tailing nothing and had nothing to load on
      reload either way. New `xillion/observability/log_capture.py` wires
      a structlog processor into `main.py`'s `structlog.configure()` that
      captures every `logger.*()` call app-wide (via
      `CallsiteParameterAdder` for the source module) into a bounded
      queue, drained by a background task that persists to a new
      `system_log` table (migration `010`) and broadcasts the same event
      live, with a 24h retention prune. New `GET /api/logs` for history on
      mount. Hand-verified end-to-end in a real browser: history loads on
      page load, then the line count updated live in real time after
      triggering a real backend action. **Found and fixed while wiring
      this in:** the console output's timestamp briefly regressed to a raw
      unix-epoch float — structlog's actual built-in default `TimeStamper`
      uses `fmt="%Y-%m-%d %H:%M:%S", utc=False`, not the bare
      `TimeStamper()` constructor's own default (`fmt=None` → epoch
      float); had to match the built-in default explicitly since
      overriding `processors=` replaces it silently
- [x] Self-failure alerting — if the *system* breaks, you get told. Two
      halves: (1) `xillion/observability/task_supervisor.py::supervise()`
      wraps the long-running background loops (tick broadcaster, daily
      refreshes, market-hours scheduler, log persistence) and Telegram-
      alerts on any exit that isn't a clean shutdown cancellation —
      **deliberately alerts on a clean `return` too, not just an
      exception**, because `_tick_broadcaster`'s own try/except already
      swallows its own errors and just returns, so exception-only
      detection would miss the most likely real failure (the broker's tick
      stream ending on a disconnect); (2) a strategy crashing in
      `on_start`/`on_bar`/`on_tick` now fires a Telegram alert in addition
      to the logging that already existed. Found in passing: `on_tick`'s
      exception handler never set `status="error"`/`last_error` the way
      `on_bar` and `on_start` already did — a crashed tick-only strategy
      (e.g. Nifty Spot Alert) looked identical to one running fine. Fixed
      to match. Also added a Telegram alert on a failed Zerodha connect
      attempt at startup/daily-refresh (previously logged only)
- [x] **Verify risk-limit hot-reload** — already covered by
      `test_hot_reload_tightens_limit_on_a_running_instance_without_restart`
      as a side effect of the "risk limits never enforced" fix above: an
      order approved under a limit of 5, then rejected after
      `engine.update_risk_config()` tightens it to 1 — no restart, same
      running instance. The `PUT /api/settings/risk-limits` endpoint this
      bullet originally named (from `09-progress-tracker.md`) doesn't
      exist in the current codebase; the real mechanism is
      `PATCH /instances/{id}` with `risk_limits` in the body, which was
      already wired to `engine.update_risk_config()` before this session

**Verify:** kill the process mid-position, restart, positions rebuild
correctly — confirmed via `test_live_instance_restores_a_real_open_position_on_start`
and friends. 234 tests passing (up from 175 at the start of this checkpoint).

---

### ✅ CP10 — Maintenance mode (~9 hrs) → *Goal #10* `DONE 2026-08-24`
- [x] Daily/weekly digest — the thing that makes 3–6 hrs/week real.
      `xillion/engine/digest.py::build_digest` reuses the exact same FIFO
      fill-matching `GET /api/trades` already does
      (`xillion/api/trades.py::_match_fills`), since that's the only place
      real live/paper P&L actually lives — CP6's journal (`build_journal`)
      was deliberately *not* reused here: it mixes in backtest-only data
      and alert-mode signals never carry a real fill. Sent via Telegram at
      ~4pm IST daily (after market close) and Sunday ~6pm IST weekly
      (`xillion/engine/digest_scheduler.py`), same fixed-clock-time pattern
      as the existing daily token/instrument refreshes — deliberately not
      the market-hours scheduler's transition-detection style, since a
      digest is a calendar event, not a reaction to market state
- [x] Self-healing / auto-recovery — `task_supervisor.py`'s CP9 alerting
      now actually restarts the crashed background task (tick broadcaster,
      daily refreshes, market-hours scheduler, log persistence, both
      digest schedulers), bounded to 5 restarts per 10 minutes so a
      crash-looping task doesn't spin forever; alerts on every restart
      *and* gives up with a distinct "gave up" alert once the budget is
      exceeded, explicitly telling you it won't retry again. Required
      changing `supervise()`'s signature from a bare coroutine to a
      zero-arg factory (`lambda: _daily_token_refresh(app)`), since a
      coroutine object can only be awaited once and restarting needs a
      fresh one each time — updated all 6 call sites in `main.py`
- [x] Runbook (`docs/process/runbook.md`) — every alert title quoted in it
      is copy-pasted from the actual code that sends it (cross-checked
      against `risk.py`, `zerodha.py`, `strategy_engine.py`,
      `task_supervisor.py`), not written from memory of what the alerts
      were *supposed* to say. Documents one real gap found while writing
      it: a daily-loss-limit rejection (`RiskRejected`) does **not** fire a
      Telegram alert today — it only shows up as a `REJECTED` order in
      Trades/Journal, so "strategy stopped trading, no alert fired" is a
      real, expected (if not ideal) state, not a bug to chase
- [x] 6 new tests (`test_digest.py`) + rewrote `test_task_supervisor.py`'s
      6 tests for the factory-based restart behavior (raises-and-restarts,
      clean-return-and-restarts, cancel-means-no-restart, no-notifier
      doesn't crash, crash-loop gives up after budget, gave-up alert body
      explicitly says it won't retry)

**Verified:** 241 tests passing (234 at the start of this checkpoint). Real
boot against a disposable local SQLite DB with the full supervised-task +
digest-scheduler stack wired in, zero startup errors. `build_digest` +
`format_digest_message` hand-run against that same live DB, correctly
reported "No closed trades" / "Nothing currently running" for the empty
state.

---

## TRACK A EXTENSION — Automation Platform Retrofit (added 2026-08-25)

Gap-mapped from `docs/architecture/automation-platform-spec/`'s 52-job
catalog onto what CP1-CP10 already built — see
[architecture/overview.md](../architecture/overview.md) §12.1 for the full
per-job-series mapping table this sequencing is drawn from. **Sequenced by
what blocks the first real strategy (the credit spread,
`docs/strategies/knowledge-base/10-FIRST-STRATEGY-SPEC.md`) going live**, not
by the spec's own phase numbers — Options S1/S2 (build + backtest) can start
in parallel with CP11-CP13 since the strategy itself is single-leg-testable
before multi-leg execution is finished, but CP11 (multi-leg + protective
orders) is a hard gate before Options S4 (live).

### ✅ CP11 — Multi-leg execution + protective orders `DONE 2026-08-25 — bracket/GTT gap closed for Zerodha, verified-blocked for Dhan`
- [x] Multi-leg position model — [xillion/core/multileg.py](../../xillion/core/multileg.py):
      `MultiLegSpec`/`Leg`/`LegRole` group 2-4 broker orders into one logical
      structure. Deliberately does NOT add a parallel position-tracking
      table — each leg still flows through the existing per-symbol
      `Position`/`PositionRecord` machinery (`ctx.place_order` per leg), so
      there's one source of truth per symbol and the coordination layer
      (ordering + rollback) sits on top rather than duplicating state
- [x] Leg-ordering discipline on entry/exit — **longs first on entry, shorts
      first on exit** — `order_entry_sequence`/`order_exit_sequence` in
      `multileg.py`, enforced regardless of the caller's list order
- [x] **Leg-failure protocol (E05)** — [xillion/core/multileg_execution.py](../../xillion/core/multileg_execution.py)
      `MultiLegExecutor`. Naked-short detection is per-leg (`protects_leg_index`
      pairing, not a hardcoded 2-leg assumption — generalises to condor/
      butterfly). Force-unwinds at market on a naked short, retries once and
      unwinds cleanly on a defined-risk partial, halts for human review on
      an unclassifiable partial. 12 unit tests cover the spec's own E05
      acceptance-test list (long fills/short rejected → retry→unwind; short
      held without its protecting long → force-unwind; partial fill above/
      below the 50% ratio; a leg stuck open past the fill timeout)
- [x] **Protective order placement (E07)** — [xillion/core/protective_orders.py](../../xillion/core/protective_orders.py)
      computes stop/target/time-stop levels from the real fill price; the
      credit-spread strategy monitors them every tick and fires a real
      market exit order (shorts-first) through the same leg-failure
      protocol when triggered. The spec's own caveat applies: a software
      stop needs the process alive to fire; an always-on watchdog independent of the
      strategy's own tick loop is CP12's job, not this one's
- [x] Position sizing for multi-leg — `size_defined_risk_position()` in
      `multileg.py`, `lots < 1 → skip, don't round up`, unit-tested against
      the exact KB `10-FIRST-STRATEGY-SPEC.md` §7 worked-example numbers
      (Nifty 200-wide → 0 lots, Nifty 50-wide → 1 lot, Sensex 100-wide →
      1 lot)
- [x] First real consumer built end-to-end: `strategies/credit_spread_weekly.py`
      (Options Stage 1) — see [docs/strategies/credit-spread-weekly.md](../strategies/credit-spread-weekly.md)
- [x] **Follow-up, 2026-08-25: Options Stage 2 (backtest) unblocked.**
      [xillion/data/option_chain.py](../../xillion/data/option_chain.py) —
      `HistoricalOptionRow` + `OptionChainWarehouse`, same cache-on-fetch/
      whole-file-bulk pattern as CP2's `BarWarehouse`, sourced from NSE
      Bhavcopy's own `StrkPric`/`XpryDt`/`OptnTp`/`UndrlygPric` columns
      (confirmed against a real live file fetched 2026-08-24, not assumed —
      `UndrlygPric` in particular is the exchange's own recorded underlying
      close, used as the backtest's spot proxy with no separate index feed
      needed). New `option_chain_snapshot` table (migration 011) — a
      DATE-SCOPED snapshot, deliberately separate from the live `instrument`
      table (a truncate-and-reload cache of TODAY only, useless for "what
      did NIFTY's chain look like on 2026-03-06"). `_BacktestContext` in
      `backtest_engine.py` now implements `get_spot`/`resolve_strike`/
      `get_option_price`/`subscribe_instrument`, reusing the SAME
      `resolve_option()` the live path uses — no second resolver. Wired
      into all three `/backtest/run*` API endpoints.
      **A deeper bug this surfaced and fixed, not assumed away:**
      `StrategyContext` had no environment-aware "what time is it" — the
      credit-spread strategy's entry-window/DTE gates called a bare
      `datetime.now()`, which only works for live/paper (bars arrive in
      real time); a real multi-year backtest replaying history would only
      ever check against *today's* real date regardless of which period
      was being simulated, so the DTE gate would pass by coincidence at
      best. Fixed by adding `StrategyContext.now()` (live: real wall-clock;
      backtest: the currently-simulated bar's own timestamp) — the
      strategy now calls `ctx.now()`, not `datetime.now()`.
      **Also found and fixed:** a MARKET order for a freshly-resolved
      option leg filled at price 0 in backtest mode, because
      `_last_price` (what `place_order`'s MARKET fallback reads) was only
      ever populated by the bar-driven symbol, never by a dynamically
      resolved leg — fixed by caching the fetched close in `get_option_price`
      itself, the same place the strategy already fetches it to compute
      credit.
      BacktestEngine's main loop now also synthesizes a daily Tick for
      every dynamically-subscribed option leg after each `on_bar` (bhavcopy
      is EOD-only, so this is honestly daily granularity, not a claim of
      intraday accuracy) — without this, `on_tick`-driven exit logic
      (CP11's protective-order monitoring) would never fire in a backtest
      at all, since `BacktestEngine.run()` only ever called `on_bar`.
- [x] **Follow-up, 2026-08-25: the real-broker bracket/GTT gap, narrowed —
      Zerodha done, Dhan verified-blocked, not guessed at either way.**
      First verified the old `supports_bracket_orders=True` flag against
      Kite Connect's *current* API docs, not assumed from the flag's own
      value: Zerodha discontinued bracket orders entirely (`"bo"` isn't a
      valid `variety` any more) — the flag now correctly reads `False`.
      GTT triggers are still real and supported, so that's what got built:
      `Broker.place_protective_gtt()`/`cancel_gtt()`
      (`xillion/core/broker_base.py`) + a real `ZerodhaBroker`
      implementation verified against the actual installed `kiteconnect`
      SDK source (`place_gtt`/`_get_gtt_payload`), not the docs alone.
      **A genuine, honestly-documented approximation, not an exact
      mirror:** Kite's GTT triggers on ONE instrument's own LTP, but the
      software stop triggers on `spread_value` (short leg LTP minus long
      leg LTP) — no single-instrument trigger can express a two-leg net
      condition. `short_leg_gtt_levels()` converts the spread-value
      threshold to an approximate short-leg-only price by holding the long
      leg's entry-fill price fixed — a real circuit-breaker for the worst
      case (process down, software stop can't fire), not a precision
      replacement for the tick-driven check that's still primary.
      `credit_spread_weekly.py` places this GTT right after entry fills
      and cancels it on any genuine exit — but deliberately **not** on
      `HALTED_FOR_HUMAN` (an unclassifiable partial fill), since the
      broker-side position is unclear exactly then and cancelling would
      remove the protection that window most needs.
      **Dhan verified-blocked at the time, not silently skipped** — Dhan's
      own equivalent ("Forever Orders") is real and documented
      (dhanhq.co/docs/v2/forever/), but its `productType` field only
      accepts `CNC`/`MTF` while `brokers/dhan.py` hardcoded every regular
      order's product to `INTRADAY`. Building Forever-Order support then
      would either silently fail against the real API or require changing
      what product type Dhan positions trade under — a bigger, separate
      decision, not guessed at here. **Resolved 2026-08-29 — see the
      follow-up entry below.**
      **Also found and fixed in the same broker-capability area:**
      `POST /brokers/connections/{name}/reconnect` was hardcoded to
      `"Zerodha Primary"` only — Dhan's own Reconnect button in Settings →
      Active connections would have 400'd. Now dispatches by connection
      name generically.

**Verify:** 33 unit tests (`test_multileg.py`, `test_multileg_execution.py`,
`test_protective_orders.py`) + 6 integration tests
(`test_credit_spread_strategy.py`) for the original CP11 scope, PLUS 7 unit
tests (`test_option_chain.py`, including the real-column-name parser check)
and 2 integration tests (`test_credit_spread_backtest.py`) for the
backtest follow-up, PLUS the 2026-08-25 GTT follow-up: 5 unit tests
(`test_zerodha_protective_gtt.py`, against the real installed SDK's method
signature) + 2 unit tests (`short_leg_gtt_levels` in
`test_protective_orders.py`) + 3 integration tests (GTT placed on entry,
cancelled on genuine exit, preserved on `HALTED_FOR_HUMAN`, in
`test_credit_spread_strategy.py`) + 4 unit tests
(`test_broker_reconnect.py`) for the reconnect fix. **A real,
pre-existing test-isolation bug found and fixed along the way:**
`test_credit_spread_strategy.py`'s `FakeContext.OPTION_PRICE` was a shared
*class-level* dict — one test's `ctx.OPTION_PRICE[...] = X` silently
leaked into every later test's fresh instance, since Python attribute
lookup falls through to the class for an unshadowed mutable default. Now
copied per-instance in `__init__`. 418/418 tests passing, no regressions.
**Not yet done:** NSE-listed underlyings only for backtest options
(NIFTY/BANKNIFTY; Sensex is BSE-listed, NSE Bhavcopy doesn't cover it).

**Follow-up, 2026-08-29: Dhan's Forever-Order path, unblocked.** Rakesh's
decision (asked directly, since this is a real capital/margin-cost
tradeoff no amount of code review substitutes for): switch Dhan's product
type from `INTRADAY` to `MARGIN` (Dhan's NRML-equivalent F&O carry
product — Dhan has no NRML label; `MARGIN` is the one that isn't
intraday-only, confirmed against the installed `dhanhq` SDK's own class
constants: `CNC`/`INTRA`/`MARGIN`/`CO`/`BO`/`MTF`, no `NRML`), and attempt
Forever Orders with it despite Dhan's own docs restricting that specific
endpoint's `productType` to `CNC`/`MTF`.
- `brokers/dhan.py`: `_PRODUCT_TYPE` changed to `"MARGIN"` for every
  order — this is also what fixes the actual underlying problem the
  product-type item was originally flagging: the credit spread and iron
  condor hold positions across days until expiry, which `INTRADAY` would
  have auto-squared-off same-day at Dhan, silently breaking both
  strategies the moment either went live there.
- New `place_protective_gtt()`/`cancel_gtt()` on `DhanBroker`, mirroring
  `ZerodhaBroker`'s existing shape (`Broker.place_protective_gtt()`'s own
  docstring already anticipated "Dhan's Forever-Order-OCO shape" when it
  was written). Built against Dhan's real Forever Order docs
  (dhanhq.co/docs/v2/forever/) and the installed SDK's `place_forever()`
  signature: `price`/`triggerPrice` are the STOP_LOSS_LEG, `price1`/
  `triggerPrice1`/`quantity1` are the TARGET_LEG (per Dhan's own field
  descriptions — "Target price/trigger/quantity for OCO order" on the
  `1`-suffixed fields specifically), one shared `transactionType`/
  `orderType` for the whole OCO pair (simpler than Kite's per-leg
  `orders[]` array). `DhanBroker.capabilities.supports_gtt_orders` is now
  `True` — since `StrategyContext.place_protective_gtt()` already
  dispatches generically off that flag (`xillion/engine/
  strategy_engine.py`), `credit_spread_weekly.py` now places a real
  Forever Order on Dhan too, with **zero strategy-code changes** — the
  generic architecture from CP11 just started working for a second
  broker the moment the capability flag and implementation existed.
  (Iron Condor Weekly deliberately still has no GTT wiring on either
  broker — see its own scope-cut note above.)
- **Honest, prominent caveat, not buried:** whether Dhan's server
  actually accepts a Forever Order for an F&O leg carried under `MARGIN`
  — given the docs' own `CNC`/`MTF`-only restriction on that specific
  endpoint — is **genuinely unverified**. No Dhan account exists in this
  sandbox to place one. Built exactly as documented; if it turns out to
  be a hard rejection in practice, the software stop (already the
  primary protection mechanism regardless, per `protective_orders.py`'s
  own module docstring) is unaffected. Logged in
  [docs/status/manual-tasks.md](../status/manual-tasks.md) as the actual
  thing to watch for the first time this runs live/paper on Dhan with
  GTT enabled — not silently assumed to work.
- **Verify:** 7 new tests in `test_dhan_protective_gtt.py` (capability
  flag, product-type constant, stop-only single-flag request shape,
  stop+target OCO request shape with the correct leg-field mapping,
  failure-envelope handling, cancel, cancel-swallows-errors) + 1 existing
  `test_dhan_broker.py` assertion updated (`product_type` from
  `INTRADAY` to `MARGIN`, matching the decision, not a silent behaviour
  drift). 510/510 tests passing, no regressions. ruff/black/mypy all
  clean.

**Multi-leg beyond 2-leg, 2026-08-29: Iron Condor Weekly (4 legs) built —
and building it surfaced two real bugs the credit spread's 2-leg shape
could never expose.** CP11's own multileg.py/multileg_execution.py were
designed generic from the start ("protects_leg_index pairing, not a
hardcoded 2-leg assumption -- generalises to condor/butterfly") but had
never actually been exercised past 2 legs until now.
- [strategies/iron_condor_weekly.py](../../strategies/iron_condor_weekly.py)
  (KB 03 A1) — same weekly-cycle conventions as the credit spread
  (09:45-10:30 entry window, VWAP+EMA trend check, entry_dte/time_stop_dte
  defaults), but the OPPOSITE market view: enters exactly when the trend
  check finds NEITHER a bull NOR a bear signal (the credit spread's own
  "no clear trend, skipping entry" branch is this strategy's entry
  signal) -- KB's own regime guidance: "range-bound -> neutral structures
  (condor)... do not sell a neutral structure into a trend day."
  `protective_orders.py`'s new `condor_value()` sums both sides'
  `spread_value()` and feeds the SAME generic `credit_spread_protective_
  levels()`/`check_exit_trigger()` the credit spread already uses --
  those functions never cared how many legs produced the number.
  **Deliberate scope cut, documented not hidden:** no broker-native GTT
  backstop for this structure (splitting a combined stop/target across
  two independent single-instrument GTTs needs its own allocation logic
  that doesn't exist yet); the software stop remains primary regardless.
- **Two real bugs found and fixed in
  [xillion/core/multileg_execution.py](../../xillion/core/multileg_execution.py)
  while designing the 4-leg entry/exit paths, before writing a single
  line of the strategy itself:**
  1. **Entry silently truncated beyond 2 legs.** The old `_execute` broke
     out of its loop on the FIRST leg failure, so for the credit spread's
     exactly-2-leg case there was never anything left to attempt anyway --
     invisible. For a condor, a failure on ONE pair's long leg meant the
     OTHER, entirely unrelated pair's short legs were never even
     attempted, and the function could report SUCCESS or UNWOUND against
     an incomplete leg set that was never fully placed. Fixed: `_execute`
     now walks the complete ordered sequence, with a new
     `_blocked_by_dependency()` gate that skips (never places an order
     for) only a leg whose OWN dependency already failed -- a SHORT leg
     whose protecting LONG failed on entry, or a LONG leg whose protected
     SHORT failed to close on exit. Retry-once now happens inline per
     leg, immediately at the point of failure, rather than being deferred
     to the rollback handler.
  2. **A failed EXIT could re-open a leg that had just closed
     successfully.** The naked-short "force unwind" reversal logic only
     makes sense on ENTRY (undo a newly-created naked position by closing
     it). Applied to a failed EXIT -- short's close succeeds, long's
     close then fails -- the old code saw "a filled SHORT without its
     LONG" and force-unwound by REVERSING the short's already-successful
     close, i.e. placing a fresh SELL, recreating the exact naked
     position the whole protocol exists to prevent. This was a latent
     bug in the 2-leg case too, sitting there since CP11 -- nothing had
     ever tested a leg failing partway through an exit. Fixed:
     `_rollback` now handles `is_exit` as its own case with no reversal
     logic at all -- everything in `filled` during an exit is
     legitimately closed already (that's the goal), so the only real
     problem is what's still open, which now halts for human review
     instead of being "reversed" into a new position.
  Both fixes are fully backward-compatible with the credit spread's
  existing behaviour -- all 44 pre-existing tests across
  `test_multileg_execution.py`/`test_multileg.py`/`test_protective_
  orders.py`/`test_credit_spread_strategy.py` pass unchanged against the
  refactored code, verified before writing a single new test.
- **Verify:** 14 tests in `test_multileg_execution.py` (10 new: condor
  all-4-legs success, independent pair still entered when the other's
  long fails, no false naked-short positive on the successful pair, two
  independent failures halts for human, the exit-reversal bug's own
  regression test on the ORIGINAL 2-leg case, and the condor exit-side
  equivalent) + 8 in `test_iron_condor_strategy.py` (entry sizing against
  KB's worked numbers, leg ordering, range-bound vs. trending entry gate,
  DTE/sizing skip paths, stop/target exit, and the leg-failure-unwinds-
  the-completed-pair scenario) + 2 in `test_protective_orders.py`
  (`condor_value`) + 1 in `test_multileg.py` (`max_loss_per_lot` against
  KB A1's own 200-wide/55-credit/lot-65 worked example: ₹9,425). 503/503
  tests passing overall, no regressions. ruff/black/mypy all clean.
  **Not yet run:** an options-chain backtest (the infra exists from the
  credit spread's own Stage 2 work and this strategy's shape should fit
  it unmodified, but genuinely hasn't been tried), and everything else
  Stage 3/4 (paper, live) -- see
  [docs/strategies/iron-condor-weekly.md](../strategies/iron-condor-weekly.md).

**Multi-leg beyond 2-leg, 2026-08-29 continued: Butterfly Weekly, the third
multi-leg strategy and the first DEBIT one.** Same day as the iron condor --
picked up as the next well-scoped item on the "Blocked on you #7" list
(credit spread + condor + butterfly, "all fully specced"), now none of
them unbuilt.
- [strategies/butterfly_weekly.py](../../strategies/butterfly_weekly.py)
  (KB 06 D1) -- 1:2:1 ratio, equidistant strikes, one option type. Reuses
  the SAME weekly-cycle conventions (09:45-10:30 entry window, VWAP+EMA
  trend check) as the other two, `entry_dte` defaulted to 1 rather than 4
  (KB D1's own cycle stage is S4-S5, DTE 1-0).
  **Modeled as 4 orders at 3 distinct strikes, not 3 legs with a 2-lot
  middle order** -- the middle strike's 2-lot short is split into two
  independent 1-lot `Leg`s, each with its own `protects_leg_index` (one
  per wing), rather than a single Leg with quantity=2*lot_size. A
  butterfly's middle short is protected by BOTH wings at once, which the
  existing `protects_leg_index` model can't express as a single 1:1
  pairing -- splitting it into two legs reuses the SAME naked-short
  isolation logic the condor's independent call/put pairs already proved
  out, rather than needing a new N:1 pairing concept. Proven correct by
  its own leg-failure test (below): when one wing is rejected, only the
  middle-strike short protecting THAT wing is correctly blocked from ever
  being placed, while the other wing's pair (which succeeded) is placed
  then cleanly unwound.
- **New debit-structure protective-order math in
  [xillion/core/protective_orders.py](../../xillion/core/protective_orders.py):**
  `butterfly_value()` (`2*short_middle_ltp - (long_lower_ltp +
  long_upper_ltp)`) and `butterfly_protective_levels()`. The credit spread
  and condor's `check_exit_trigger()` assumes "value rising = bad, falling
  = good" -- true for a CREDIT structure's cost-to-close, but a debit
  butterfly's own value moves the OPPOSITE way with P&L on the surface.
  The fix wasn't a new trigger function: `butterfly_value()` uses the
  SAME Sigma(short)-Sigma(long) convention as `spread_value()`/
  `condor_value()`, which (worked through the actual entry/max-profit/
  total-loss cases against KB D1's own worked example: 25 debit, 100
  width) turns out to already fall in the right direction for a debit
  structure too -- so `check_exit_trigger()` needed ZERO changes, only
  `butterfly_protective_levels()` converting profit-space targets
  (% of max profit, % of debit given back) into that same cost-to-close
  space. No KB-cited management percentages exist for D1 the way A1/A2
  have explicit ones -- the 50%-of-max-profit target and 75%-of-debit
  stop defaults are this codebase's own reasonable choices, stated
  honestly in the function's own docstring, not presented as KB-derived.
- **Time stop handled differently from the other two strategies, on
  purpose:** `ProtectiveOrderSpec.time_stop_date` is date-only, and
  `check_exit_trigger()` fires the instant the calendar date arrives --
  fine for the credit spread/condor (which want to exit BEFORE expiry-day
  gamma), wrong for the butterfly (whose whole edge is holding THROUGH
  expiry day for the pin). Using that field here would force-exit at the
  first tick of the very day the strategy exists to hold through. Left
  unset; `on_tick` instead checks its own inline date+time-of-day gate
  (15:10 IST on the expiry date, ahead of X02's 15:15 IST square-off).
- **Verify:** 7 new tests in `test_protective_orders.py` (`butterfly_value`
  at entry/max-profit/total-loss against the KB worked example,
  `butterfly_protective_levels` matching the worked example's exact
  numbers, reuse of `check_exit_trigger()` unmodified, both validation
  errors) + 11 in new `test_butterfly_strategy.py` (correct sizing against
  KB's own ₹1,625 max-loss-per-lot worked example, wing-then-middle entry
  ordering, range-bound entry gate, DTE/size/non-positive-debit/reward-
  risk skip paths, stop/target exit, the expiry-day flatten-time force
  exit, and the leg-failure test proving the split-middle-leg design
  actually isolates a single wing's failure). 542/542 tests passing
  overall, no regressions. ruff/black/mypy all clean (mypy scoped to
  `xillion/` per the Makefile's own gate -- `strategies/`, like
  `brokers/`, isn't in it).
  **Not yet run:** an options-chain backtest, and everything else Stage
  3/4 (paper, live) -- see
  [docs/strategies/butterfly-weekly.md](../strategies/butterfly-weekly.md).

---

### ✅ CP12 — Trailing-stop engine `DONE 2026-08-25 — watchdog gap narrowed, not fully closed`
- [x] Three trailing algorithms + the ratchet enforcement point —
      [xillion/core/trailing_stop.py](../../xillion/core/trailing_stop.py):
      `fixed_trail` (spec §3.2.1, generic baseline), `r_ladder_trail` (spec's
      own "recommended default"), `credit_trail` (spec §3.2.6 — the
      credit-spread-specific one, trails on captured credit %, never on
      underlying spot per the spec's explicit "category error" warning).
      ATR/chandelier and swing-structure trails (need bar history +
      indicators) not implemented — a natural next addition, not required
      by this checkpoint's own "at least one algorithm" bar
- [x] **Ratchet property-tested**: `ratchet()` is the single point every
      algorithm routes through (`max` for LONG, `min` for SHORT); a
      dedicated property test runs 1000 independent random price paths ×
      2 directions × 30 steps each (30,000 checks total) asserting the
      stop is monotonic at EVERY step, not just start-vs-end. Stdlib
      `random` with a fixed seed rather than adding a `hypothesis`
      dependency for one property
- [x] Breakeven-shift trigger (T05) — `breakeven_shift()`/`apply_breakeven_shift()`,
      fires once at the configured R-multiple, sets a flag so it can't
      re-fire, still routes through the ratchet
- [x] Time-stop enforcement — already existed from CP11
      (`protective_orders.py`'s `check_exit_trigger` TIME_STOP branch); not
      duplicated here
- [x] **"Survives a process restart" — the real watchdog-gap work.**
      `ctx.state` now genuinely persists to `StrategyInstance.state_blob`
      and restores on the next `spawn()` — that column has existed in the
      schema since migration 001 and `StrategyContext`'s own docstring
      claimed this happened ("persisted to DB on on_stop, restored on
      on_start"), but nothing ever wrote or read it; `ctx.state` silently
      reset to `{}` on every single spawn. This is what actually would let
      a real trailing-stop's state (or CP11's credit-spread protective
      levels) survive a deliberate restart. Persisted two ways: awaited on
      a clean `StrategyRunner.stop()` (guarantees the FINAL state lands),
      and fire-and-forget after every `on_bar` (crash resilience for the
      common case — a process killed between bars still has the last
      bar's state on disk). Pickle, not JSON, matching the column's
      `LargeBinary` type and the state's potential non-JSON contents
      (Decimal, etc)

**Honest gap, narrowed but not closed:** this makes a *deliberate* restart
(redeploy, manual stop/start) safe — state is genuinely there when the
process comes back. It does **not** add an independent watchdog that
detects an *ungraceful crash* and restarts the instance itself (the
automation spec's K03 heartbeat/watchdog job) — if the process dies without
calling `stop()`, only the last on_bar's fire-and-forget snapshot exists,
and nothing currently notices the crash and acts on it. That remains open.

**Verify:** `test_trailing_stop.py` (20 tests, including the 30,000-check
ratchet property test) + `test_strategy_state_persistence.py` (3 integration
tests: state survives a clean stop+respawn with a brand-new engine/bus,
`on_start`'s `setdefault` doesn't clobber restored values, and fire-and-
forget persistence after `on_bar` doesn't require waiting for a clean
stop). 312/312 tests passing, no regressions.

---

### ✅ CP13 — Expanded risk engine `DONE 2026-08-25`
- [x] Brought `RiskManager.check()` from 6 checks to **18** —
      [xillion/core/risk.py](../../xillion/core/risk.py), table-driven
      (`checks: list[tuple[name, ok]]`, matching the spec's own
      `validate_order()` shape) rather than nested early-returns, both for
      readability and because it made 100% branch coverage tractable.
      Priority order followed exactly as `risk-and-compliance.md` Part C.1
      specified:
      1. **Price collar** (`price_collar` — order price within 0.5x-1.5x
         LTP) + **OPS cap tightened to 7/sec** with a genuine 9/sec hard
         ceiling — hitting the hard ceiling now fires the kill switch
         (runaway-loop signal per spec §10.3: "a loop that generates 9
         orders/second will generate 9,000"), tracked on a SEPARATE
         attempt-window from the soft-throttle accepted-window, since the
         runaway signature is attempt rate, not accepted-order rate
      2. **Idempotency-key dedup** (`not_duplicate` — a client_order_id
         re-submitted within 5 minutes is rejected)
      3. Prop-firm DD gates — still deferred to Lane B, unchanged
      Also added, all from the spec's same check groups: `qty_lot_multiple`,
      `qty_within_freeze`, `qty_sane`, `price_tick_multiple`,
      `price_within_circuit`, `notional_sane`, `trading_enabled` (a softer,
      manually-reversible pause distinct from the kill switch), `order_count_sane`
      (per-strategy daily order cap), `not_self_trade` (opposite-side open
      order on the same symbol — `ExecutionRouter.submit()` now supplies
      this from its own `get_open_orders()` automatically). Every new
      market-data-dependent check (`price_collar`, `price_tick_multiple`,
      `price_within_circuit`, `notional_sane`, `qty_lot_multiple`,
      `qty_within_freeze`) is **skipped, not failed,** when the caller's
      `MarketContext` doesn't supply that field — honestly documented as
      not yet wired to a live broker quote (no code path constructs one
      pre-trade today), not silently treated as passed.
      **Deliberately NOT implemented, and why:** `margin_sufficient` (would
      need a synchronous pre-trade broker RPC — a real latency tradeoff not
      decided yet), `market_open`/`symbol_tradeable` (risk of regressing
      paper/alert-mode testing outside market hours without deciding what
      "mode-aware" means for this check first), `modify_rate_ok`
      (`modify_order` itself isn't implemented anywhere in the codebase yet
      — nothing to rate-limit).
- [x] **100% branch coverage on `xillion/core/risk.py`** — verified with
      `pytest --cov=xillion.core.risk --cov-branch`, not just "tests pass."
- [x] **Audit log wiring** — `xillion/core/audit.py`'s `AuditLog`/
      `AuditLogRecord` (hash-chained, append-only) existed in the schema
      and as working code since early in the project, but nothing ever
      called `.record()` — risk decisions were only ever visible in
      structlog output. `ExecutionRouter.submit()` now writes every
      decision (approved or rejected, with the specific failed check
      names) here, **awaited, not fire-and-forget** — matching the spec's
      own K04 requirement that order-event audit writes are synchronous on
      the critical path.
      **A real bug this caught, not a hypothetical:** the first version of
      this used `asyncio.create_task()` (fire-and-forget, matching this
      file's OWN precedent for `_persist_order`/`_persist_trade_close`) and
      it reliably **hung the entire integration test suite** partway
      through — orphaned audit-write tasks from earlier tests, still
      holding the shared SQLite connection when their test's event loop
      tore down, blocked a later test's DB access indefinitely. Switching
      to awaited (which the spec asked for anyway) fixed it outright.

**Verify:** a deliberately fat-fingered order (10x the LTP) is rejected
before it reaches the broker adapter (`test_risk_audit_log.py`'s
`test_fat_fingered_price_is_rejected_before_reaching_the_broker` — asserts
`broker.placed_orders == []`), with the specific failed check
(`price_collar`) named in a real `audit_log` row, not just a log line.
343/343 tests passing (53 in `test_risk_manager.py` alone), no regressions.

---

### ✅ CP14 — Scheduled EOD reconciliation + flatten-at-close `DONE 2026-08-25`
- [x] **X02 — square-off enforcer** — [xillion/engine/square_off.py](../../xillion/engine/square_off.py).
      Deliberately driven by a `Broker` only, nothing from `StrategyEngine`/
      `StrategyContext` — per the spec, this job "must work when everything
      else is broken" and "does not check whether strategies are armed…
      it queries the broker for open positions and closes them." Queries
      `broker.get_positions()`, closes anything nonzero at MARKET, then
      **re-queries to verify** rather than trusting the close order's ack —
      an unverified close is exactly the kind of assumption CP11's E06 also
      refused to make. Scope note: implements the safety property (nothing
      open past close) immediately at MARKET rather than the spec's full
      13-minute price-improvement ladder (warn → soft LIMIT → aggressive →
      MARKET → verify) — strictly safer, not price-optimal; the staged
      ladder is a natural next refinement, honestly deferred, not silently
      dropped.
- [x] **M01 — broker reconciliation** — [xillion/engine/reconciliation.py](../../xillion/engine/reconciliation.py),
      independent of X02 (runs 30 min later, its own scheduled trigger) so
      it's a genuine second check, not just X02 grading its own homework.
      Compares broker positions against `PositionRecord` three ways
      (broker-only, internal-only, quantity-mismatch) and additionally
      flags **any** open position at EOD as a discrepancy even when both
      sides agree — matching the spec's "must be FLAT at EOD for intraday
      strategies" rule. Persisted to a new `reconciliation_report` table
      (migration 012) — not just logged, so a `DISCREPANCY`/`FAILED` day is
      a durable, queryable fact per the spec's own "block tomorrow's
      trading if not CLEAN" design (that blocking behaviour itself wasn't
      wired to anything at the time — see "CP14 follow-up, 2026-08-28"
      below, where it was closed). **Scope note (original, 2026-08-25):**
      positions only — orders/fills reconciliation and funds (broker P&L
      vs computed P&L) reconciliation are NOT implemented; funds
      specifically needs a "today's realised P&L" broker capability the
      `Broker` ABC doesn't expose today, honestly left as a gap rather
      than faked. **Orders/fills closed 2026-08-29 — see "CP14 follow-up,
      2026-08-29" below. Funds also closed 2026-08-29 — see "CP14
      follow-up: funds reconciliation" further below.** M01's original
      scope note is now fully closed.
- [x] Both wired as their own supervised background tasks in
      [xillion/main.py](../../xillion/main.py) — X02 at 15:15 IST, M01 at
      15:45 IST, same sleep-until-next-fixed-clock-time pattern as CP10's
      digest scheduler, deliberately two separate loops (not one combined
      job) so a bug in one can't silently take out the other.

**Verify:** the crash scenario simulated directly — a real open position at
the broker with nothing in xillion's memory aware of it (no StrategyEngine
involved at all) — then X02 and M01 run in sequence exactly as the
scheduler would: good path (`test_x02_flattens_then_m01_confirms_clean`)
X02 flattens it and M01 independently confirms CLEAN; bad path
(`test_x02_fails_to_flatten_and_m01_catches_it_loudly`) X02's close order
is rejected, and M01 still shows the position as an EOD `DISCREPANCY` with
a critical alert fired — never silently carried forward. 367/367 tests
passing, no regressions.

**CP14 follow-up, 2026-08-28: the "block tomorrow's trading" gate itself,
closed.** Picked up as the next well-scoped Track A item after Gold Lane
B1's plumbing shipped, per Rakesh's "complete all planned code
implementation" redirect — this needed no external hardware/account,
unlike Gold Lane B1, so it was a natural next piece.
- **Migration 015** adds `acknowledged` / `acknowledged_at` /
  `acknowledged_by` to `reconciliation_report` — the durable "a human
  reviewed this" record the spec's "manual sign-off to resume" line needs.
  Applied to the real Supabase DB this session (013→015), not just
  written — confirmed via `alembic current`.
- **The gate itself:**
  [xillion/engine/reconciliation.py](../../xillion/engine/reconciliation.py)'s
  new `unresolved_blocker_exists()` looks at the MOST RECENT trading date
  that has any report and returns true if anything on it is non-CLEAN and
  unacknowledged — deliberately "most recent day", not "every day ever",
  so a stale unsigned-off day from weeks ago can't block forever once a
  later clean day exists.
  [xillion/engine/eod_scheduler.py](../../xillion/engine/eod_scheduler.py)'s
  M01 tick (`run_reconciliation_tick`, split out from the scheduler loop
  so it's directly testable) calls `risk.pause_trading()` when any
  broker's report isn't CLEAN.
  [xillion/main.py](../../xillion/main.py) startup re-derives the same
  gate from the DB on every boot — the pause is otherwise only an
  in-memory `RiskManager` flag, which a Render redeploy/restart would
  otherwise silently clear even with a genuinely unresolved DISCREPANCY
  still on the books.
- **Manual sign-off:** new
  [xillion/api/reconciliation.py](../../xillion/api/reconciliation.py) —
  `GET /reconciliation/reports` (list) and
  `POST /reconciliation/reports/{id}/acknowledge` (sign off; resumes
  trading only if nothing else unresolved remains for that trading day —
  a second broker's still-open DISCREPANCY on the same day correctly
  keeps the gate up).
- **Frontend:** `Layout.tsx` now shows a distinct "TRADING PAUSED" banner
  (separate from the kill-switch banner) when `risk.status().trading_enabled`
  is false, linking to a new "Reconciliation (M01)" panel added to
  Configuration → Risk tab — lists recent reports and lets you acknowledge
  an unresolved one.
- **Honest limitation, not silently glossed over:**
  `RiskManager.pause_trading()`/`resume_trading()` is a single global
  boolean with no "who/what paused it" tracking. As of this writing M01's
  gate is its only caller, so the acknowledge endpoint resuming trading is
  safe — but if any other feature is ever wired to the same flag (a
  maintenance pause, say), this needs to become a reason-aware gate
  instead of a bare boolean, or two unrelated pause reasons could clear
  each other.
- **Verify:** 9 new tests (5 in `test_reconciliation.py` covering
  `unresolved_blocker_exists()` — unacknowledged/acknowledged/CLEAN/
  same-day-partial-signoff/only-latest-day-matters; 4 in new
  `test_eod_scheduler.py` covering `run_reconciliation_tick()` — CLEAN
  leaves trading enabled, DISCREPANCY and FAILED both pause it, and a
  paused gate genuinely rejects a real `RiskManager.check()` call, not
  just a status flag). 462/462 tests passing, no regressions (caught and
  fixed a self-inflicted mistake along the way: an early draft of
  `test_eod_scheduler.py` was written with `Write` instead of `Edit` and
  silently clobbered that file's pre-existing CP14 timing/broker-discovery
  tests -- restored by merging both sets into one file before committing).
  Migration
  applied and confirmed against the real Supabase DB
  (`alembic current` → 015). ruff/black/mypy all clean; frontend `tsc
  --noEmit` and `vite build` both clean. **Not verified: the actual
  logged-in UI** (banner + Reconciliation panel rendering, acknowledge
  button working end-to-end) — entering the dev login password is outside
  what Claude will do itself even for a local app, so this needs Rakesh's
  own look once he's testing.

**CP14 follow-up, 2026-08-29: orders/fills reconciliation, M01's other
positions-only gap, closed.** Same M01 job, extended rather than a
parallel system -- reuses the trading-gate wiring from the day before with
no new gating logic needed, since "any order mismatch" now just adds to
the same `order_mismatches` list the status computation already checks.
- **Migration 016** adds `order_mismatches_json` to `reconciliation_report`.
  Applied to the real Supabase DB and confirmed (`alembic current` → 016).
- **The check itself:**
  [xillion/engine/reconciliation.py](../../xillion/engine/reconciliation.py)'s
  new `_reconcile_orders()` compares today's `OrderRecord` rows (scoped to
  the specific `BrokerConnection` being reconciled, and to rows submitted
  today -- a multi-day option hold's original entry order correctly isn't
  compared against a "today" list it was never going to be on) against
  `broker.get_orders_today()`, matched by `broker_order_id` -- deliberately
  NOT by `client_order_id`/tag, since e.g. `brokers/zerodha.py`'s
  `_kite_to_order` falls back to the order tag for that field and isn't a
  reliable round-trip across adapters. Flags `broker_only`, `internal_only`,
  `status_mismatch` (we think PENDING, broker says FILLED, or the reverse),
  and `fill_mismatch` (filled quantity or avg fill price disagree beyond a
  ₹0.01 tolerance).
- **Deliberate design calls, not obvious in isolation:** a
  `broker.get_orders_today()` fetch failure forces the run to DISCREPANCY
  (same "uncertainty isn't safe" stance the existing position-fetch-failure
  path takes) -- but a broker with genuinely no `BrokerConnection` row
  (test doubles, a broker never formally registered) does NOT force
  non-CLEAN, it's a clean skip with a note. Getting this backwards either
  way would have broken real behaviour: forcing non-CLEAN on a missing
  connection would have made every existing CLEAN test (and any
  unregistered-but-harmless broker) permanently block trading; not forcing
  it on a genuine fetch failure would have silently hidden real broker
  API outages.
- **Scope note, stated in the module docstring:** still only order-level
  aggregate fill data (`filled_quantity`/`avg_fill_price`), not individual
  `FillRecord` rows -- partial fills aren't tracked as separate rows
  anywhere yet (`ExecutionRouter._persist_order` only writes a
  `FillRecord` once an order reaches FILLED), so there's nothing more
  granular to reconcile against without that being built first. Funds
  reconciliation (broker P&L vs. computed P&L) is still the one piece of
  M01 left undone, for the same broker-capability-gap reason as before.
- **Frontend:** the Reconciliation panel (Configuration → Risk) now shows
  order-mismatch counts alongside position mismatches per report.
- **Verify:** 11 new tests in `tests/unit/test_orders_reconciliation.py`
  covering clean-match, broker_only, internal_only, status_mismatch,
  fill_mismatch (both quantity and price, plus a within-tolerance case
  that must NOT flag), cross-broker-connection isolation, prior-day-order
  exclusion, fetch-failure forcing DISCREPANCY, and the missing-
  BrokerConnection skip NOT forcing DISCREPANCY. Caught and fixed a real
  bug while writing these: comparing `OrderRecord.avg_fill_price` (a
  `Decimal` at runtime despite the model's `float | None` type hint --
  SQLAlchemy's `Numeric` type doesn't coerce) directly against a broker
  `Decimal` raised `TypeError` on every single matching-order case,
  including the plain CLEAN one. Fixed by `float()`-ing both sides
  explicitly. 473/473 tests passing, no regressions. ruff/black/mypy all
  clean; frontend `tsc --noEmit` and `vite build` both clean. Same
  logged-in-UI caveat as the day before -- not visually verified.

**CP14 follow-up, 2026-08-29: funds reconciliation, M01's last open piece,
closed.** Same day as the auth fix and the two broker-capability items
above -- the "needs a 'today's realised P&L' broker capability the Broker
ABC doesn't expose" gap this scope note flagged twice now (2026-08-25 and
2026-08-29) is closed, not deferred a third time.
- **`Broker.get_realised_pnl_today()`** (optional, same NotImplementedError-
  by-default pattern as `place_protective_gtt`/`cancel_gtt`) +
  `BrokerCapabilities.supports_realised_pnl_query` in
  [xillion/core/broker_base.py](../../xillion/core/broker_base.py). This is
  deliberately its own method, not a reuse of `get_positions()`'s own
  `realised_pnl` field -- that list only covers currently-open positions,
  so a position fully closed out earlier today would already be missing
  from it, along with the P&L it booked.
- **Zerodha:** sums Kite's `"day"` positions array's `realised` field --
  verified against Kite's own docs (fetched directly, not assumed), which
  describe `"day"` specifically as "useful for computing intraday profits
  and losses for trading strategies", unlike `"net"` (mixes in
  carried-forward multi-day positions' historical realised total, not just
  today's).
- **Dhan:** sums `realizedProfit` across every row Dhan's positions
  endpoint returns, including closed-out ones (Dhan's docs show a
  `positionType: "CLOSED"` value -- there's no separate day/net split like
  Kite's, just one list). **Honest caveat, same spirit as the Forever-Order
  one:** Dhan's docs don't state outright whether `realizedProfit` resets
  daily (what this method promises) or is cumulative since the position was
  first opened -- material specifically for a MARGIN-carried multi-day
  option position, which is exactly what this codebase trades under since
  2026-08-29's product-type decision. Worth watching against a real account
  the first time M01's funds check runs on Dhan with a multi-day position
  open.
- **The check itself:**
  [xillion/engine/reconciliation.py](../../xillion/engine/reconciliation.py)'s
  new `_reconcile_funds()` compares the broker figure against
  `DailyStrategyPnl.realised_pnl` (xillion's own internally computed
  figure, from actual fill prices when a position closes --
  `strategy_engine.py`'s `persist_trade_close` -- genuinely independent of
  what the broker reports, not a comparison against itself), scoped to the
  specific broker connection via `StrategyInstance.broker_connection_id`,
  the same join every other check in this module already uses. A ₹1
  tolerance absorbs rounding noise. **Same two deliberate design calls as
  the orders check:** a broker without `supports_realised_pnl_query` is a
  clean skip (a capability that was never promised isn't evidence of
  anything wrong); a fetch failure forces DISCREPANCY (uncertainty isn't
  safe).
- **Migration 018** adds `reconciliation_report.funds_mismatch_json`
  (nullable -- null covers both "broker doesn't support this" and "nothing
  beyond tolerance to report", unlike `order_mismatches_json`'s
  default-`"[]"` list shape). Applied to the real Supabase DB, confirmed
  via `alembic current` → 018.
- **Frontend:** the Reconciliation panel now shows "funds off by ₹X" on a
  non-CLEAN report alongside the existing position/order mismatch counts.
- **Verify:** 7 new tests in `tests/unit/test_funds_reconciliation.py`
  (clean match, mismatch beyond tolerance, within-tolerance not flagged,
  broker-without-capability clean skip, fetch-failure forcing DISCREPANCY,
  missing-BrokerConnection clean skip, cross-broker-connection isolation)
  + 2 in `test_zerodha_protective_gtt.py` (day-array sum, empty-array
  zero) + 3 in `test_dhan_protective_gtt.py` (sum-across-all-positions
  including CLOSED, empty list, data-envelope unwrapping). 524/524 tests
  passing, no regressions. ruff/black/mypy all clean (mypy scoped to
  `xillion/` per the Makefile's own gate, same as every other checkpoint
  this session -- `brokers/` has pre-existing, unrelated mypy findings not
  touched here); frontend `tsc --noEmit` clean. Same logged-in-UI caveat as
  every other Configuration-panel change this session -- not visually
  verified.

---

### 🟡 CP15 — Dhan as a full trading broker, parallel with Zerodha `CODE DONE 2026-08-25 — blocked on credentials for live verification`
- [x] **`brokers/dhan.py`** — auth, positions/funds, order placement
      (place/modify/cancel/get/list), live ticks, historical data — matching
      the `brokers/zerodha.py` pattern (reconnect hardening, real
      socket-state tracking distinct from the REST session state) rather
      than adopting OpenAlgo (open question Q11 — a second hand-written
      adapter didn't make the case for a dependency yet). Built against
      **real, verified sources**, not assumed: fetched DhanHQ's own docs
      (dhanhq.co/docs/v2/orders/, /live-market-feed/, /market-quote/) and
      the official `dhanhq` PyPI SDK's source (github.com/dhan-oss/DhanHQ-py)
      directly during this session — order request/response shapes, the
      TRANSIT/PENDING/PART_TRADED/TRADED/REJECTED/CANCELLED/EXPIRED status
      enum, and the WebSocket feed's binary tick protocol are all confirmed
      against real docs and source, not guessed. The WebSocket feed's
      binary parsing is delegated to the SDK's own `MarketFeed` class
      rather than hand-rolled — a custom binary protocol (not JSON) is real
      complexity worth reusing a maintained implementation for, same
      reasoning `zerodha.py` already applied to `KiteTicker`.
      Extracted the scrip-master (symbol → securityId) resolution shared by
      this and `data_providers/dhanhq.py` into
      [xillion/core/dhan_instruments.py](../../xillion/core/dhan_instruments.py)
      rather than duplicating it a second time.
      **A real bug the real CSV caught, not assumed away:** `LOT_SIZE` in
      Dhan's actual scrip master is float-formatted (`"1.0"`, not `"1"`) —
      `int()` on that string raises `ValueError`. Fixed to `int(float(...))`.
      **Genuine unknown, inherited from the SDK itself, not hidden:** the
      SDK's own `DhanLogin.generate_token()` docstring admits it doesn't
      know the PIN+TOTP endpoint's exact success response shape ("usually
      it returns accessToken") — handled defensively (tries a few plausible
      keys, raises a clear error otherwise) rather than assumed correct.
- [x] **Multi-broker selection actually wired** — `xillion/api/instances.py`'s
      `_resolve_broker` was **hardcoded to "Zerodha Primary"** for every
      live/alert-mode instance regardless of what it was configured with;
      Dhan would have been unreachable from live trading even fully
      connected. Now resolves via the instance's own
      `broker_connection_id` → `BrokerConnection.name` →
      `app.state.broker_instances`, so an instance genuinely trades through
      whichever broker it's configured for.
      **A second real bug found while fixing the first:** `start_instance_core`
      unconditionally called `await broker.connect({})` even when
      `_resolve_broker` returned an ALREADY-connected broker — for
      `ZerodhaBroker`, whose `connect()` immediately does
      `credentials["api_key"]`, that empty-dict second call would raise
      `KeyError`. Never caught before because live mode has been blocked on
      real Kite Connect credentials (Blocked-on-you #1) for this project's
      entire history. `_resolve_broker` now returns `(broker,
      already_connected)` and the caller only connects when it's actually needed.
- [x] Wired into `xillion/main.py` — `_try_connect_dhan` (same DB-first/
      env-fallback credential loading as Zerodha's), called at startup
      alongside Zerodha, non-fatal if unconfigured or failing (Zerodha stays
      the primary broker either way). Daily token re-validation at 6:30 IST
      (15 min after Zerodha's, avoiding both brokers hitting their auth
      endpoints at the exact same moment) — doesn't force-delete the cached
      token first like Zerodha's does, since `DhanBroker.connect()` already
      validates the cached/provided token itself and only falls through to
      PIN+TOTP auto-refresh if it's genuinely invalid.
- [x] Failover semantics — **decided and built 2026-08-29, see "Broker
      failover (Zerodha ↔ Dhan)" below.** Answer: EXIT-ONLY, opt-in per
      connection (nothing fails over unless explicitly configured), never
      opens new positions on the secondary broker.

**Verify:** `test_dhan_instruments.py` (10 tests, real scrip-master CSV
columns) + `test_dhan_broker.py` (9 tests, real order request/response
shapes, every documented Dhan order status mapped) + `test_resolve_broker.py`
(5 tests, proves Dhan is genuinely selectable and the connect({}) bug is
fixed) all pass — but **the checkpoint's own literal Verify line ("a real
Dhan order placed and filled in paper mode, live ticks flowing, auth
refresh working on Dhan's own daily-token cadence") requires a real Dhan
account and is not yet done** — logged in
[docs/status/manual-tasks.md](../status/manual-tasks.md) as the actual
blocker, not silently skipped. 391/391 tests passing overall, no
regressions.

**Follow-up, 2026-08-25: paper mode is now genuinely free-to-verify on Dhan
alone, no Zerodha subscription required.** Prompted by the user asking
whether Kite Connect's ₹500/mo was actually necessary before seeing the app
work, or could be deferred. It could — but three separate bugs stood
between "Dhan is code-complete" and "paper mode actually shows a live price
sourced from Dhan":
1. `start_instance_core`'s live-tick subscription (a *second*, separate
   spot from `_resolve_broker`, which this checkpoint's own fix above
   didn't cover) was still hardcoded to the literal string `"Zerodha
   Primary"` — a Dhan-only instance got no ticks even with Dhan connected.
   Now resolves via `broker_connection_id` → `BrokerConnection.name`, same
   pattern as `_resolve_broker`.
2. **Dead code, real bug:** `PaperBroker.on_tick` was never actually
   subscribed to `MarketDataBus` — the wiring sketched in `_resolve_broker`
   was written but never connected (the comment there admitted as much:
   "not implemented in bus"). `PaperBroker._last_prices` — used for both
   fills and `get_quote` — silently never updated from live ticks in
   production, for *any* broker, Zerodha included, this whole time. Now
   `start_instance_core` subscribes a handler per instrument for paper-mode
   instances, tracked in `app.state.paper_tick_handlers` and unsubscribed
   in `stop_instance_core` (otherwise every restart leaks a handler holding
   a reference to the discarded `PaperBroker`).
3. `_try_connect_dhan` connected the broker but never started a
   `_tick_broadcaster` task for it the way `_try_connect_zerodha` does —
   `DhanBroker.tick_stream()` was never drained, so its ticks never reached
   `app.state.bus` regardless of (1) and (2). Now wired identically to
   Zerodha's (`_tick_broadcaster` is broker-agnostic, just needed the
   `supervise(...)` call).

New `test_paper_tick_wiring.py` (4 tests) proves paper mode subscribes
through whichever broker the instance is configured for (not hardcoded),
that `PaperBroker._last_prices` genuinely updates from a published bus
tick, and that stopping an instance unsubscribes its handler. 395/395
tests passing. **Net effect: a paper instance configured for "Dhan
Primary" now works end-to-end once a free Dhan account + token exists —
Kite Connect's ₹500/mo is no longer required to see the app trade for
real** (still needed eventually for the Zerodha-specific path, but not to
validate the system today).

**Follow-up, 2026-08-25: Dhan credentials moved off `.env`, onto the same
encrypted-DB path Zerodha already used.** The user asked directly: with
multiple broker providers, isn't `.env` the wrong place to store
credentials — shouldn't they live in the DB so they're easy to update or
add a new provider? Correct instinct, and the architecture already half
agreed — `xillion/auth/credstore.py`'s `BrokerCredential` table
(Fernet-encrypted payload) plus a full `GET`/`PUT`/`DELETE
/settings/zerodha` API and Settings UI form already existed, but were only
ever wired up for Zerodha; Dhan's loader (`_load_dhan_credentials`) checked
the DB first but nothing ever wrote to it, so it silently always fell back
to `.env`. Added the mirror: `GET`/`PUT`/`DELETE /settings/dhan`
(`xillion/api/settings.py`) and a matching Dhan card in
`frontend/src/pages/Settings.tsx` → Brokers tab. Credentials now go in
through the app itself, encrypted at rest, no `.env` editing, and this
pattern generalizes cleanly to any future broker (MT5 for Gold Lane B1,
etc.) — same shape, new router functions. New `test_dhan_settings.py` (2
tests) proves the round-trip and that saving/deleting one broker's
credentials never touches another's row. 397/397 tests passing.

**Broker failover (Zerodha ↔ Dhan), 2026-08-29.** Answers the "Failover
semantics" question left open above: **exit-only, opt-in per connection**
— matches automation-platform-spec 15-RUNBOOK-AND-OBSERVABILITY.md's own
runbook line verbatim ("If failover configured → switch to secondary
broker for exits only"), not a full active-active switch. Nothing fails
over unless a connection has an explicit failover target configured —
before this, a broker going down just sat there with no automated
response at all; there wasn't even periodic health polling.
- **Migration 017** adds `broker_connection.failover_connection_id`
  (self-referencing FK, nullable) — applied to the real Supabase DB,
  confirmed via `alembic current` → 017.
- **Health monitoring, new:**
  [xillion/engine/broker_health.py](../../xillion/engine/broker_health.py) —
  nothing polled `Broker.healthcheck()` on any schedule before this; it
  only ran on-demand from the Settings page. Now polls every connected
  broker every 30s, reacting to a state TRANSITION (healthy → 3
  consecutive failures, ~90s) rather than firing on one slow response.
  Wired as its own supervised background task in `xillion/main.py`, same
  pattern as X02/M01.
- **The exit-only action, new:**
  [xillion/engine/broker_failover.py](../../xillion/engine/broker_failover.py) —
  the down broker is unreachable by definition, so unlike X02 (which
  queries the broker directly), this trusts xillion's own `PositionRecord`
  (scoped to strategy instances configured on the down connection) for
  what's open, then places closing orders through the failover broker.
  Works because `OrderRequest.symbol` is already the canonical NSE
  tradingsymbol both `brokers/zerodha.py` (uses it directly) and
  `brokers/dhan.py` (resolves it to a `security_id` via its own scrip
  master) accept identically — confirmed by reading both adapters'
  `place_order`, not assumed. Doesn't hand-update `PositionRecord`
  afterward, matching X02's own precedent — M01 reconciles against
  whichever broker actually holds the position by its next run.
- **Trigger paths:** automatic (health monitor, 3 consecutive failures +
  a configured + healthy target) and manual (`POST
  /api/brokers/connections/{name}/failover`, the runbook's own documented
  operator action — "switch to secondary broker" isn't only meant to be
  automatic).
- **API:** extended `GET /brokers/connections` with failover config +
  health fields; new `PATCH .../failover-target` (set/clear, auth-gated)
  and `POST .../failover` (manual trigger, auth-gated) in
  `xillion/api/brokers.py`. **Found in passing 2026-08-29, fixed the same
  day:** the FOUR pre-existing routes in this same file (`GET
  /connections`, `POST .../reconnect`, `GET .../status`, `POST
  /refresh-instruments`) had NO auth check at all — confirmed live
  against the dev server (200, not 401, with no session cookie). All four
  now take `user: AppUser = Depends(get_current_user)`, matching every
  other authenticated route in this file and the app's own convention
  (per-route dependency, not a router-level one). No dedicated 401 test
  added — this codebase's existing convention is to exercise route
  functions directly rather than through an HTTP `TestClient` (see
  `test_signals_api.py`'s own docstring), so the auth wiring itself is
  trusted to FastAPI's dependency injection the same way the two routes
  built auth-gated from the start already were. 510/510 tests passing,
  no regressions. ruff/black/mypy all clean.
- **Frontend:** Configuration → Brokers → Active connections table now has
  a failover-target dropdown per connection, a "Failover now" button when
  one's configured, and a consecutive-failure count badge.
- **Verify:** 7 new tests in `test_broker_failover.py` (empty/clean cases,
  long vs. short position closing side, cross-connection isolation, a
  failed exit reported not raised, multiple positions across instances)
  + 6 in `test_broker_health.py` (healthy never accumulates, below-
  threshold doesn't trigger, threshold-with-no-target only alerts,
  threshold-with-healthy-target triggers exactly once — not once per
  tick, threshold-with-unhealthy-target doesn't trigger, recovery resets
  all flags). 486/486 tests passing, no regressions. ruff/black/mypy all
  clean; frontend `tsc --noEmit` and `vite build` both clean. Same
  logged-in-UI caveat as the reconciliation work — not visually verified.
  **Genuinely untested against real brokers**, same honesty as everything
  else built this way this session: the symbol-compatibility reasoning is
  sound from reading both adapters' code, but has never actually placed a
  real order through Dhan for a position opened via Zerodha.

**Product type made UI-configurable, 2026-08-29.** Rakesh's own request,
prompted by seeing the "decide Zerodha's product type" item in
manual-tasks.md: rather than a one-time hardcoded decision the way Dhan's
was made earlier the same day, make BOTH brokers' product type a setting
he can change himself from the app, any time, no code change or redeploy.
- **`brokers/zerodha.py`/`brokers/dhan.py`:** both had a single hardcoded
  product type (`self._kite.PRODUCT_MIS`, `_PRODUCT_TYPE = "MARGIN"`) used
  at every `place_order()`/`place_protective_gtt()` call site. New
  `_product_type()` instance method on each reads `self._credentials.get(
  "product_type")` (already the per-connection dict every other credential
  field lives in -- `connect()` stores whatever `xillion.auth.credstore`
  hands it), falling back to the original hardcoded default (MIS / MARGIN)
  if unset or set to something invalid -- an existing connection that
  never opens the new dropdown keeps behaving exactly as before, verified
  by the pre-existing tests passing unchanged.
- **No new DB table or migration needed** -- `BrokerCredential`'s
  encrypted payload is already a generic JSON blob per connection
  (`xillion/auth/credstore.py`), so `product_type` is just one more key in
  the same dict `api_key`/`client_id`/etc. already live in.
  `xillion/api/settings.py`'s `ZerodhaCredentialsRequest`/
  `DhanCredentialsRequest` gained a `Literal["MIS","NRML"]` /
  `Literal["INTRADAY","MARGIN"]` field (defaults MIS/MARGIN); the GET
  status endpoints now echo the saved value back so the frontend dropdown
  reflects what's actually configured, not just what the form happens to
  hold.
- **Frontend:** Configuration -> Brokers -> Zerodha/Dhan cards each get a
  "Product type" `<select>` alongside the existing credential fields,
  prefilled from the GET status response on load and after every save.
- **Verify:** 7 new broker-level unit tests (`_product_type()` default/
  configured/invalid-falls-back-to-default for both brokers, plus a
  request-shape test proving the configured value actually reaches the
  GTT/place_order call) + a new `test_zerodha_settings.py` (Zerodha had no
  Settings-API test file at all before this) and an addition to
  `test_dhan_settings.py`, both proving the field round-trips through the
  real encrypted-DB storage path, not just the Pydantic model. 552/552
  tests passing, no regressions. ruff/black/mypy all clean; frontend `tsc
  --noEmit` and `vite build` both clean. Same logged-in-UI caveat as every
  other Configuration-panel change this session -- the dropdowns
  themselves weren't visually confirmed against a live login.

---

## TRACK B — Asset pipelines

Each asset runs the same 6 stages — see
[14-asset-pipeline.md](../process/asset-pipeline.md). Mark stages as they complete.

| Asset | S1 Build | S2 Backtest | S3 Paper | S4 Live | S5 Auto | S6 Docs |
|---|---|---|---|---|---|---|
| **Options — credit spread** (Nifty/Sensex weekly) · Zerodha+Dhan | ✅ `strategies/credit_spread_weekly.py` | ✅ real backtest (open+close, real trade) | ⬜ | ⬜ blocked on real-broker bracket/GTT (CP11 gap) | ⬜ | 🟡 Stage 1 documented |
| **Gold — Lane B1** (XAUUSD, Sweep-Reversal) · alert engine live 2026-09-22, decoupled from Funding Pips MT5 | ✅ `strategies/gold_sweep_reversal.py`, alert+paper+backtest modes, tested | 🔴 **Run for real 2026-09-22 — net loss.** 201 trades/6mo, 47.8% win rate, -$12,705.76. Two parameter sweeps (57 combos total) also net-negative — see strategy doc §3. **Strategy-viability decision pending**, not an engineering gap | ✅ alert pipeline live and verified (real `daily levels marked`, real ticks) — **paper trading (real simulated fills) not started**, blocked on the viability decision above | ⬜ N/A — alert-only, no execution planned yet | ⬜ | ✅ `docs/strategies/gold-xauusd-sweep-reversal.md`, fully current |
| **Gold — Lane B2** (MCX futures/options) · Zerodha/Dhan | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Stock options** · Zerodha | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Stocks** · Zerodha | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Crypto** · TBD exchange | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

**2026-08-25: Options S1 + S2 built.** `strategies/credit_spread_weekly.py`
implements the Nifty/Sensex weekly Bull Put / Bear Call credit spread from
`docs/strategies/knowledge-base/10-FIRST-STRATEGY-SPEC.md` — entry timing,
trend-aligned direction, strike-count strike selection (a coarser proxy for
the KB's delta arms — no greeks engine exists), credit-adequacy filter,
KB §7 position sizing, multi-leg entry/exit via CP11, and software
protective-order monitoring. Full rules + honest gaps written up in
`docs/strategies/credit-spread-weekly.md`. S2 (Backtest) is now real, not
just wired: `xillion/data/option_chain.py` + `_BacktestContext` resolve
actual historical strikes from NSE Bhavcopy, and the strategy has run a
genuine open→close cycle through `BacktestEngine` with a real recorded
trade (see CP11 section above for the full writeup, including two real
bugs this surfaced and fixed). **What Stage 2 still can't do:** run the
real, multi-year, pass/fail-criteria backtest KB `10-FIRST-STRATEGY-SPEC.md`
§10 calls for — that needs the actual 2-5yr NSE backfill (Blocked-on-you
#6) and is NSE-listed underlyings only (NIFTY/BANKNIFTY; Sensex is
BSE-listed, out of reach of this provider). S4 (Live) is blocked on the
CP11 bracket/GTT gap (software stops now survive a restart via CP12, but
that's not the same as a fully independent crash-watchdog — see CP12).

**2026-09-21, continued: taken/skipped + outcome tracking (G5) and weekly
win-rate reporting (G6) built.** Migration 020 adds `user_action` (TAKEN|
SKIPPED), `user_action_at/_source`, `outcome` (WIN|LOSS|BREAKEVEN),
`outcome_notes`, `outcome_recorded_at` to `signal_log` -- generic to any
alert-mode ENTER signal, not Gold-specific. New `PUT /journal/signal-action`
and `PUT /journal/signal-outcome` endpoints. `xillion/engine/journal.py`'s
`build_journal` now prefers this self-reported outcome over its existing
price-derived `classify_signal_outcome` when present -- necessary because
Gold Sweep-Reversal never emits a real EXIT signal to classify from (alert-
only, one-shot ENTER, no on_tick exit monitoring), so without this every
one of its calls would show `still_open` forever. **Frontend: the Alerts
page** (`frontend/src/pages/Alerts.tsx`) **now has "I took this"/"Skipped"
buttons and a Win/Loss/Breakeven picker per ENTER signal, plus an
expandable row showing the full reasoning text** (`SignalLog.message`,
which already carries G2's `reason`) -- this is the "mark it on the
webpage" half of what was asked; Telegram inline buttons stay a fast-follow
(logged in manual-tasks.md as a design note, not blocking). Also fixed a
real pre-existing display bug while touching this page: Alerts always
rendered every price with a hardcoded ₹ symbol, which would have shown
Gold's dollar prices as rupees the moment a Gold signal ever appeared --
now currency-aware by symbol.

**Weekly review (G6): extended the existing CP10 weekly Telegram digest**
(Sundays 6pm IST, already-running `run_weekly_digest`) rather than building
a new scheduler -- `DigestReport`/`build_digest`
(`xillion/engine/digest.py`) now also aggregates the period's alert ENTER
signals: taken/skipped/unmarked counts and a win-rate line
(`WW/LL/BEBE (NN% win rate of resolved calls)`) computed from the same
self-reported `outcome` field. This directly answers "every week I'll check
what was taken and what the win % is" via the push that already exists,
rather than a new pull-only report -- the existing Journal/Alerts pages
still work for an on-demand look too.

New tests: 5 in `test_gold_sweep_reversal.py` (G2, listed below), 3 in
`test_journal.py` (self-reported outcome takes priority over price-derived;
both new endpoints update the row; invalid action is rejected with 400), 1
in `test_digest.py` (alert-signal stats + the exact rendered digest text).
Migration 020's raw `ALTER TABLE ... ADD COLUMN` statements verified
directly against SQLite (plain nullable columns, no constraints -- doesn't
hit the batch-mode limitation an earlier, unrelated migration has on
SQLite; this repo's migrations are Postgres-primary per CLAUDE.md anyway).
Frontend `tsc --noEmit` and `npm run build` (CI's actual frontend check)
both clean. 584/584 backend tests passing, ruff/black/mypy clean.

**2026-09-21, continued: Sweep-Reversal strategy logic built (G2) --
`strategies/gold_sweep_reversal.py`.** The exact card, mechanically: 4
daily levels (Asian session H/L from live M5 bars, previous trading day
H/L walking back over closed weekends), sweep-then-M5-reclaim trigger,
fixed sizing (min-3pt/0.5pt-buffer SL, 7.5pt TP), 2 trades/day cap, a
10-min cooldown after any entry (the card's own FundingPips-rule mapping),
trading-window gate. Runs alert-only via `ctx.alert_entry` -- **new
`reason` field added to `OrderRequest`/`alert_entry`/`alert_exit`**
(`xillion/core/events.py`, `strategy_base.py`,
`strategy_engine.py:_handle_alert_signal`) so the Telegram alert and
`SignalLog.message` carry a real "why this entry" explanation (which line
swept, at what price, R:R, trade N/max today, the card's own discipline
reminders), not just the existing generic side/price/target/stop template
-- optional, so credit-spread-weekly needs no change. 5 new tests
(`test_gold_sweep_reversal.py`) against a hand-built fake context, verified
by hand: exact SHORT/LONG math, session-window gate, daily cap, cooldown.
**Two real bugs found by writing these tests, not assumed correct:** (1)
`ctx.log(..., level=level_name, ...)` collided with `log()`'s own `level`
severity parameter -- `TypeError` on every fired signal, would have crash-
looped the instance in production; (2) gating the sweep/reclaim tracking
itself on the cooldown (not just the firing) silently dropped a sweep that
started during the cooldown window, so the bar right at the cooldown
boundary looked like a fresh one-bar sweep+reclaim instead of continuing
one already in progress -- restructured so cooldown/daily-cap/news-veto
only suppress firing, never the underlying level tracking. Plugin
discovery clean, `mypy xillion` (CI scope)/`ruff`/`black` (repo-wide, both
CI scope) all clean, 580/580 tests passing. **Not yet run against live
data** -- still needs the Twelve Data key (G1) to actually see a bar.

**2026-09-21, continued: Sweep-Reversal alert engine's data feed built
(G1).** `brokers/twelve_data_feed.py` — a data-only "broker" plugin
(Twelve Data's free tier, `TWELVE_DATA_API_KEY`) that supplies live XAUUSD
M5 candles without any Wine/MT5 dependency: polls `/time_series` every 30s,
and when a new 5-min bar closes, replays it as 4 time-ordered synthetic
ticks through the existing `tick_stream()` -> `MarketDataBus` ->
`BarAggregator` path so the resulting Bar matches Twelve Data's own OHLC
exactly (not a polling approximation). Every order-placement method raises
`NotImplementedError` — structurally no execution, same guarantee as the
MCP server's missing order-placement tool. Wired into startup via
`_try_connect_twelve_data` in `xillion/main.py` (mirrors
`_try_connect_dhan`/`_try_connect_mt5`, gated on the key being set, non-
fatal if missing). **Real gap found and fixed along the way:**
`api/instances.py`'s `_ensure_broker_connection` only ever knew about
"Zerodha Primary"/"Dhan Primary" as broker-connection names — any other
connected broker (MT5 Funding Pips, and now this) had no way to become an
instance's `broker_connection_id` at all. Added an explicit
`broker_connection_name` field to `CreateInstanceRequest`, tried first
before the old priority fallback. Plugin discovery confirmed clean (zero
errors, broker shows up in the registry); `mypy xillion` (CI's actual
scope), `ruff`, `black` all clean; full test suite (575) still green — but
**this whole broker is unverified against the real Twelve Data API**, no
key exists in this sandbox yet (see manual-tasks.md item just added).
`get_history()`/`get_quote()` also implemented for symmetry (Stage 2
backtest could use this same feed later, though Twelve Data's free-tier
history depth for M5 is unconfirmed — another honest unknown, not assumed).

**2026-09-21: Gold Lane B1's first named strategy, Sweep-Reversal, Stage 1
rules encoded.** User-provided session-sweep-fade card (4 daily levels —
Asian high/low + prior-day high/low, M5 close-back-inside trigger, fixed
0.08 lot / 3.0pt min SL / 7.5pt TP, 2 trades/day max, London window
12:30–18:30 IST only) written up in full, including the FundingPips 1 Step
Flex $5K prop-rule mapping and the user's manual 4-day TradingView-replay
validation protocol, in
[docs/strategies/gold-xauusd-sweep-reversal.md](../strategies/gold-xauusd-sweep-reversal.md).
The user's own reference Python backtester (MT5-only, Windows/Wine) is
checked in verbatim at
[scripts/gold_sweep_backtest.py](../../scripts/gold_sweep_backtest.py) so it
doesn't need re-pasting into a future session — **not yet run against real
data**, no strategy code written yet. **What's next (Stage 2):** either the
user runs the reference script against real MT5 history, or completes the
manual 100+-trade TradingView replay test — a keep/kill decision on win rate
comes out of that before any strategy code gets written. **Separately, a
live *alert-only* engine for this strategy (Telegram signal notifications
with reasoning, no order placement) is being scoped as its own work item —
deliberately decoupled from the Funding Pips MT5 broker/bridge (see the doc's
§7 note), since alert mode doesn't need Wine or a running MT5 terminal, only
a price feed. Not started yet; see "Blocked on you" below for the manual
setup this still needs.**

### Per-asset enablement work
Infrastructure each asset needs before its pipeline can start:

- **Options** — 🟡 Stage 1+2 done (engine-level). **Blocked on:** the real
  multi-year backfill for a genuine pass/fail backtest run (#6 below),
  real-broker bracket/GTT for Stage 4. Stage 3 (paper) is unblocked today —
  CP11's leg-failure protocol and software protective orders are both real,
  tested, and now restart-safe (CP12), just not yet run against live market
  data for the required 2+ weeks
- **Gold Lane B1 (XAUUSD/Funding Pips)** — 🟡 **2026-08-28: MT5 broker
  plugin + bridge built, structurally correct but unverified end-to-end**
  (same position CP15/Dhan started from before real credentials existed).
  `brokers/mt5_funding_pips.py` (migration 014: `mt5_pending_order` /
  `mt5_bridge_tick` / `mt5_bridge_state`) + `xillion/api/mt5_bridge.py` +
  `mt5_bridge/bridge.py`. Architecturally different from Zerodha/Dhan on
  purpose: the official `MetaTrader5` Python package only talks to a real
  MT5 terminal on the SAME machine, which Render (this backend's host) can
  never be — so this broker queues orders/reads prices via DB tables a
  separate local process (the bridge, run on Rakesh's own Mac under Wine
  per his no-VPS-cost choice) polls against, rather than calling a broker
  API directly like every other plugin here does. `OrderRequest.quantity`
  (int, project-wide) is repurposed as MICRO-LOTS (hundredths of a lot) for
  this broker only, documented in the file rather than changing the shared
  type. 12 new unit tests (`test_mt5_broker.py`) cover the queue/poll/
  report mechanics with a real in-memory DB, no real MT5 needed for that
  part. **Still needed, and genuinely open:** 24×5 session calendar,
  currency field, real FX lot-size math beyond the micro-lot convention,
  **Funding Pips drawdown rules as hard risk limits** (breaching one
  instantly fails the account — see `architecture/risk-and-compliance.md`
  Part C.3), and the actual Wine/Mac bridge setup + a real MT5
  account to verify any of this against — none of that exists in this
  sandbox. `mt5_bridge/README.md` has the setup steps but they're
  unverified against a real Mac+Wine environment. **Historical Gold data
  source (Stage 2) built 2026-08-29 — see "Gold Lane B1 backtest data
  source" below.**

**Gold Lane B1 backtest data source, 2026-08-29.** Rakesh's decision
(asked directly, since this genuinely needed a design pick, not something
to guess at): both candidate approaches from `deferred-backlog.md`
together, (a) extending the bridge and (b) a free external backup — plus a
request for a persistent "local agent" connection (his own framing,
comparing it to Azure/Testsigma local agents) so backtests work even away
from the Mac.
- **(a) MT5 bridge extended for on-demand history.** New
  `mt5_historical_request` table (migration 019) reuses the exact same
  "queue a row in the DB, the local bridge polls and fulfils it" shape
  `mt5_pending_order` already uses for live orders — the MT5 terminal's
  history, like its order execution, only exists on the machine actually
  running it.
  [xillion/api/mt5_bridge.py](../../xillion/api/mt5_bridge.py)'s `poll()`
  now also returns pending historical requests (left PENDING rather than
  flipped to an intermediate state the way orders are, since a history
  fetch is idempotent — a bridge restart mid-fetch just re-fetches on its
  next cycle instead of the request getting stuck); new
  `POST /historical-report` receives the fetched bars.
  [mt5_bridge/bridge.py](../../mt5_bridge/bridge.py) calls MT5's own
  `copy_rates_range()` each poll cycle for any pending request.
  New [data_providers/mt5_bridge_history.py](../../data_providers/mt5_bridge_history.py)
  (`MT5BridgeHistoryProvider`) is the actual `HistoricalDataProvider` a
  backfill request goes through — it enqueues the request and polls (2s
  interval, 60s timeout) for the bridge to fulfil it, so this plugs into
  the EXACT SAME `BarWarehouse`/Coverage-and-backfill machinery every
  other provider already uses, no new UI needed (confirmed: the existing
  Data Providers panel is driven entirely by the plugin registry). If the
  bridge is offline, this fails with a clear "did not respond, is your
  bridge running?" error rather than hanging.
- **"Local agent" framing — didn't need a new mechanism.** The bridge
  already polls OUT to the backend on its own schedule (never the reverse
  — that's specifically why it works through NAT/a home firewall with zero
  inbound port-forwarding on Rakesh's Mac). Extending that one existing
  channel to also carry historical requests, rather than inventing a
  second connection type, is what makes this already work "even when
  away" — the backtest just has to wait for the Mac to be reachable and
  the bridge running, same as live trading already does.
- **(b) Alpha Vantage FX, a free backup.** New
  [data_providers/alpha_vantage_fx.py](../../data_providers/alpha_vantage_fx.py)
  (`AlphaVantageFXProvider`) — daily XAUUSD bars via Alpha Vantage's
  FX_DAILY endpoint, needs only a free API key (no card). Verified live
  against Alpha Vantage's real API that `FX_DAILY?from_symbol=XAU&
  to_symbol=USD` is accepted (not an invalid-parameter error, just gated
  on a real key) and that the numbered-field response convention
  ("1. open" etc) is real (confirmed via `TIME_SERIES_DAILY`'s own demo
  endpoint, which does return real data). **Honest, stated gap:** the
  exact FX-specific top-level JSON key and whether a volume field exists
  at all weren't independently confirmed against a live authenticated FX
  response (the demo key doesn't cover FX) — parsed defensively (tries the
  documented key, falls back to the equity-style key name, treats missing
  volume as 0) rather than assumed correct, and raises a clear error if
  neither key is present instead of silently returning nothing.
- **Real bug found and fixed along the way, not specific to Gold:** adding
  this as a SECOND `requires_broker` data provider (alongside the existing
  Kite one) surfaced that `xillion/api/data.py`'s `start_backfill()` broker
  selection just took whichever connected broker happened to be first in
  dict iteration order — correct only by coincidence while Kite/Zerodha
  was the only such pairing that existed. New
  `DataProviderCapabilities.required_broker_name` pins each provider to
  the specific broker CLASS it actually needs (`MT5BridgeHistoryProvider`
  -> `"MT5 Funding Pips"`, `KiteHistoricalProvider` -> `"Zerodha"`); a
  session with both Zerodha and MT5 connected at once would otherwise have
  silently handed Kite's `fetch_bars()` the MT5 broker instance.
- **Verify:** 7 new tests in `test_mt5_historical.py` (poll returns/
  excludes/isolates pending requests correctly, leaves them PENDING not
  ACKED, historical-report marks DONE/FAILED, unknown request id doesn't
  crash) + 5 in `test_mt5_bridge_history_provider.py` (no-broker error,
  enqueue-then-fulfil round trip via a simulated concurrent "bridge",
  FAILED propagates the bridge's own error message, a genuine timeout when
  nothing responds) + 8 in `test_alpha_vantage_fx.py` (documented key
  parses, defensive fallback key parses, date-range filtering, symbol
  splitting, rate-limit `Note` raises clearly, intraday timeframe
  rejected, missing key/short symbol rejected) + 3 in
  `test_backfill_broker_selection.py` (a pinned provider gets its own
  broker even when a different one is first in dict order, an unpinned
  provider keeps the old loose behaviour, a clear 422 when only the wrong
  broker is connected). 575/575 tests passing, no regressions.
  ruff/black/mypy all clean; plugin discovery confirmed clean locally —
  both "MT5 Bridge (Gold)" and "Alpha Vantage FX" load with zero errors.
  Migration 019 applied to the real Supabase DB, confirmed via
  `alembic current` -> 019. **Not yet run against real data** — no real
  Mac+Wine bridge or Alpha Vantage key exists in this sandbox to actually
  fetch a real Gold bar with; the plumbing is proven correct against a
  simulated bridge/stubbed HTTP response, not a live run.

- **Gold Lane B2 (MCX)** — ⬜ needs: MCX instrument/expiry resolution
  (monthly, 5th), reuses the Lane A broker adapter (Dhan/Zerodha both
  support MCX) — cheaper to build than B1 since no new broker is needed,
  only a new instrument type
- **Stock options** — ⬜ needs: stock-option chain resolution (reuses index logic)
- **Stocks** — ⬜ needs: equity instrument type (cheapest — multiplier is 1)
- **Crypto** — ⬜ needs: exchange integration, **1% TDS in the fee engine**
  (this alone makes most active crypto strategies unprofitable — model it
  before trading, not after)

---

## Blocked on you

> **Full actionable checklist, kept live across sessions:**
> [`docs/status/manual-tasks.md`](manual-tasks.md) — this table is the
> per-checkpoint summary; that file is what Rakesh actually works through
> and checks off. Keep both in sync (see `.claude/skills/xillion-manual-tasks/`).

| # | Item | Blocks | Status |
|---|---|---|---|
| 1 | Kite Connect plan (~1 hr) | CP4 onward (Zerodha-specific path only) | Open — **low priority, deferred by Rakesh 2026-08-25**, do #10 first |
| ~~2~~ | ~~Real strategy rules from trading-course videos~~ | ~~Options S1~~ | ✅ **Resolved 2026-08-25** — `docs/strategies/knowledge-base/` |
| ~~3~~ | ~~CA opinion on Funding Pips prop-firm income~~ | ~~Gold Lane B1 S4~~ | ✅ **Resolved 2026-08-25** — decided not needed, will declare as foreign income on ITR directly |
| ~~4~~ | ~~Funding Pips account + challenge~~ | ~~Gold Lane B1 S3 onward~~ | ✅ **Resolved 2026-08-25** — already had this |
| ~~5~~ | ~~Confirm ₹50k starting capital, ₹1,000/mo first milestone~~ | ~~Options S4~~ | ✅ **Resolved 2026-08-25** — confirmed yes |
| ~~6~~ | ~~Run `python scripts/backfill.py` for real (2-5yr)~~ | ~~CP3 close-out, Options S2~~ | ✅ **Done 2026-08-26** — 2021-2026 NIFTY+BANKNIFTY, one continuous `bar_coverage` span, confirmed via direct DB query |
| ~~7~~ | ~~A real multi-leg options strategy to design multi-leg support against~~ | ~~CP5 close-out, Options S1~~ | ✅ **Resolved 2026-08-25, all three since built** — credit spread (2-leg, CP11), iron condor (4-leg) and butterfly (1:2:1 debit), both 2026-08-29 |
| ~~8~~ | ~~Confirm free-tier Redis provider choice~~ | ~~CP13 (only if in-memory state turns out insufficient)~~ | ✅ **Resolved 2026-08-25** — decided: Upstash. Not wired in yet, only needed if CP13's in-memory state turns out insufficient |
| 9 | A free-tier cloud LLM key (Gemini/Groq) in `prosper-engine/.env` — not blocking (Ollama's real tool-calling covered full verification), just faster/hosted than local Ollama when you want it | CP8 close-out | Open, not blocking — **explicitly deferred by Rakesh 2026-08-25** |
| ~~10~~ | ~~**Dhan API access token + client ID**~~ | ~~CP15 live verification~~ | ✅ **Resolved 2026-08-26** — connected live on Render; see the crash-loop bug found+fixed same day, above |
| ~~11~~ | ~~Telegram bot~~ | ~~Alerts, kill-switch notifications~~ | ✅ **Resolved 2026-08-26** — connected live on Render, "Send test message" verified working |
| ~~12~~ | ~~Twelve Data free API key (live XAUUSD M5 candles)~~ | ~~Gold Sweep-Reversal alert engine running against real data~~ | ✅ **Resolved 2026-09-21** — in `.env`, verified live (real quote + real M5 bar poll) |
| ~~13~~ | ~~Finnhub free API key (news/econ-calendar ritual check)~~ | ~~Gold Sweep-Reversal news-check ritual only~~ | ✅ **Resolved 2026-09-21** — in `.env`, verified live. Wiring it into `_news_veto_active()` (still a stub) is separate follow-up work, not blocked on Rakesh |
| ~~14~~ | ~~Confirm before running: apply migration 020 to the real Supabase DB~~ | ~~Taken/skipped/outcome columns existing on the real DB~~ | ✅ **Resolved 2026-09-21** — applied, verified via `information_schema` |
| ~~15~~ | ~~Supabase project paused/gone — hostname returned NXDOMAIN~~ | ~~Everything~~ | ✅ **Resolved 2026-09-21** — Rakesh resumed it from the dashboard |
| 16 | 🔴 Decide how to proceed on Gold Sweep-Reversal after two failed parameter sweeps (net loss on real 6mo backtest, SL cap/floor sweeps both net-negative) | Further parameter work, real paper trading | Open — see `manual-tasks.md`, not urgent |
| ~~17~~ | ~~Upload `.env` + `data/.encryption_key` + XAUUSD backfill + warehouse DB backups to Drive~~ | ~~Continuing this project from a new laptop without a ~23-hour redo or lost broker/API access~~ | ✅ **Resolved 2026-09-23** — all four confirmed uploaded |

---

## Explicitly deferred / out of scope

**See [16-deferred-backlog.md](deferred-backlog.md)** — every consciously-
deferred item with its reason and the trigger that would justify revisiting.
Check it before treating anything as a missing feature.

---

## Update protocol

**Whenever a checkpoint or pipeline stage completes:**

1. Tick the boxes and change ⬜ → ✅ (or 🟡 for in-progress)
2. Update **Last updated** and **Current position** at the top
3. Add a one-line note on anything surprising found along the way — the
   surprises are what a cold session most needs to know
4. If the work produced a strategy insight, also write it to
   `docs/strategies/<name>.md` (RAG ingests these)

**Status legend:** ✅ done · 🟡 in progress · ⬜ not started · 🔴 blocked

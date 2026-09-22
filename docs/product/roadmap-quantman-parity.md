# 13 — QuantMan-Parity Roadmap (started Aug 2026)

> **Start here for the "big picture" plan.** This is the living tracker for the
> end-to-end automation goal — from registering a strategy/setup, through
> backtesting, paper soak, manual-execution alerts, full automation, and
> finally AI-assisted verification via `prosper-engine`. Update the checkboxes
> as you go; this file (plus [09-progress-tracker.md](../archive/progress-tracker-phases-0-10.md)
> for underlying technical debt) is the source of truth across sessions.
>
> **2026-09-22 — checkboxes synced to reality, and priority set: Track B is
> now the main roadmap.** Rakesh's call this session — day-to-day priority
> lives in `docs/status/task-tracker.md`'s Track A/B framework (CP-numbered
> platform checkpoints + per-asset-class pipeline stages), with the near-term
> goal of getting Track B (Gold Lane B1, and whatever asset lanes follow)
> fully usable end-to-end from the UI/Telegram, not just runnable by a
> developer who knows the code. This QP-numbered doc still holds going
> forward — everything below maps cleanly onto that CP/Track work (see the
> notes on each QP section) — but `task-tracker.md` is the one to read for
> "what's actually next."

## Vision

Inspired by [quantman.trade](https://www.quantman.trade) — but personal,
self-hosted, and asset-class-agnostic from day one (options first, but the
"setup" model must extend cleanly to forex, stocks, and swing trading later
without a rewrite).

End state: register a setup once → it gets backtested → soaked in paper mode
→ sends you manual buy/sell alerts with target & stop-loss → once trusted,
flip it to full automation → an LLM reviews every signal before it fires and
attaches a confidence score → only then does real capital scale up.

**Decision log (locked in 2026-08-02, don't re-litigate without new info):**
- Strategy/setup definition is **hybrid**: simple condition-builder UI for
  common cases, code-based `Strategy` plugins (existing architecture, see
  [04-plugin-contracts.md](../architecture/plugin-contracts.md)) for complex multi-leg
  option structures. The UI/data model must not be options-only — instrument
  type (index/option/future/equity/forex-later) is a first-class field.
- No UI sections get hidden. Full nav stays visible; each phase below just
  focuses on *perfecting* the flows it owns rather than hiding the rest.
- Bugs are found and fixed proactively (self-audit), not pre-listed by the
  user.
- Kite Connect's ₹500/mo Historical Data API is the default data source for
  now (see [Data providers](#data-providers-free--affordable--professional)
  below) — sufficient for spot/futures-based setups and short-lookback
  options price backtesting. Revisit only once a specific strategy (from the
  user's trading course) actually needs multi-year OI/IV history.

---

## QP-0 — Bug audit & stabilization (done 2026-08-03)

Goal: the existing core flows (strategy list, instance create/start/stop,
backtest run, alert mode) work cleanly before piling new features on top.

- [x] Self-audit: drove the running app (browser + API) through every core
      flow — Dashboard, Strategies (Instances/Classes/Archived, create/start/
      stop in both Paper and Alert mode), Trades, Backtest (real CSV upload +
      run), Logs, all 5 Settings tabs, Brokers
- [x] Fixed **strategy_class/broker_class DB persistence never implemented**
      — plugin discovery only built an in-memory registry; nothing wrote rows
      to Postgres, so creating any instance on a fresh DB failed with "has no
      DB record — reload plugins first," even after clicking reload. Added
      `xillion/db/plugin_sync.py`, wired into both app startup (`main.py`)
      and the `/strategies/reload` endpoint.
- [x] Fixed **silent zero-trade backtest bug** — `example_sma_cross.py`
      called `ctx.history(symbol, self.timeframe, ...)` using the strategy's
      hardcoded class attribute instead of `bar.timeframe`; combined with the
      Backtest page's Timeframe dropdown defaulting to a static `'5m'`
      regardless of the selected strategy, this meant backtests silently
      produced 0 trades / 0% return with no error unless you manually set the
      dropdown to match the strategy's own declared timeframe. Fixed the
      strategy to use `bar.timeframe`, and `Backtest.tsx` to auto-sync the
      dropdown to the selected strategy's default. Verified end-to-end: a
      real CSV backtest now correctly produces 1 trade / +₹199.19 / 100% win
      rate, matching an independent Python-side calculation.
- [x] No user-supplied bug list — found-and-fixed only, per your preference
- Known, already-tracked (not new): Logs page has no DB persistence
  (stream-only), no Positions endpoint yet — both in 09-progress-tracker.md
  Phase 11 P2.

---

## QP-1 — Strategies registrable, reading data as expected (done 2026-08-03)

Goal: define a setup via the hybrid UI/code model; confirm it correctly reads
live + historical market data for its configured instrument(s).

- [x] Audited the `params_schema`-driven instance form — it already fully
      covers the "simple UI-form for common cases" half of the hybrid model
      (auto-renders int/float/str/bool/choice fields with min/max/choices,
      verified live). No new UI framework needed.
- [x] Confirmed the architecture is **already explicitly asset-class-agnostic**
      — `strategy_base.py` documents that only 4 methods (`get_spot`,
      `resolve_strike`, `get_option_price`, `subscribe_instrument`) are
      options-specific; everything else (`buy`/`sell`, `history`,
      `params_schema`, `instruments`) is fully generic. A forex/equity/swing
      strategy needs zero framework changes — this resolves the
      "instrument-type field" concern from the original plan; it's not
      needed as a separate field since the generic surface already doesn't
      assume options.
- [x] Confirmed `SMA Cross` and `Nifty Spot Alert` are **already fully
      generic, no-code setups** — their `instruments` list is set per-instance
      via the New Instance form (not hardcoded in the class), verified by
      creating an "SMA Cross" instance on NIFTY through the UI alone.
- [x] Built the one genuinely missing common condition: added
      `strategies/rsi_threshold_alert.py` (RSI-threshold cross, same
      mode-agnostic/no-broker-imports pattern as the other two). Verified via
      direct backtest (correct BUY signal at RSI 80.69 crossing threshold 70)
      and live in the UI (auto-discovered, DB-synced, params form renders
      correctly, no console errors).
- Deferred: a true drag-and-drop multi-condition builder — held off building
  further per your call, until real strategies from your trading-course videos
  are available to inform what "common setups" actually need. The 3 generic
  strategies (SMA cross, price-level cross, RSI threshold) are the starter
  set; extend this list opportunistically as real needs surface, rather than
  guessing at a fuller condition library now.

**Exit:** met — created setups via UI alone (no new `Strategy` subclass) for
2 of 3 generic strategies; confirmed correct evaluation against real
historical data end-to-end.

---

## QP-2 — Backtest with historical data

Goal: backtest engine (already built — see Phase 2, 09-progress-tracker.md)
produces accurate results for the user's real strategies once shared.

- [x] Built a **pluggable historical-data-provider system** (2026-08-03),
      same drop-a-file plugin pattern as strategies/brokers — see
      `xillion/core/data_provider_base.py`. Explicitly designed for the
      free/affordable/professional tiers in the table below, and for future
      forex sourcing (e.g. TradingView), per the user's ask to not be
      Kite-only. New tables: `data_provider_class`, `data_provider_credential`
      (migration `004_data_providers.py`). New DB-sync
      hook in `plugin_sync.py`. New API: `GET/PUT/DELETE
      /api/data-providers/...` and `POST /api/backtest/run-provider`. New
      Settings → "Data Providers" tab; Backtest page has a Source toggle
      (Upload CSV | Fetch from provider).
  - [x] `data_providers/nse_bhavcopy.py` — **free**, no API key, official
        NSE F&O end-of-day archive. Verified against a real live file
        (`BhavCopy_NSE_FO_..._20260731...csv.zip`); values matched exactly.
        Daily bars only, options/futures only (no equity spot).
  - [x] `data_providers/zerodha_kite.py` — reuses whichever Zerodha broker
        connection is already live (Settings → Brokers) instead of managing
        separate credentials; thin adapter over the existing
        `Broker.get_history()`. Not live-tested (no Zerodha connected in
        this session) but structurally verified — server boots clean,
        follows the exact same code path as the already-tested broker.
  - [x] `data_providers/dhanhq.py` — needs a Dhan access token + client ID
        (Settings → Data Providers, added custom field labels for these
        since they're not a generic "key/secret" pair). Request payload
        fields, base URL, and auth headers verified directly against
        DhanHQ's official Python SDK source
        (github.com/dhan-oss/DhanHQ-py — `_historical_data.py`,
        `dhan_http.py`), not just docs paraphrase. Symbol resolution (Dhan
        needs a numeric `securityId`, not a tradingsymbol) verified against
        a real downloaded instrument master
        (images.dhan.co/api-data/api-scrip-master-detailed.csv) — resolving
        "NIFTY-Aug2026-FUT" correctly returns `securityId=58072`, matching
        NSE's own instrument token for the same contract exactly. **Not
        live-tested against an authenticated API call** — no Dhan account
        credentials available in this environment; same caveat as
        zerodha_kite.py. Symbol format is Dhan's own naming convention
        (e.g. "NIFTY-Aug2026-FUT"), not Kite/NSE-style — documented in the
        provider's description text.
  - [x] `data_providers/_template.py` — documented skeleton for adding
        TrueData or a TradingView-based forex provider later: copy the
        file, fill in `fetch_bars()`, done. No other code changes needed —
        same "drop a file" pattern already proven for strategies/brokers.
  - [x] Verified end-to-end via the actual UI: ran SMA Cross against
        `NIFTY26AUGFUT` fetched live from NSE Bhavcopy (Free) — 41 real
        bars, backtest completed in 32.7s, no errors. (That runtime is from
        sequential day-by-day fetching with no caching yet — a reasonable
        thing to optimize later if this provider sees frequent use, not
        blocking now.)
- [x] **No longer blocked**: real strategy rules provided and encoded for
      both live strategy families — the Options credit-spread rules (CP4+)
      and, 2026-09-21, the Gold XAUUSD Sweep-Reversal card (full rules,
      sizing, prop-firm mapping — see
      [gold-xauusd-sweep-reversal.md](../strategies/gold-xauusd-sweep-reversal.md)).
      Spot/futures OHLC (via the free NSE provider + Twelve Data for Gold) has
      been enough for both so far — no strategy has yet needed OI/IV/Greeks
      history.
- [x] Backtest metrics cross-checked against a manually-verified sample —
      done for real, 2026-09-22: the Gold Sweep-Reversal backtest ran against
      a real 6-month XAUUSD sample (201 trades) and the resulting R:R,
      expectancy, and per-level breakdown were hand-verified against the
      strategy's own stated rules (see the strategy doc §3) — this is what
      surfaced that the card's assumed 2.5:1 R:R doesn't hold in practice
      (~0.46:1 real), not an engine bug.

**Exit:** met, for the strategies built so far (Options + Gold). Revisit only
if a future strategy needs OI/IV/Greeks history the free tier doesn't cover.

---

## QP-3 — Paper / simulated live trading soak

Goal: run the registered setup(s) in paper mode against live market data for
a few weeks; validate signal timing matches expectation.

- [ ] Reuses existing paper trading engine (Phase 4/5, already built) — this
      phase is monitoring + bug-fixing, not new features, unless something's
      broken
- [ ] Multi-week paper run log, no missed/duplicate/mistimed signals

**Not started for either live strategy family, 2026-09-22.** Options is
technically unblocked (S3 paper mode exists, hasn't been run for a soak
period yet). Gold is explicitly blocked on Rakesh's own open decision — see
`docs/status/manual-tasks.md`'s 🔴 item — no real/paper capital risk is being
taken on this strategy's current parameters until that's resolved either way.

**Exit:** a few weeks of clean paper-mode operation with signal timing you'd
trust enough to act on manually.

---

## QP-4 — Alerting system (manual execution)

Goal: alert mode (already built — Telegram + `signal_log`, structurally zero
order-execution path) covers the **full trade lifecycle**, not just entry.

- [x] Target price + stop-loss fields confirmed present in the alert payload
      and `signal_log` schema for both live strategy families.
- [x] Exit alert built for **Options credit-spread-weekly** (CP4) — a real
      second Telegram message fires on setup-exit, paired with the entry via
      `signal_log`.
- [ ] **Gap found 2026-09-22, directly relevant to "usable from next week":**
      Gold Sweep-Reversal's alert mode is entry-only — `_fire_entry()` in
      `strategies/gold_sweep_reversal.py` calls `ctx.alert_entry()` with
      target/SL in the message, but there is no matching exit alert; you
      currently have to watch price yourself (or wait for the weekly digest)
      to know a signal hit target/SL. Non-alert modes (paper/live) already
      close and `ctx.notify()` correctly via `on_tick()` — alert mode never
      calls it. Not yet fixed; logged here rather than silently left as a
      "should already work" assumption.
- [x] You manually place buy/sell based on alerts only — no code executes
      orders in either strategy's alert mode (structurally true, not just
      policy — see QP-6's no-order-placement-tool note).

**Exit:** met for Options; **not yet met for Gold** — the missing exit alert
above is the one concrete gap standing between Gold's alert engine and "fully
usable end-to-end from Telegram."

---

## QP-5 — Full automation (real order placement)

Goal: flip validated setups from alert-only to live mode.

- [ ] Reuses existing live mode + Risk Manager + kill switch (Phase 5,
      already built) — apply to the specific validated strategies from QP-4,
      not the placeholder
- [ ] Only strategies that passed QP-3/QP-4 soak get promoted here — not a
      blanket switch

**Exit:** matches existing Phase 5 exit criterion, but for a real validated
strategy: small real order placed and filled cleanly, kill switch verified.

---

## QP-6 — LLM/AI support (MCP server)

Goal: expose xillion's control/query surface as MCP tools.

- [x] Built (CP7): `xillion-mcp` / `python -m xillion.mcp_server` exposes 9
      query tools plus 3 guarded control tools (start/stop an instance, kill
      switch). **No order-placement tool exists, structurally** — enforced by
      `test_no_order_placement_tool_exists`, not just a policy note.
- [x] Verified against a real MCP client (`prosper-engine`'s `TradingAgent`,
      CP8) calling a real running xillion backend.

**Exit:** met, 2026-08-26 (CP7) — an MCP client (Claude Desktop, a script, or
`prosper-engine`) can call these tools against a running xillion instance.

---

## QP-7 — AI pre-trade verification via prosper-engine

Goal: before an alert fires, `prosper-engine`'s LLM reviews the setup +
market context and attaches a success-probability estimate.

- [x] Wired (CP8): `prosper-engine`'s `TradingAgent` calls xillion's MCP tools
      in a real tool loop, verified against local Ollama (`qwen3:8b`).
- [x] `AI_CONFIDENCE_URL` hook in xillion's alert pipeline: a 0-100 confidence
      score is written to `signal_log.ai_confidence` as a background task
      after the alert fires (deliberately non-blocking — a local thinking
      model measured 30-60s+/call, too slow for the critical path). Empty by
      default (opt-in, zero network calls unless set).
- [x] Predicted-confidence vs. real outcome is trackable: the Journal now
      surfaces `ai_confidence` next to the signal's self-reported outcome
      (taken/skipped, win/loss/breakeven) — the comparison exists, though
      not enough real signals have fired yet to say whether the score is
      actually informative.

**Exit:** met (CP8) — a live alert can carry an AI-generated confidence
percentage, and the Journal lets you compare it against real outcomes after
the fact. Still using local Ollama, not a cloud LLM — an optional free
cloud-LLM key is logged as deferred in `manual-tasks.md` (Rakesh's call,
"keep for later"), not a blocker.

---

## QP-8 — Scale up capital

Goal: after QP-1 through QP-7 are proven with real time and small real
capital, increase position sizing.

- [ ] No new engineering — a decision gate based on the logged track record
      from QP-3/QP-5
- [ ] Revisit `DEFAULT_MAX_OPEN_POSITIONS` / loss-pct defaults
      (`render.yml`, `.env`) once ready

**Exit:** your own judgment call, informed by real logged performance data —
not a code milestone.

---

## Data providers: free → affordable → professional

For when a strategy from the trading course needs more than Kite gives you.
Don't pre-build for these — revisit once QP-2 hits an actual gap.

| Tier | Provider | What you get | Good for |
|---|---|---|---|
| **Free** | NSE bhavcopy (official EOD archives) | Raw daily OI/OHLC per contract, official source, needs your own ETL to reconstruct a usable chain history | DIY multi-year option-chain database if you're willing to build the pipeline yourself |
| **Free** | Public option-chain viewers (StocksRin, StockMojo, NiftyTrader, TradingTick) | CSV/manual export of historical strike-wise OI/IV/LTP | Manual spot-checking, not built for programmatic backtest ingestion (rate limits, fragile scraping, unclear ToS for algo use) |
| **Affordable (current default)** | Kite Connect Historical Data API (~₹500/mo) | OHLC candles per instrument (spot/futures/each option contract); F&O history ~1 year, equity/index 5+ years | Spot/futures-based setups, short-lookback single/multi-leg option price backtests — what QP-1/QP-2 need today |
| **Affordable** | Sensibull (~₹800/mo) | Options analytics/payoff UI on top of your broker; some community API access exists but it's not a bulk historical data feed | Manual strategy validation/payoff-diagram sanity checks, not a raw data source for your own engine |
| **Professional** | TrueData | Exchange-authorised vendor; live full option chain (strikes/IV/Greeks), historical tick (5 days default, extendable) + 1-min bars for longer periods | Real algo-trading-grade data if a strategy needs OI/IV/Greeks history at scale — check truedata.in/price for current tiers |
| **Professional** | Global Datafeeds | Exchange-authorised vendor; options chain + Greeks, historical & live | Same tier as TrueData, alternative vendor — compare current pricing at globaldatafeeds.in |
| **Analytics (not raw data)** | Opstra | Deep OI/volatility analytics, backtesting-style evaluation, API access | Intermediate/advanced strategy research and validation, not necessarily a substitute for owning the raw feed |

Sources: [Kite historical docs](https://kite.trade/docs/connect/v3/historical/) ·
[TrueData market data API](https://www.truedata.in/market-data-apis) ·
[Global Datafeeds APIs](https://globaldatafeeds.in/apis/) ·
[Opstra vs Sensibull](https://algotest.in/blog/opstra-vs-sensibull/) ·
[NSE option historical data](https://www.niftytrader.in/nse-option-historical-data)

---

## Cross-reference

- Underlying technical build (plugin core, backtest engine, live trading,
  risk manager, UI) is already done — see
  [09-progress-tracker.md](../archive/progress-tracker-phases-0-10.md) Phases 0–10.
- Remaining technical debt from that tracker (Phase 11 P2/P3: logs
  persistence, positions endpoint, Telegram live test) should get folded
  into QP-0/QP-3 rather than tracked twice.
- Deploy/infra workflow (Supabase, Render) lives in
  [xillion/CLAUDE.md](../../CLAUDE.md), not here — this doc is product phases
  only.

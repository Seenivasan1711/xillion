# Where things stand — plain-English view

> This is the quick-read version. For full engineering detail on any line
> here, see [`task-tracker.md`](task-tracker.md) (the source of truth,
> updated every session) and [`manual-tasks.md`](manual-tasks.md) (your
> actual to-do checklist). This file exists so you don't have to read
> those to answer "what can I do today, and what's next."

**Last updated:** 2026-08-26

---

## 1. What's fully working right now

The platform itself — the engine, not any specific strategy — is
**100% built**. All 15 platform checkpoints (CP1–CP15) are done: backtest
engine, live/paper trading engine, multi-leg option execution, protective
stops (software + real Zerodha GTT), trailing stops, an 18-check risk
engine, EOD reconciliation, a strategy journal, an MCP server + AI
assistant, Telegram alerting, and Dhan as a second broker — all tested
(431 tests passing), all deployed.

You can use all of this today:

- **Paper trading** — spawn any strategy in paper mode against real live
  Dhan market data. No real money. (Just fixed 2026-08-26: a Dhan-only
  setup couldn't resolve option strikes at all — see §4.)
- **Backtesting** — 2021–2026 real NIFTY + BANKNIFTY history is fully
  loaded (5+ years, continuous). Run any strategy against it from the
  Backtest page.
- **Telegram alerts** — strategy start/stop, order fills/rejections,
  drawdown breaches, kill-switch triggers.
- **The Journal** — every trade's outcome, auto-tagged where the data
  supports it.
- **The MCP/AI assistant** — read-only queries + guarded controls
  (start/stop/kill-switch) from Claude Desktop or similar, via
  `prosper-engine`.
- **Risk engine** — 18 checks (price collar, order-rate limits,
  duplicate-order dedup, notional sanity, etc.), all wired into every
  order, not just logged.
- **EOD safety net** — auto-flattens anything left open at close, then
  independently reconciles against the broker 30 minutes later.

## 2. Built, but not yet *proven* — needs it to actually run

These aren't missing code — they're missing **time** or **a real run**:

- **Options paper soak.** The credit-spread strategy is fully wired for
  paper mode. It needs to actually run for **2+ weeks of real market
  days** before its numbers mean anything — that's calendar time, not
  engineering time, and it can't be sped up. **Start this as early as
  possible**, since every day it isn't running is a day of soak time lost.
- **The real multi-year pass/fail backtest.** The credit-spread strategy's
  engine works, but the actual "run it against 2021–2026 and check it
  against the 8 pass/fail criteria" (`docs/strategies/knowledge-base/10-FIRST-STRATEGY-SPEC.md`
  §10) hasn't been executed yet. This is the thing that tells us whether
  the strategy is worth trading at all, before any real money is at risk.
  Next up.

## 3. Not built yet — genuinely new engineering

Everything below is a **new asset class**, not a fix or a gap in what
exists. None of it is started.

| Asset | What it needs | Rough size |
|---|---|---|
| **Gold (Funding Pips, XAUUSD)** | An MT5 broker plugin, 24×5 session calendar, currency field, FX lot math, Funding Pips drawdown rules as hard risk limits | ~19 hrs — **plus a hosting decision**: MetaTrader5's Python API is Windows-only, so this needs a VPS or bridge service before any code gets written |
| **Gold (MCX futures/options)** | MCX instrument/expiry resolution. Reuses your existing Zerodha/Dhan connections — no new broker needed | Cheaper than XAUUSD — no MT5 problem |
| **Stock options** | Stock-option chain resolution (reuses the index-option logic already built) | Moderate |
| **Stocks** | Equity instrument type (multiplier = 1, simplest of all) | Cheapest |
| **Crypto** | New exchange integration + 1% TDS modeled honestly in the fee engine (this alone likely makes most active strategies unprofitable — better to learn that in a backtest) | Lowest priority, by your own call |

## 4. Capability → blocker map

**"I want to do X" → what's actually stopping it → whose job that is**

| I want to... | Blocked by | Whose call |
|---|---|---|
| See a paper trade actually open | ~~Instrument cache was Zerodha-only~~ **Fixed 2026-08-26** — just needs the strategy's entry-day gate to line up (see below) | Done |
| Trade Options live with real money | (a) Zerodha/Dhan product-type decision — credit spread holds multi-day, both brokers hardcode intraday-only product today (b) static-IP whitelisting for Zerodha orders | You |
| Get real-broker GTT protection on Dhan (not just software stops) | Dhan's Forever Orders only accept CNC/MTF, not the INTRADAY product currently used — same product-type decision as above | You |
| Start the Gold/XAUUSD pipeline | MT5 hosting decision (VPS vs. bridge service) | You |
| Use a faster/hosted AI assistant instead of local Ollama | A free Gemini/Groq key in `prosper-engine/.env` — not blocking anything, just faster | You, whenever |
| Get the Zerodha-specific live path (better liquidity data) | Kite Connect subscription, ₹500/mo — deferred by your own call, not needed for anything today | You |

## 5. Right now, specifically

- Your paper instance (**Credit Spread Weekly — Paper**, on Dhan) can now
  resolve strikes. It will only actually *attempt* an entry on the one day
  each week that's exactly 4 days before NIFTY's weekly (Tuesday) expiry —
  next one is **Friday, 2026-08-28** — and only if that day's entry
  filters (trend alignment, minimum credit) also pass. Zero trades before
  then is expected, not broken.
- Next concrete step: run the real pass/fail backtest (§2) so we know
  whether this strategy is worth the paper-soak time at all.

---

*This file is a snapshot, not a live tracker — when it and
`task-tracker.md` disagree, trust `task-tracker.md` and treat this one as
due for an update.*

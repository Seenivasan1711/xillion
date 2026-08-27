# 12 — User Guide

Everything you need to actually use Xillion after it's running. This guide assumes `make dev` is running and the UI is open at **http://localhost:5174**.

> **Last updated:** 2026-08-27, against Track A (CP1–CP15, all done or code-complete)
> and the Supabase→local backtest-warehouse split. See
> [docs/status/task-tracker.md](../status/task-tracker.md) for exact current
> status of any item mentioned here.

---

## Table of contents

1. [First-time setup](#1-first-time-setup)
2. [Logging in](#2-logging-in)
3. [Connecting a broker (Zerodha / Dhan)](#3-connecting-a-broker-zerodha--dhan)
4. [Local backtest data (NSE Bhavcopy warehouse)](#4-local-backtest-data-nse-bhavcopy-warehouse)
5. [Running a backtest](#5-running-a-backtest)
6. [Creating a strategy instance (paper trading)](#6-creating-a-strategy-instance-paper-trading)
7. [Going live](#7-going-live)
8. [Dashboard explained](#8-dashboard-explained)
9. [Kill switch](#9-kill-switch)
10. [Journal & Alerts](#10-journal--alerts)
11. [Dev page (logs + WS status)](#11-dev-page-logs--ws-status)
12. [Writing a custom strategy](#12-writing-a-custom-strategy)
13. [Notifications (Telegram)](#13-notifications-telegram)
14. [MCP server — letting an AI assistant use the app](#14-mcp-server--letting-an-ai-assistant-use-the-app)
15. [Settings reference](#15-settings-reference)
16. [Known limitations](#16-known-limitations)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. First-time setup

```bash
# Clone and install
git clone <your-repo-url>
cd xillion
make setup       # creates .env, installs Python + Node deps, creates data/
```

Open `.env` and review the defaults. The only variable you must set before going live is `APP_SECRET_KEY` — change it from the placeholder to a long random string.

```bash
make dev         # starts backend on :8001 and frontend on :5174
```

| URL | Purpose |
|-----|---------|
| http://localhost:5174 | React UI |
| http://localhost:8001/api/docs | Swagger interactive API docs |
| http://localhost:8001/api/health | Health check (JSON) |

> **Two separate databases.** Live app state (users, sessions, strategy
> instances, credentials, journal — under 1MB) lives in the main DB
> (`DATABASE_URL`, Supabase Postgres in this project's deployment). Backtest
> history (`bar`, `bar_coverage`, `option_chain_snapshot`) lives in a
> **separate, local-only** SQLite warehouse (`data/backtest_warehouse.db`) —
> see §4. This keeps a free-tier cloud Postgres from filling up with
> regenerable historical cache.

---

## 2. Logging in

On first visit you land on a **Setup** page (only shown once).

1. Choose a username and password. This becomes your single admin account.
2. Optionally enable **TOTP 2FA** — you'll be shown a QR code to scan in any authenticator app (Google Authenticator, Aegis, etc.). You can also enable it later under **Settings → Account**.
3. Click **Create account**. You're redirected to the login page.
4. Log in. If you set up TOTP, you'll be prompted for the 6-digit code after entering your password.

> Sessions persist across browser refreshes until you log out or the session expires (7 days by default).

---

## 3. Connecting a broker (Zerodha / Dhan)

**Settings → Brokers tab.** Xillion supports two brokers today, connected independently — an instance picks which one it trades through, and either can run at once. Credentials for both are encrypted at rest (Fernet) and entered through the app, never `.env`.

### Zerodha

| Field | Where to find it |
|-------|-----------------|
| API Key | Zerodha Kite developer console |
| API Secret | Same — shown once on app creation |
| User ID | Your Zerodha client ID (e.g. `AB1234`) |
| Password | Your Zerodha login password |
| TOTP Secret | The secret used to generate your Zerodha TOTP (not the 6-digit code — the base32 seed) |

The backend auto-reconnects at **6:15 AM IST** daily to refresh the access token. Zerodha's bracket orders are discontinued by the broker itself — protective stops use GTT triggers instead (see §16).

### Dhan

| Field | Where to find it |
|-------|-----------------|
| Client ID | Dhan account dashboard |
| Access Token | Dhan API access token (generate/refresh in the Dhan web app) |

Daily token re-validation runs at **6:30 AM IST** (15 min after Zerodha's, so both brokers don't hit their auth endpoints at the same moment). Dhan is genuinely usable end-to-end in paper mode without ever connecting Zerodha or paying for Kite Connect — useful if you want to see the system trade for free first.

Either broker: if the connection succeeds you'll see **Connected** in the brokers section and the topbar status dot turns green. If it fails, the error is shown inline.

---

## 4. Local backtest data (NSE Bhavcopy warehouse)

Real backtests need real historical bars and option-chain data. Xillion caches this for free from **NSE Bhavcopy** into a local SQLite warehouse (`data/backtest_warehouse.db`), separate from the main app DB — see the note in §1.

**As shipped, NIFTY + BANKNIFTY are pre-backfilled 2021-01-01 → present** (about 4.5M bars, 2.2M option-chain rows). Confirm coverage any time under **Settings → Data Providers** — it shows the exact date range currently cached and lets you trigger a backfill for a new range or symbol (fetches day-by-day from NSE, free, no API key needed).

**This warehouse is local-only for now** — Render's free plan has no persistent disk, so a deployed instance re-fetches from NSE on demand rather than having this cache. Real backtesting is a local-workstation activity until/unless that's revisited.

**Back it up before anything risky** (wiping `data/`, moving machines) — rebuilding from scratch takes hours:
```bash
make backup-warehouse                                   # → data/backups/warehouse/warehouse_<ts>.db.gz
make restore-warehouse FILE=data/backups/warehouse/warehouse_<ts>.db.gz
```
Whole-file snapshot (gzipped), so it automatically covers any table added later. Upload the `.gz` wherever you keep backups (Drive, etc.) — there's no cloud copy by design.

---

## 5. Running a backtest

**Backtest page.** Two ways to get bars in:

### With the local warehouse (recommended — real data, zero setup)

1. **Strategy** — pick from the dropdown (shows every strategy discovered in `strategies/`, e.g. `Credit Spread Weekly`, `SMA Cross`).
2. **Data provider** — choose `NSE Bhavcopy`.
3. **Symbol** (`NIFTY` / `BANKNIFTY`), **exchange**, **timeframe**, and a **date range** inside the covered window from §4.
4. **Initial capital**, **slippage (bps)**, and any strategy-specific **parameters** (auto-rendered from the strategy's `params_schema`).
5. Click **Run Backtest**. Bars are fetched from the local warehouse (cache-hit — no network call) or from NSE directly if the range isn't cached yet (cached automatically for next time).

Prefer to script it? `POST /api/backtest/run-provider` does the same thing — see `http://localhost:8001/api/docs`. `POST /api/backtest/optimize` (grid search) and `/walk-forward` (walk-forward validation) run parameter sweeps over the same warehouse-backed bars, with results ranked by your chosen metric.

### With a CSV file (bring your own data)

1. Prepare a CSV in this format:
   ```
   symbol,ts,open,high,low,close,volume
   NIFTY,2024-01-15T09:15:00,21000,21050,20990,21030,12500
   NIFTY,2024-01-15T09:30:00,21030,21080,21010,21060,9800
   ```
   `ts` must be ISO 8601 (date + time). Extra columns are ignored. You can include a `timeframe` column if mixing timeframes.
2. Fill in the same strategy/instruments/timeframe/capital/slippage/params fields as above, upload the CSV, click **Run Backtest**.

### Reading results

Every run — either path — renders an equity curve, metrics grid, and trade log in place, and is saved to **Run history** on the same page for later comparison.

| Metric | What it means |
|--------|--------------|
| Total return | Total % gain/loss over the period |
| CAGR | Annualised return |
| Sharpe | Risk-adjusted return (higher = better; > 1.0 is respectable) |
| Sortino | Like Sharpe but only penalises downside volatility |
| Max DD | Largest peak-to-trough equity drop |
| Win rate | % of trades that were profitable |
| Profit factor | Gross profit ÷ gross loss (> 1.5 is decent) |
| Expectancy | Average ₹ expected per trade |
| Avg holding | Average bars held per trade |

> A backtest that looks great is still just a backtest. Check for lookahead bias, data snooping, and survivorship bias before reading too much into it.

**Once a strategy checks out here**, promote it the normal way — commit the file, PR, merge to `main`. The strategy code has no dependency on the local warehouse; live/paper trading runs on real-time broker ticks, not this cache.

---

## 6. Creating a strategy instance (paper trading)

**Strategies page → New Instance**

1. Click **+ New Instance**.
2. Fill in:
   - **Name** — a label for this instance (e.g. `SMA Cross NIFTY`)
   - **Strategy** — choose from discovered strategies
   - **Broker** — which connected broker (Zerodha or Dhan) this instance trades/gets ticks through
   - **Mode** — select **Paper** (needs the chosen broker connected for live ticks; without it the strategy idles)
   - **Instruments** — symbols to subscribe to (e.g. `NIFTY`, `RELIANCE`)
   - **Timeframe** — bar timeframe (e.g. `5m`, `15m`)
   - **Capital allocation** — ₹ reserved for this instance
   - **Parameters** — strategy-specific knobs
   - **Auto start/stop** (optional) — toggle to start/stop this instance automatically at market open/close
3. Click **Create**. The instance appears in the list with status **idle**.
4. Click **Start** to begin running. Status changes to **running** with a live dot.

### Paper mode behaviour

- Strategy receives live ticks (from whichever broker it's configured for) aggregated into bars at the chosen timeframe.
- Order fills are simulated by the paper broker with a small latency + slippage.
- No real orders are placed.
- `ctx.state` persists across a restart (survives a deliberate stop/start or redeploy — not yet an independent crash-watchdog for an ungraceful process death, see §16).

### Stopping

Click **Stop** on the instance card or row. The strategy's `on_stop()` hook is called before the runner shuts down.

---

## 7. Going live

> **Read `docs/process/go-live-checklist.md` and complete every item before switching to live mode.**

1. Run the strategy in paper mode for at least one full market session (multi-leg/options strategies: a full paper-soak window per `docs/status/manual-tasks.md`). Verify the logic behaves as expected.
2. Edit the instance (or recreate it) in **live** mode.
3. Live mode routes orders through the real broker. Fills are real money.
4. The risk manager gates every order — 18 checks including price collar, OPS throttle, daily loss cap, max open positions, duplicate/self-trade detection. See **Settings → Risk** to configure limits. Every decision (approved or rejected, with the specific failed checks) is written to an append-only, hash-chained audit log.

### Before each live session

- Confirm the broker you're trading through is connected (green dot in topbar).
- Check risk limits are set appropriately.
- Know where the kill switch is (top-right dropdown, skull icon).

---

## 8. Dashboard explained

| Section | What it shows |
|---------|--------------|
| **Hero P&L card** | Today's realised PnL in ₹ and %, intraday sparkline built from fills, 4-stat footer (open trades, closed trades, win rate, avg trade PnL) |
| **Equity curve card** | Historical equity by day. Use the 1W/1M/3M/1Y selector to zoom. |
| **Stat strip** | Strategies running/total · Broker status · Drawdown % vs daily limit · Today's order count |
| **Risk budget** | Two gauges: capital deployed % and daily loss budget consumed %. Table shows individual risk limits. |
| **Live ticks** | Real-time tick grid from the WebSocket feed, up to 8 symbols. |
| **Active strategies** | Running and idle instances with live P&L, trade count, capital, and start/stop controls. |

The dashboard polls every **15 seconds** and receives tick/order updates instantly over WebSocket.

---

## 9. Kill switch

The **kill switch** is in the top-right corner (skull icon dropdown). It has four options:

| Option | What happens |
|--------|-------------|
| Pause all strategies | Stops all running strategy runners. Does not cancel open orders. |
| Cancel all orders | Sends cancel requests to the broker for all open orders. |
| Flatten positions | Exits all open positions at market. |
| **Kill switch (2-step)** | All three above in one atomic action, gated by a fresh TOTP code if 2FA is enabled. Latches the kill flag in memory — strategies cannot restart until you reset it. |

**To reset:** same dropdown → Reset kill switch. Also requires a fresh TOTP if 2FA is enabled.

A kill switch event fires a Telegram alert (if configured) and broadcasts to all connected UI tabs. There is also an automatic, scheduled EOD safety net independent of any strategy: a square-off enforcer flattens anything the broker reports open at 15:15 IST, and a reconciliation check 30 minutes later flags (and alerts on) any remaining discrepancy — designed to work "even when everything else is broken," since it queries the broker directly rather than trusting xillion's own in-memory state.

---

## 10. Journal & Alerts

### Journal (`/journal`)

Every closed trade — from a real live/paper fill or a backtest run — lands here, whichever mode produced it. Shows entries, win rate, and auto-tagged outcomes:

- `win` / `loss` — from real P&L
- `stopped_out` / `target_hit` — only when the exit price genuinely crossed the recorded stop-loss/target level
- Everything else defaults to `unclassified` — clicking a row lets you set a manual failure mode (e.g. `late_entry`, `gap`, `regime_change`) plus a free-text note; this is honest rather than guessed, since tagging those automatically would need tick-level fill/rejection data the system doesn't capture yet.

Filter by strategy. Exporting a strategy's journal writes its failure log + version history into `docs/strategies/<name>.md`, which is also what an AI assistant's RAG layer reads from (§14) — so a well-tagged loss here becomes something a future conversation can actually recall.

### Alerts (`/signals`)

Alert-mode signal history: every ENTER/EXIT with its target and stop-loss, correctly linked (an EXIT always matches *its own* ENTER, even with repeated tags/re-entries). Same data that gets formatted into a Telegram message when notifications are on.

---

## 11. Dev page (logs + WS status)

Streams structured log entries from the backend in real time over WebSocket, plus a live connection-status badge for the WS feed itself.

- Use the **level filter** (all / info / warn / err / debug) to narrow the view.
- Use the **search box** to filter by any keyword (strategy name, symbol, event type).
- Logs persist to the DB (24h retention) — history loads on page load, then tails live. Not an unbounded audit trail; for that, see the risk audit log (§7).

---

## 12. Writing a custom strategy

Two ways to build one — pick whichever fits:

### No-code: condition builder

**Strategies page → New strategy → Condition builder.** Compose entry/exit rules from rows of `metric` (SMA/EMA/RSI/ATR/VWAP/Bollinger/MACD/Supertrend, with a configurable period) + `operator` + `threshold or another metric`. Long or short, entry and exit are each an AND of their rows. Saved as a JSON params blob against the generic `Condition Strategy` plugin — no Python file needed. Optionally run a **parameter sweep** (grid search or walk-forward) over the resulting strategy from the Backtest page.

### Code: drop a Python file

```bash
cp strategies/_template.py strategies/my_strategy.py
```

Edit the file. Minimum required:

```python
class MyStrategy(Strategy):
    name = "My Strategy"
    version = "1.0.0"
    params_schema = [
        {"name": "fast", "type": "int", "default": 10, "description": "Fast MA period"},
        {"name": "slow", "type": "int", "default": 30, "description": "Slow MA period"},
    ]

    async def on_start(self, ctx: StrategyContext) -> None:
        self.fast = ctx.params["fast"]
        self.slow = ctx.params["slow"]

    async def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        # your logic here — call ctx.place_order() to trade
        pass

    async def on_stop(self, ctx: StrategyContext, reason: str) -> None:
        pass
```

Once saved, click **Reload strategies** in the Strategies page (or restart the backend). The strategy appears in the dropdown immediately.

### Context API

| Method | What it does |
|--------|-------------|
| `ctx.place_order(request)` | Submit an order (passes through the 18-check risk manager first) |
| `ctx.cancel_order(client_order_id)` | Cancel a pending/open order |
| `ctx.position(symbol)` | Get current position for a symbol |
| `ctx.positions()` | All open positions |
| `ctx.open_orders()` | All pending/submitted orders |
| `ctx.equity()` | Current equity = capital + realised + unrealised PnL |
| `ctx.realised_pnl_today()` | Today's realised PnL |
| `ctx.history(symbol, timeframe, n)` | Fetch last N bars — from the DB warehouse if live/paper history is short |
| `ctx.now()` | Current time — real wall-clock live/paper, the currently-simulated bar's timestamp in backtest (use this, not `datetime.now()`, for anything time-gated) |
| `ctx.alert_entry(...)` / `ctx.alert_exit(...)` | Fire an ENTER/EXIT alert signal (target/stop-loss recorded, auto-linked, shows on the Alerts page) |
| `ctx.log(level, message, **fields)` | Emit a structured log entry |
| `ctx.params` | Dict of configured params |
| `ctx.state` | Persistent dict — survives a restart (DB-backed, not just in-memory) |

### OrderRequest fields

```python
from xillion.core.events import OrderRequest, Side, OrderType

req = OrderRequest(
    symbol="NIFTY",
    exchange="NSE",
    side=Side.BUY,           # or Side.SELL
    quantity=1,
    order_type=OrderType.MARKET,
    price=None,              # required for LIMIT orders
    tag="entry",             # optional label shown in order log
)
order = await ctx.place_order(req)
```

For a multi-leg (spread/straddle/condor) strategy, see `xillion/core/multileg.py` and the real example in `strategies/credit_spread_weekly.py` — legs are grouped into a `MultiLegSpec`, with entry/exit ordering and leg-failure handling built in rather than something each strategy has to reimplement.

---

## 13. Notifications (Telegram)

**Settings → Notifications tab**

1. Create a Telegram bot via [@BotFather](https://t.me/botfather) — copy the bot token.
2. Start a chat with your bot (or add it to a group). Get the chat ID using `https://api.telegram.org/bot<token>/getUpdates`.
3. Enter the **Bot token** and **Chat ID** in Settings (stored encrypted in the DB, not `.env`).
4. Toggle on the alert types you want:
   - Strategy started/stopped
   - Order filled
   - Order rejected
   - Drawdown breach
   - Kill switch fired
   - System task crash / gave-up-restarting alerts
5. Click **Save** — takes effect immediately on the running notifier, no restart needed.

Test it by clicking **Send test message**.

---

## 14. MCP server — letting an AI assistant use the app

`xillion-mcp` (or `python -m xillion.mcp_server`) exposes xillion over the Model Context Protocol, so an AI assistant (Claude Desktop, or a custom agent like this project's `prosper-engine`) can query and lightly control the running app — every tool is a thin wrapper over the real REST API, so it inherits the app's real auth rather than a second path.

**Read-only tools:** `list_strategies`, `get_positions`, `get_trades_today`, `get_portfolio`, `run_backtest`, `get_journal`.
**Guarded control tools:** `start_instance`, `stop_instance`, `kill_switch` (the kill switch always asks for a fresh TOTP code, same gate as the web UI, never bypassed).
**No order-placement tool exists** — structurally, not just by convention; an assistant cannot place a trade through this server, full stop.

Requires the real backend already running:
```bash
export XILLION_API_BASE=http://localhost:8001/api   # default if unset
export XILLION_MCP_USERNAME=<your username>
export XILLION_MCP_PASSWORD=<your password>
export XILLION_MCP_TOTP_CODE=<code>                 # only if 2FA is on and logging in fresh
xillion-mcp
```
Point a local MCP client (Claude Desktop, etc.) at it with those env vars set in its config.

---

## 15. Settings reference

| Tab | What you configure |
|-----|--------------------|
| **Brokers** | Zerodha + Dhan credentials, connection status, test/reconnect buttons |
| **Data Providers** | NSE Bhavcopy coverage (date range cached) and backfill trigger — see §4 |
| **Risk** | Daily loss % cap, per-trade risk %, max open positions, position size cap (₹), OPS throttle |
| **Notifications** | Telegram bot token + chat ID, per-event toggles |
| **Account** | Username display, timezone, theme (dark/light), TOTP re-enroll |
| **Configuration** | Alert-event toggles and other app-level configuration |
| **Danger zone** | Reset all trading data · Wipe everything (drops all DB tables and re-creates them) |

Risk limits take effect immediately — no restart needed. They are read by the risk manager on every order check.

---

## 16. Known limitations

Honestly-documented current gaps — not guessed at, pulled from the same source (`docs/status/task-tracker.md`) that tracks engineering status:

| Gap | Impact | Status |
|-----|--------|--------|
| **Backtest data is local-only** | Render (no persistent disk on the free plan) can't cache the NSE Bhavcopy warehouse — real backtesting only works on a local workstation for now. | By design for now, see §4. |
| **Real-broker bracket/GTT for Dhan** | Software protective stops (survive a *deliberate* restart, §6) are the only protection on Dhan; Zerodha has real GTT-triggered stops as a broker-side backstop. | Blocked on a product-type decision (Dhan's Forever Orders need `CNC`/`MTF`, not the `INTRADAY` product xillion currently trades under). |
| **No independent crash-watchdog** | A *deliberate* stop/restart is state-safe (`ctx.state` persists). An ungraceful process crash is not automatically detected/restarted — background tasks self-heal, but a full process death (e.g. OOM-killed) is not yet watched. | Open, tracked as a hardening item. |
| **VIX filter / economic-calendar veto not wired** (credit-spread strategy) | The strategy's entry logic skips two of the knowledge base's documented filters — no VIX or economic-calendar data provider is connected yet. Visible in the UI as an unchecked option, not silently absent. | Open. |
| **Sensex unsupported in backtest** | NSE Bhavcopy (the free data source) doesn't cover BSE-listed instruments. Live/paper trading isn't affected — this is a backtest-data-source gap only. | Open. |
| **Failover between brokers** | If Zerodha is down, Dhan does not automatically take over (or vice versa) — both connect independently, no auto-switch. | Deferred, not P0. |

---

## 17. Troubleshooting

### "No strategies found"
- The `strategies/` directory must have at least one valid `.py` file.
- Click **Reload** in the Strategies page after adding a file.
- Check the Dev page for plugin loader errors.

### "No broker classes in DB. Reload plugins first."
- The brokers directory must have at least one valid broker plugin.
- Run `make dev` fresh — plugin discovery runs at startup.

### Broker connection fails
- Zerodha: double-check the TOTP secret — it's the base32 seed, not a generated 6-digit code. Ensure the Kite developer console app is not revoked.
- Dhan: confirm the access token hasn't expired — regenerate it in the Dhan web app.
- "Invalid access token" after it was working: the daily token refresh may have failed — wait for the next scheduled refresh (6:15 AM Zerodha / 6:30 AM Dhan IST) or restart the backend.

### Strategy stays idle / no ticks
- Paper/live mode requires the instance's configured broker to be connected for live ticks.
- Verify the instance is **running** (not just created).
- Open the Dev page and look for `tick broadcaster started`.

### Backtest returns "No bars returned"
- The date range or symbol isn't covered yet — check **Settings → Data Providers**, trigger a backfill for that range, then re-run.

### Frontend can't reach backend
- Backend runs on port **8001** and frontend on **5174**.
- Vite proxies `/api` and `/ws` to the backend automatically in dev mode — no CORS config needed in the browser.
- If you see 401 responses, your session expired — log in again.

### Port already in use
```bash
lsof -i :8001     # find what's using the port
kill -9 <PID>
make dev
```

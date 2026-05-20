# 12 — User Guide

Everything you need to actually use Xillion after it's running. This guide assumes `make dev` is running and the UI is open at **http://localhost:5174**.

---

## Table of contents

1. [First-time setup](#1-first-time-setup)
2. [Logging in](#2-logging-in)
3. [Connecting Zerodha](#3-connecting-zerodha)
4. [Running a backtest](#4-running-a-backtest)
5. [Creating a strategy instance (paper trading)](#5-creating-a-strategy-instance-paper-trading)
6. [Going live](#6-going-live)
7. [Dashboard explained](#7-dashboard-explained)
8. [Kill switch](#8-kill-switch)
9. [Logs page](#9-logs-page)
10. [Writing a custom strategy](#10-writing-a-custom-strategy)
11. [Notifications (Telegram)](#11-notifications-telegram)
12. [Settings reference](#12-settings-reference)
13. [Known limitations](#13-known-limitations)
14. [Troubleshooting](#14-troubleshooting)

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

---

## 2. Logging in

On first visit you land on a **Setup** page (only shown once).

1. Choose a username and password. This becomes your single admin account.
2. Optionally enable **TOTP 2FA** — you'll be shown a QR code to scan in any authenticator app (Google Authenticator, Aegis, etc.). You can also enable it later under **Settings → Account**.
3. Click **Create account**. You're redirected to the login page.
4. Log in. If you set up TOTP, you'll be prompted for the 6-digit code after entering your password.

> Sessions persist across browser refreshes until you log out or the session expires (7 days by default).

---

## 3. Connecting Zerodha

**Settings → Brokers tab**

You need four things from your Zerodha account:

| Field | Where to find it |
|-------|-----------------|
| API Key | Zerodha Kite developer console |
| API Secret | Same — shown once on app creation |
| User ID | Your Zerodha client ID (e.g. `AB1234`) |
| Password | Your Zerodha login password |
| TOTP Secret | The secret used to generate your Zerodha TOTP (not the 6-digit code — the base32 seed) |

Fill all five fields and click **Save & Connect**. Credentials are encrypted at rest using Fernet symmetric encryption.

If the connection succeeds you'll see **Zerodha: Connected** in the brokers section and the topbar status dot turns green. If it fails, the error message is shown inline — the most common cause is a wrong TOTP secret.

> The backend auto-reconnects at 6:15 AM IST daily to refresh the Zerodha access token.

---

## 4. Running a backtest

**Backtest page**

### With a CSV file

1. Prepare a CSV in this format:
   ```
   symbol,ts,open,high,low,close,volume
   NIFTY,2024-01-15T09:15:00,21000,21050,20990,21030,12500
   NIFTY,2024-01-15T09:30:00,21030,21080,21010,21060,9800
   ```
   `ts` must be ISO 8601 (date + time). Extra columns are ignored. You can include a `timeframe` column if mixing timeframes.

2. On the Backtest page:
   - **Strategy** — pick from the dropdown (shows all strategies in `strategies/`)
   - **Instruments** — comma-separated symbols (e.g. `NIFTY,BANKNIFTY`)
   - **Timeframe** — must match your CSV data (e.g. `15m`, `1h`, `1d`)
   - **Initial capital** — starting equity in ₹
   - **Slippage** — basis points added to every fill (5 bps = 0.05%)
   - **Parameters** — strategy-specific; auto-rendered from the strategy's `params_schema`

3. Upload the CSV and click **Run Backtest**.

Results appear in-page: metrics grid, equity curve sparkline, and a trade log of the last 6 trades. The run is saved to the database — you can re-run with different params.

### Interpreting results

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

---

## 5. Creating a strategy instance (paper trading)

**Strategies page → New Instance**

1. Click **+ New Instance**.
2. Fill in:
   - **Name** — a label for this instance (e.g. `SMA Cross NIFTY`)
   - **Strategy** — choose from discovered strategies
   - **Mode** — select **Paper** (you must have Zerodha connected for live ticks; without it the strategy idles)
   - **Instruments** — symbols to subscribe to (e.g. `NIFTY`, `RELIANCE`)
   - **Timeframe** — bar timeframe (e.g. `5m`, `15m`)
   - **Capital allocation** — ₹ reserved for this instance
   - **Parameters** — strategy-specific knobs
3. Click **Create**. The instance appears in the list with status **idle**.
4. Click **Start** to begin running. Status changes to **running** with a live dot.

### Paper mode behaviour

- Strategy receives live Zerodha ticks aggregated into bars at the chosen timeframe.
- Order fills are simulated by the paper broker with a small latency + slippage.
- No real orders are placed.
- P&L is tracked in-memory (persisted to DB in Phase 10).

### Stopping

Click **Stop** on the instance card or row. The strategy's `on_stop()` hook is called before the runner shuts down.

---

## 6. Going live

> **Read `docs/11-go-live-checklist.md` and complete every item before switching to live mode.**

1. Run the strategy in paper mode for at least one full market session. Verify the logic behaves as expected.
2. On the instance card, the mode badge shows **paper**. Edit the instance (or recreate it) in **live** mode.
3. Live mode routes orders through the real Zerodha broker. Fills are real money.
4. The risk manager gates every order: OPS limit, per-strategy daily loss cap, max open positions. See **Settings → Risk** to configure limits.

### Before each live session

- Confirm Zerodha is connected (green dot in topbar).
- Check risk limits are set appropriately.
- Know where the kill switch is (top-right dropdown, skull icon).

---

## 7. Dashboard explained

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

## 8. Kill switch

The **kill switch** is in the top-right corner (skull icon dropdown). It has four options:

| Option | What happens |
|--------|-------------|
| Pause all strategies | Stops all running strategy runners. Does not cancel open orders. |
| Cancel all orders | Sends cancel requests to Zerodha for all open orders. |
| Flatten positions | Exits all open positions at market. |
| **Kill switch (2-step)** | All three above in one atomic action, gated by TOTP if 2FA is enabled. Latches the kill flag in memory — strategies cannot restart until you reset it. |

**To reset:** same dropdown → Reset kill switch. Also requires TOTP if 2FA is enabled.

A kill switch event fires a Telegram alert (if configured) and broadcasts to all connected UI tabs.

---

## 9. Logs page

The Logs page streams structured log entries from the backend in real time over WebSocket.

- Use the **level filter** (all / info / warn / err / debug) to narrow the view.
- Use the **search box** to filter by any keyword (strategy name, symbol, event type).
- The **filtered line count** updates as you type.
- The **tailing** badge shows when new lines are being appended.

Logs are ephemeral (in-memory ring buffer). They are not persisted between restarts — for persistent logging, configure a file or remote sink via `structlog` in the backend.

---

## 10. Writing a custom strategy

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
| `ctx.place_order(request)` | Submit an order (passes through risk manager first) |
| `ctx.cancel_order(client_order_id)` | Cancel a pending/open order |
| `ctx.position(symbol)` | Get current position for a symbol |
| `ctx.positions()` | All open positions |
| `ctx.open_orders()` | All pending/submitted orders |
| `ctx.equity()` | Current equity = capital + realised + unrealised PnL |
| `ctx.realised_pnl_today()` | Today's realised PnL |
| `ctx.history(symbol, timeframe, n)` | Fetch last N bars from DB |
| `ctx.log(level, message, **fields)` | Emit a structured log entry |
| `ctx.params` | Dict of configured params |
| `ctx.state` | Persistent dict — survives bar-to-bar within a session |

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

---

## 11. Notifications (Telegram)

**Settings → Notifications tab**

1. Create a Telegram bot via [@BotFather](https://t.me/botfather) — copy the bot token.
2. Start a chat with your bot (or add it to a group). Get the chat ID using `https://api.telegram.org/bot<token>/getUpdates`.
3. Enter the **Bot token** and **Chat ID** in Settings.
4. Toggle on the alert types you want:
   - Strategy started/stopped
   - Order filled
   - Order rejected
   - Drawdown breach
   - Kill switch fired
5. Click **Save**.

Test it by clicking **Send test message** (or triggering a kill switch reset).

---

## 12. Settings reference

| Tab | What you configure |
|-----|--------------------|
| **Brokers** | Zerodha API credentials, connection status, test button |
| **Risk** | Daily loss % cap, per-trade risk %, max open positions, position size cap (₹), OPS throttle |
| **Notifications** | Telegram bot token + chat ID, per-event toggles |
| **Account** | Username display, timezone, theme (dark/light), TOTP re-enroll |
| **Danger zone** | Reset all trading data · Wipe everything (drops all DB tables and re-creates them) |

Risk limits take effect immediately — no restart needed. They are read by the risk manager on every order check.

---

## 13. Known limitations

These are confirmed gaps as of Phase 9 (May 2026). They are tracked as Phase 10 work.

| Gap | Impact | Workaround |
|-----|--------|-----------|
| **DB persistence for orders/fills** | `OrderRecord`, `FillRecord`, `PositionRecord`, `DailyRiskState`, `DailyStrategyPnl` are never written during live trading — the execution pipeline is in-memory only. | P&L figures in the dashboard come from in-memory strategy contexts and reset to zero on backend restart. |
| **Win rate always 0** | Dashboard hero card shows `—` for win rate. | Computed once per-trade DB persistence is in place. |
| **`pnl` and `trade_count` in strategy table** | Show `0` while a strategy is running (positions update but fills aren't tracked back to the context yet). | Check the Logs page for individual order events. |
| **Historical equity curve** | Flat / single bar until `DailyStrategyPnl` rows exist. | Run paper mode for a few days first. |
| **Intraday sparkline** | Empty on first run of the day (no fills yet). | Fills drive the curve; it populates during live/paper trading sessions. |

---

## 14. Troubleshooting

### "No strategies found"
- The `strategies/` directory must have at least one valid `.py` file.
- Click **Reload** in the Strategies page after adding a file.
- Check the Logs page for plugin loader errors.

### "No broker classes in DB. Reload plugins first."
- The brokers directory must have at least one valid broker plugin.
- Run `make dev` fresh — plugin discovery runs at startup.

### Zerodha connection fails
- Double-check the TOTP secret — it's the base32 seed, not a generated 6-digit code.
- Ensure the Zerodha API app is not revoked in the Kite developer console.
- If the error says "invalid access token", the daily token refresh may have failed — wait for the 6:15 AM IST refresh or restart the backend.

### Strategy stays idle / no ticks
- Paper mode requires Zerodha to be connected for live ticks.
- Verify at least one strategy instance is **running** (not just created).
- Open the Logs page and look for `tick broadcaster started`.

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

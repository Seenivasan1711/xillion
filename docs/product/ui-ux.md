# 06 — UI / UX Design

The UI's job is **to keep you calm and in control**. Markets are stressful. The interface should never add to that. Defaults that surface the right info; one-click actions for the things you do most; friction (confirmation, 2FA) for the things that hurt if done by accident.

## 1. Design principles

1. **Information density without clutter.** A trader's dashboard, not a marketing page.
2. **Status before content.** Top of every screen tells you the system state at a glance: green / yellow / red.
3. **One screen, one job.** Don't make the dashboard try to be the strategy editor.
4. **Mobile-respectful.** You'll be on your phone during stressful moments. Critical actions reachable with a thumb.
5. **Consistency > novelty.** Same colours mean the same things everywhere. Same layout patterns across pages.
6. **Friction where it matters.** Going live, kill switch, deleting a strategy → confirm. Toggling a chart timeframe → no confirm.
7. **Logs are first-class.** Every action shows up in the audit log; the audit log is searchable from the UI.

## 2. Visual language

### Colour semantics (used consistently)

| Colour | Meaning | Hex (Tailwind) |
|---|---|---|
| Green | profit, healthy, "go" | `emerald-500` |
| Red | loss, alert, "stop" | `rose-500` |
| Amber | warning, paused | `amber-500` |
| Blue | info, neutral data | `sky-500` |
| Slate (greyscale) | structure, text | `slate-50..950` |

Profit & loss values: **always** green/red text with a sign. Never just a number.

### Typography

- Headings: Inter (sans-serif), tight tracking
- Body: Inter
- Numbers, prices, log lines: JetBrains Mono (monospace, so columns line up)

### Spacing

- Generous on desktop (16/24/32 px scale)
- Compact on mobile (8/12/16 px scale)
- Tables collapse to cards on narrow viewports

### Theme

- Dark mode default. Light mode available.
- Dark mode background: `slate-950`. Surface: `slate-900`. Borders: `slate-800`.

## 3. Information architecture

```
Top bar (always visible)
 ├ App name + status pill (e.g. "Live · 3 strategies running")
 ├ Mode toggle (today's date / market session indicator)
 ├ Notifications bell
 ├ Profile menu
 └ KILL SWITCH (red, prominent, far right)

Left nav (collapsible on mobile)
 ├ Dashboard         ← landing
 ├ Strategies
 ├ Backtest
 ├ Trades
 ├ Logs
 └ Settings

Bottom strip (mobile only)
 ├ Dashboard | Strategies | Trades | Kill (large red icon)
```

## 4. Screen-by-screen

### 4.1 Dashboard (the home screen)

The single most important screen. Optimised for "I just opened the app — what's happening?"

```
┌──────────────────────────────────────────────────────────────┐
│  AlgoTrader      ● Live · 3 running    🔔 2     [KILL ALL]   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │ Today's P&L    │  │ Open Positions │  │ Risk Used      │  │
│  │  +₹ 4,250      │  │ 2              │  │ 38% / day cap  │  │
│  │  +1.2%         │  │ ₹ 1.2L exposure│  │ ▓▓▓░░░░░░░     │  │
│  └────────────────┘  └────────────────┘  └────────────────┘  │
│                                                              │
│  Active Strategies                                           │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ ● ORB NIFTY   Live   +₹ 3,100   1 pos    [pause]    │    │
│  │ ● SMA Cross   Live   +₹ 1,150   1 pos    [pause]    │    │
│  │ ● Mean Rev    Paper  −₹ 200     0 pos    [pause]    │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  Recent Activity                                             │
│  10:32  ORB NIFTY  BUY 1 lot @ 22480.5      filled          │
│  10:32  ORB NIFTY  SL placed @ 22420                        │
│  09:55  SMA Cross  BUY 5 RELIANCE @ 2890    filled          │
│  09:30  Market opened — all strategies armed                │
│                                                              │
│  [ View all activity → ]                                     │
└──────────────────────────────────────────────────────────────┘
```

Key behaviours:
- All data live via WebSocket — no refresh button
- Tap any strategy row → strategy detail
- Tap "Risk Used" → risk dashboard with breakdown
- KILL ALL is red, large, top-right, **always visible**

### 4.2 Strategies

A list view; tap to drill into one strategy.

```
┌──────────────────────────────────────────────────────────────┐
│  Strategies                              [+ New instance]    │
├──────────────────────────────────────────────────────────────┤
│  Filter: [All  ▾]  Mode: [All  ▾]  Sort: [P&L  ▾]            │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ ORB NIFTY                                             │   │
│  │ Class: ORBStrategy v1.0.0   Mode: Live   Status: ●    │   │
│  │ Today: +₹ 3,100  ·  Trades: 2  ·  Win: 100%           │   │
│  │ Capital: ₹50,000  ·  Limit: ₹1,000 daily loss         │   │
│  │ [View]  [Pause]  [Kill]                               │   │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ SMA Cross — RELIANCE                                  │   │
│  │ ... (same shape) ...                                  │   │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

#### Strategy detail screen

Tabs: **Overview · Parameters · Trades · Logs · History**

Overview shows:
- Live equity curve (today)
- Current position, unrealised P&L
- Recent signals (with reasoning if logged)
- Key params (read-only summary)
- Big buttons: **Pause / Resume / Kill**, and **Switch mode** (Paper ↔ Live, with confirmation)

Parameters:
- Auto-rendered form from `params_schema`
- Save → restart strategy with new params (asks for confirmation if live)
- Diff view: "you're about to change `fast` from 10 to 12"

### 4.3 New strategy instance wizard

A 3-step modal:

1. **Pick strategy class** (from discovered list)
2. **Configure** (instruments, timeframe, capital, risk limits, parameters)
3. **Choose mode** (Backtest / Paper / Live) — Live requires 2FA

### 4.4 Backtest

```
┌──────────────────────────────────────────────────────────────┐
│  Backtest                                  [+ New backtest]  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Recent runs                                                 │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ SMA Cross  RELIANCE  2024-01..2024-12               │     │
│  │ Sharpe 1.42 · MaxDD 8.2% · CAGR 18% · Trades 47    │     │
│  │ [view] [compare]                                    │     │
│  └─────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

#### Backtest detail

- Big equity curve at top, with drawdown band shaded
- Metrics grid: total return, CAGR, Sharpe, Sortino, max DD, drawdown duration, win rate, profit factor, expectancy, trade count
- Trade list with filter (winners/losers/by month)
- Per-trade drilldown: entry/exit prices, P&L, slippage, signal context

#### Compare view

Side-by-side, two equity curves on the same chart, two metrics columns. For deciding "did changing `fast` from 10 to 12 help?"

### 4.5 Trades

A clean filterable table. Defaults to **today**.

- Filters: date range, strategy, broker, mode, side, status
- Click a row → drawer with:
    - Order timeline (submitted → accepted → filled)
    - Fills (multiple if partial)
    - Position impact at the time
    - Signal context (which strategy bar / tick triggered this)
    - Audit log entries for this order
- Export → CSV

### 4.6 Logs

Structured log search.

```
Filters:  [Strategy ▾]  [Level ▾]  [Time range ▾]   🔍 [search text]
─────────────────────────────────────────────────────────────────
10:32:14  INFO   ORB NIFTY     signal=long entry, range_high=22480
10:32:14  INFO   risk          approved: 1/3 daily losses, position OK
10:32:14  INFO   exec          submitting order client_id=abc123 to Zerodha
10:32:14  INFO   broker        accepted by Kite, broker_id=240509000123
10:32:15  INFO   broker        filled @ 22480.5, slippage 0
10:32:15  INFO   ORB NIFTY     entered, placing SL @ 22420
─────────────────────────────────────────────────────────────────
```

Each line: timestamp, level, source, structured message. Click a line for the full JSON.

### 4.7 Settings

Tabs:

- **Brokers** — list configured connections, status, "Add new"
- **Risk** — global limits + defaults for new strategies
- **Notifications** — Telegram, email, rules
- **Compliance** — show static IP, OPS limit, last token refresh, audit log export
- **Account** — change password, manage 2FA, sessions

## 5. The kill switch UX

Top-right button on every screen. Bright red. Hard to miss.

When clicked:

```
┌──────────────────────────────────────────────┐
│  KILL SWITCH                                 │
├──────────────────────────────────────────────┤
│  This will:                                  │
│   • Stop all 3 running strategies            │
│   • Cancel 2 open orders                     │
│   ☑ Also exit current positions at market    │
│                                              │
│  Enter 2FA code:  [______]                   │
│                                              │
│           [Cancel]    [KILL ALL]             │
└──────────────────────────────────────────────┘
```

After firing:
- All strategies → status `KILLED`, can't restart without manual action
- Banner across top: "Kill switch fired at 10:42:12 by user. [Review log]"
- Stays banner-active until acknowledged

## 6. Mobile considerations

Most pages collapse cleanly. Specific calls:

- Bottom nav strip with **5 items**: Dashboard, Strategies, Trades, Logs, Kill (large red)
- Tables → stacked cards
- Charts → simplified, with timeframe pills
- Modal flows → full-screen sheets
- "Run Backtest" is desktop-first; on mobile it's view-only

## 7. Confirmation patterns

| Action | Confirmation |
|---|---|
| Toggle dark mode, change timeframe | None |
| Save strategy parameters (paper/backtest) | Inline confirm |
| Save strategy parameters (live) | Modal, type strategy name |
| Switch to paper mode | Modal, simple confirm |
| Switch to live mode | Modal + 2FA |
| Delete a backtest run | Modal, simple confirm |
| Delete a strategy instance | Modal, type instance name |
| Kill switch | Modal + 2FA |
| Disconnect broker | Modal, type broker name |

## 8. Empty states

Important and often skipped:

- No strategies yet → big CTA: "Drop a `.py` file into `strategies/` then click Reload"
- No brokers connected → walkthrough: "1. Generate Kite Connect credentials at developers.kite.trade. 2. Add them to .env. 3. Click Connect."
- No backtests yet → "Pick a strategy and run your first backtest"
- No trades today → "Markets open at 09:15. Strategies are armed."

## 9. Accessibility

- Colour is never the only signal (icons + text always accompany)
- Keyboard navigation works for all primary flows
- Sufficient contrast (WCAG AA minimum)
- Screen-reader labels on all icon-only buttons

## 10. Out of scope (not yet)

- Drag-and-drop strategy builder
- Visual strategy editor (no-code)
- Charting at the level of TradingView
- Custom dashboard layouts
- Multi-screen workspaces

These are real wants. They're 6+ months away. v1 is functional, calm, and trustworthy.

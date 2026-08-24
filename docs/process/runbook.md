# Runbook

CP10's answer to "what do I actually do day to day." Written against what
the system genuinely does today, not aspirationally — every alert title
quoted below is copy-pasted from the code that sends it
(`xillion/observability/`, `xillion/core/risk.py`, `brokers/zerodha.py`,
`xillion/engine/strategy_engine.py`), so if the wording drifts, this doc is
what's stale, not the alert.

**Goal:** 3–6 hrs/week of your attention. The system tells you when it
needs more than that — everything else, you can genuinely ignore.

---

## The daily rhythm

- **~4:00pm IST**, a Daily digest arrives on Telegram: trades closed today,
  win/loss, P&L per instance, any instance stuck in `error` status, count
  of error/critical log lines, what's currently running.
  (`xillion/engine/digest_scheduler.py::run_daily_digest`)
- **Sunday ~6:00pm IST**, a Weekly digest — same shape, 7-day window.
- If the digest says **"No closed trades" + "Nothing currently running"**
  and you didn't expect that (market was open, instances should've been
  trading), that's the one digest outcome worth investigating rather than
  skimming — see [Auto start/stop looks stopped](#auto-startstop-looks-stopped) below.

If nothing else pages you between digests, there is nothing to do. That's
the point.

---

## What each alert means and what to do

| Alert title (exact) | Source | What it means | Action |
|---|---|---|---|
| `KILL SWITCH FIRED` | `xillion/core/risk.py` | Someone (you, or a script hitting the API) hit the kill switch. **All strategies halted.** | Confirm it was intentional. If not: someone/something has API access it shouldn't. Reset via Settings → Risk once safe. |
| `Zerodha connect failed` | `xillion/main.py` | Startup or the 6:15am daily token refresh couldn't connect. **No live prices, no order placement.** | Check `.env` credentials haven't expired/changed. Check Kite Connect subscription is still active. Reconnect via Settings → Brokers once fixed. |
| `Zerodha feed down` | `brokers/zerodha.py` | The tick WebSocket's own reconnect attempts (kiteconnect's internal retry) are exhausted. Ticks have stopped; strategies relying on `on_tick`/`on_bar` are now blind. | Reconnect Zerodha via Settings → Brokers. Don't wait for the 6:15am refresh if this happens mid-session — it won't self-heal until then. |
| `{task} restarting` | `xillion/observability/task_supervisor.py` | A background loop (tick broadcaster, a scheduler, log persistence) crashed and is being auto-restarted (up to 5 times / 10 min). | Usually nothing — this *is* the self-healing working. If it repeats across days, read the body's error and file it — it's a real bug, just not urgent. |
| `{task} gave up` | same | The task crashed 5+ times in 10 minutes and stopped retrying. | **Restart the process.** This is the one alert that always needs you — self-healing has an admitted limit and this is it. |
| `{instance}: failed to start` | `xillion/engine/strategy_engine.py` | A strategy's `on_start` raised. Instance is in `error` status, never began running. | Check Logs page filtered to that instance's name for the traceback. Usually a bad param or a missing instrument resolution. Fix, then Start again. |
| `{instance}: on_bar raised an exception` / `on_tick raised an exception` | same | The strategy crashed mid-session. Instance is now in `error` status and **has stopped processing new bars/ticks** — any position it was holding is untouched (still live at the broker), just no longer being managed by this strategy. | Check what it was holding (Dashboard → Positions, or the broker app directly) before deciding whether to just restart the instance or intervene on the position by hand first. |
| Daily/Weekly digest | `xillion/engine/digest_scheduler.py` | Not an alert — a status report. | Skim it. Only act if something in it surprises you. |

**Deliberately not covered above:** an order silently rejected by the
daily-loss gate (`RiskRejected(reason="...daily loss limit hit...")`) does
**not** currently fire a Telegram alert — it just shows up as a `REJECTED`
order in Trades/Journal. If a strategy seems to have "stopped trading" but
isn't in `error` status and there's no alert, check whether it's hit its
own daily loss limit before assuming something's broken.

---

## What to safely ignore

- A single `{task} restarting` alert that doesn't repeat — the point of
  self-healing is that a transient blip shouldn't need you.
- `zerodha: ticker reconnecting` in the Logs page (not a Telegram alert,
  logged at `warning`) — kiteconnect's own reconnect-in-progress message.
  Only `Zerodha feed down` (reconnect *exhausted*) needs action.
- An instance briefly in `idle` status right at 9:15am or 3:30pm IST — the
  market-hours auto start/stop scheduler
  (`xillion/engine/market_scheduler.py`) polls every 30s, so there's a
  small window where status hasn't caught up yet.

---

## When to intervene manually vs. let it self-heal

- **Let it self-heal:** any single `{task} restarting`. That's the system
  working as designed.
- **Intervene:** `{task} gave up`, `Zerodha feed down`,
  `Zerodha connect failed`, or any `{instance}: ... raised an exception`
  where the instance was holding a position. Real money or real data flow
  is affected in all four; none of these retry themselves.
- **Intervene immediately, don't wait for a digest:** `KILL SWITCH FIRED`
  that you didn't trigger.

---

## Where to look when something seems off but nothing alerted

1. **Logs page** — every `structlog` event app-wide, live-tailed and
   persisted for 24h (`xillion/observability/log_capture.py`). Filter by
   level (`err`/`warn`) first.
2. **Journal page** — per-signal/trade outcome classification
   (`stopped_out`/`target_hit`/`win`/`loss`), useful for "did this
   strategy's *logic* fail, not just the process."
3. **Dashboard** — current positions, today's P&L, running instances at a
   glance.
4. **Strategies page → instance card** — `status` and `last_error` per
   instance; the `Auto` badge shows whether market-hours auto start/stop is
   opted in for that instance.

---

## Auto start/stop looks stopped

If an instance with `Auto` enabled didn't start at market open:

1. Check the process didn't restart *during* market hours — the scheduler
   only fires on an open↔closed **transition** it actually observes; if the
   process was down at 9:15am and came up at, say, 10:00am while the
   market was already open, nothing "transitions" and it won't auto-start
   until the *next* close→open. Start it manually for that session.
2. Check `xillion/api/instances.py::start_instance_core`'s usual failure
   modes still apply here (plugin not loaded, broker not connected) — the
   scheduler calls the exact same code path as the Start button and logs
   the same rejection reason, just via `logger.warning` instead of an HTTP
   error, so check Logs rather than expecting a UI popup.

---

## Periodic maintenance (not urgent, but don't skip forever)

- **`system_log` grows until the 24h prune runs** (every 200 persisted log
  lines, not on a fixed clock — see `log_capture.py::_prune_old_logs`). No
  action needed under normal volume; if you ever see the Logs page
  timing out, that prune cadence is the first thing to check.
- **Restart the process occasionally**, even without a `gave up` alert —
  self-healing bounds crash-loops, it doesn't fix underlying resource
  leaks a long-running Python process might accumulate. Nothing currently
  measures that; a periodic restart is cheap insurance until it does.
- **Re-check `NSE_BSE_HOLIDAYS_2026`** (`xillion/core/market_calendar.py`)
  every December against NSE/BSE's official circular for next year — it's
  hand-maintained, not live-fetched.

---

## What this runbook does *not* cover

- Strategy-level decisions (when a strategy's *edge* looks broken, not just
  its process) — that's the Journal page + your own judgment, not a
  runbook rule.
- Anything under [go-live-checklist.md](go-live-checklist.md) — that's a
  one-time pre-launch gate, not an ongoing rhythm.

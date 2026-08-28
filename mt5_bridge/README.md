# MT5 bridge — Gold Lane B1 (Funding Pips)

Runs on **your own Mac** (per your choice — no VPS cost) and connects your
real MT5 terminal to the xillion backend. See
`brokers/mt5_funding_pips.py`'s module docstring in the main repo for why
this is a separate process instead of a normal broker plugin — short
version: MT5 only talks to Python running on the same machine as the
terminal, and xillion's backend (Render) can never be that machine.

**Important, and easy to get wrong:** the official `MetaTrader5` Python
package is a Windows binary. Under Wine on a Mac, that means **both the
terminal and the Python process running this bridge must run inside Wine**
— a native macOS Python (the one `python3` on your Mac normally points to)
physically cannot import this package at all. Everything below installs a
Windows Python *inside* Wine specifically for this reason.

I haven't been able to test this exact Wine setup myself (no Mac + MT5 +
Wine environment available to verify against) — the steps below are the
best-documented path, but if something doesn't match what you see, that's
the most likely place it diverges, not a sign you did something wrong.

---

## 1. Install Wine + the MT5 terminal

1. Install Wine on your Mac (e.g. `brew install --cask wine-stable`, or
   the Homebrew Cask for whichever Wine build you prefer).
2. Download the MetaTrader 5 setup file for Mac from MetaQuotes
   (metatrader5.com — "Download for macOS"). This is actually a
   Wine-wrapper installer, not a native Mac app.
3. Run it, let it install its bundled Wine prefix + the terminal.
4. Open the terminal, **File → Login to Trade Account**, enter your Funding
   Pips account number, password, and the exact broker server name Funding
   Pips emailed you. Leave it logged in.

## 2. Enable algorithmic trading in the terminal

**Tools → Options → Expert Advisors tab:**
- Check **"Allow Algorithmic Trading"**
- Check **"Allow WebRequest for listed URLs"** if you ever want the
  terminal itself to call out (not required for this bridge, which works
  the other way — Python calling MT5, not MT5 calling out)
- Click OK, confirm the **Algo Trading** button in the toolbar is
  green/enabled

## 3. Install a Windows Python inside the same Wine prefix

The MT5 installer's Wine prefix is usually at
`~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/`
(exact path varies by installer version — check where the MT5 installer
put things if this doesn't exist).

1. Download a Windows Python installer (e.g. python.org's `.exe`, a recent
   3.11 or 3.12 build — match whatever this repo's own Python version is
   close to, not strictly required to be identical).
2. Run it **through Wine**, pointed at the same prefix the terminal uses —
   typically: `WINEPREFIX=~/Library/Application\ Support/net.metaquotes.wine.metatrader5 wine python-3.xx.x.exe`
3. This gives you a `wine python.exe` you can invoke from Terminal.

## 4. Install this bridge's dependencies — using the Wine Python, not your Mac's

```bash
cd mt5_bridge
WINEPREFIX=~/Library/Application\ Support/net.metaquotes.wine.metatrader5 \
  wine python.exe -m pip install -r requirements.txt
```

## 5. Configure and run

```bash
cp .env.example .env
# edit .env: your xillion login, and XILLION_API_BASE (localhost for
# make dev, or your Render URL once deployed)

WINEPREFIX=~/Library/Application\ Support/net.metaquotes.wine.metatrader5 \
  wine python.exe bridge.py
```

You should see:
```
[bridge] logged in to http://localhost:8001/api as <you>
[bridge] MT5 terminal connected -- account <login>, balance <balance>
[bridge] polling http://localhost:8001/api/mt5-bridge every 2.0s for connection 'MT5 Funding Pips'
```

Leave this running (and the MT5 terminal open) the whole time you want Gold
strategies live/paper trading. If the terminal or this script stops, the
backend's `healthcheck()` on the MT5 broker connection will start failing
once ~2 minutes of silence passes — check **Settings → Brokers** in the
xillion UI for connection status.

## 6. On the xillion backend side

Set `MT5_FUNDING_PIPS_ENABLED=true` in `.env` (local) or the Render
dashboard's environment vars, then restart. The broker registers itself as
**"MT5 Funding Pips"** under Settings → Brokers — no credentials to enter
there, since your Funding Pips login never leaves this machine.

---

## Known limitations (v1, honestly scoped)

- **No historical data feed.** Backtesting Gold needs its own data source —
  not built yet. Live/paper trading works fully (real ticks from your real
  terminal); backtesting doesn't, until that's built separately.
- **Cancel only cancels a still-pending (unfilled) MT5 order.** Closing an
  already-open position happens through the strategy's normal exit logic
  (a fresh opposite-side order), not through the cancel path.
- **Reliability depends on your Mac staying awake and online**, and the
  Wine-wrapped terminal being genuinely stable over days/weeks — this is
  the tradeoff of the no-VPS-cost choice; if it turns out too flaky in
  practice, a small Windows VPS (~$5-10/mo) is the documented fallback.
- **Polling, not push** — real fills/prices show up within one poll
  interval (`XILLION_MT5_POLL_INTERVAL_SECONDS`, default 2s), not
  instantly. Fine for a swing-oriented Gold strategy; not suitable for
  anything latency-sensitive.

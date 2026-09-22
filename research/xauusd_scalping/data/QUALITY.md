# Data quality — XAUUSD M1, Dukascopy

**Honest status: a real but small sample, not the 3-year target.** Free
data acquisition for M1 gold hit real constraints in this environment —
documented below rather than glossed over.

## Source selection

- **HistData.com** (the spec's first suggestion): its free-download flow
  requires a per-page JavaScript-generated anti-bot token (`tk` form
  field, empty in the raw HTML, populated client-side) — not scriptable
  via plain HTTP without either browser automation (unavailable here) or
  reverse-engineering their token algorithm, which would cross into
  circumventing anti-scraping protection. **Not used.**
- **dukascopy-node**: needs npm/Node — not attempted, since the same data
  is reachable directly.
- **MetaTrader5 python package**: needs a running MT5 terminal — not
  reachable from this sandboxed environment (this is the same constraint
  the main xillion app's Gold Lane B1 already documents for its own MT5
  bridge).
- **Dukascopy's public tick feed** (`datafeed.dukascopy.com`, no API key
  — the same endpoint dukascopy-node itself wraps): **used.** Reachable,
  but aggressively and inconsistently rate-limited from this environment
  — a rapid retry returned HTTP 429, and the very next attempt after that
  timed out entirely. A 2.0-2.5s delay between hourly requests worked
  reliably in testing.

## What was actually downloaded

- **Symbol**: XAUUSD, M1 bars aggregated from real tick data.
- **Range attempted**: 2026-09-14 to 2026-09-17 (3 days).
- **Result**: 58 of 72 hours downloaded successfully, 2 genuinely empty
  (weekend), 12 failed (timeouts/429s during the run — the manifest
  (`xauusd/_manifest.json`) tracks these separately so a resumed run
  retries only the failed hours, not everything).
- **Bars produced**: 3,480 real M1 bars, `xauusd/XAUUSD_2026-09.parquet`.
- **Price sanity check**: bars range ~$4270-4335, consistent with gold's
  real spot price in this window (cross-checked against this session's
  earlier live Twelve Data quotes for XAUUSD, ~$4300-4370) — not just
  internally consistent, checked against an independent real source.
- **Price divisor verified empirically, not assumed**: Dukascopy's raw
  tick format encodes price as a scaled integer; decoding a real
  downloaded hour and checking the result against gold's actual price
  that week confirmed divisor=1000 (documented in
  `download_dukascopy.py`'s module docstring with the actual decoded
  numbers).
- **Gaps**: 5 gaps >5 minutes in the sample, all attributable to the 12
  failed hours creating holes — re-running the downloader (it's
  resumable, see `download_dukascopy.py`'s `--resume`-shaped manifest
  logic) against the same date range will backfill these on retry.

## Timezone

All timestamps are UTC throughout — Dukascopy's feed is UTC-native, and
the engine (`engine/cost_model.py`'s `session_for`) tags sessions directly
off UTC hour, matching the convention already established elsewhere in
this xillion project (see `xillion/core/market_calendar.py`'s `IST`
handling for the equivalent NSE-side convention). IST/broker-time display
is a P5 (live alert service) concern, not a backtest-data concern.

## What's NOT done — the honest gap

**3 years of continuous M1 history was not acquired in this session.** At
the safe request pace found (~2.5s/hour), a full 3-year backfill is
~26,280 hourly requests — multiple hours to a day+ of continuous running,
not something to run synchronously in one session. `download_dukascopy.py`
is built to be safely interrupted and resumed (the manifest persists
completed/empty/failed hours), so the actual path forward is: run it as a
long-lived background job over the following days, not a redesign. The
harness itself (below) does not depend on having 3 years — it's proven
correct against synthetic data (`tests/test_engine.py`), and P3's
walk-forward protocol can begin against whatever real coverage exists,
widening the window as the backfill progresses.

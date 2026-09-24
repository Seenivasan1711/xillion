"""
Measures a per-session spread profile for FX pairs from Dukascopy's own
bid/ask ticks, to replace the guessed table in engine/instruments.py.

Why Dukascopy as the proxy: Rakesh's FundingPips MT5 reading (2026-09-24,
16:56 server time, London/NY overlap) showed EURUSD 1pt / GBPUSD 0pt —
at or BELOW Dukascopy's interbank spread in liquid hours (2 / 6pts). So
Dukascopy's session profile is a measured, slightly conservative stand-in
for how the broker's spread moves through the day (Asia, rollover), which a
single MT5 reading can't show.

Output: median spread (points) per (session) and the 25th/75th percentile
of per-hour medians, printed as a table to paste into instruments.py.

    python measure_fx_spread_profile.py              # EURUSD + GBPUSD
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from engine.cost_model import session_for  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "download_dukascopy", Path(__file__).parent / "data" / "download_dukascopy.py"
)
dl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dl)

# Three ordinary mid-week days inside the XAUUSD/FX data window, no major
# holiday. Tue-Thu avoids Monday-open / Friday-close distortions.
SAMPLE_DAYS = [datetime(2026, 6, 9, tzinfo=UTC), datetime(2026, 6, 17, tzinfo=UTC), datetime(2026, 7, 8, tzinfo=UTC)]
POINT = 0.00001
DELAY = 3.0  # slow on purpose: the download chain is hitting the same host


def measure(symbol: str) -> dict:
    per_session: dict[str, list[float]] = {}
    with httpx.Client() as client:
        for day in SAMPLE_DAYS:
            for h in range(24):
                dt = day + timedelta(hours=h)
                try:
                    raw = dl._fetch_hour(client, symbol, dt)
                except Exception as exc:  # noqa: BLE001 -- a missing sample hour is fine, logged
                    print(f"  {symbol} {dt:%Y-%m-%d %H}h: skipped ({exc})", flush=True)
                    continue
                ticks = dl._parse_ticks(raw, dt, dl.PRICE_DIVISORS[symbol])
                if ticks:
                    med = statistics.median((t["ask"] - t["bid"]) / POINT for t in ticks)
                    per_session.setdefault(session_for(dt).value, []).append(med)
                time.sleep(DELAY)
    return per_session


def main() -> None:
    for symbol in ("EURUSD", "GBPUSD"):
        prof = measure(symbol)
        print(f"\n{symbol} spread by session (points; per-hour medians over {len(SAMPLE_DAYS)} days)")
        print(f"{'session':<20}{'hours':>6}{'p25':>8}{'median':>8}{'p75':>8}")
        for sess, vals in sorted(prof.items()):
            vals.sort()
            q = statistics.quantiles(vals, n=4) if len(vals) >= 4 else [vals[0], statistics.median(vals), vals[-1]]
            print(f"{sess:<20}{len(vals):>6}{q[0]:>8.1f}{statistics.median(vals):>8.1f}{q[2]:>8.1f}")


if __name__ == "__main__":
    main()

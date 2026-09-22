"""
Resumable downloader for Dukascopy's public historical tick feed
(datafeed.dukascopy.com), no API key needed -- the same public endpoint the
dukascopy-node library wraps. Decompresses each hour's LZMA .bi5 file,
parses Dukascopy's fixed 20-byte tick record format, aggregates to M1
OHLC bars, and appends to partitioned monthly parquet files under
data/xauusd/.

Tick record format (big-endian, 20 bytes): ms_offset(i32), ask_raw(i32),
bid_raw(i32), ask_vol(f32), bid_vol(f32). Price divisor for XAUUSD is 1000
-- verified empirically against a real downloaded hour (2024-01-01 01:00
UTC): ask_raw=2060405 / 1000 = 2060.405, matching gold's real spot price
that week (~$2040-2070/oz). Not assumed from documentation -- checked
against a real decoded file.

Rate limiting: Dukascopy returned HTTP 429 on a rapid retry during initial
testing (2026-09-22) and a bare timeout on the very next attempt after
that -- this endpoint is aggressively and inconsistently rate-limited from
a shared/sandboxed IP. DEFAULT_DELAY_SECONDS is deliberately conservative.
At this pace, a full 3-year backfill (~26,280 hourly files) takes multiple
hours to a day+ of continuous running -- this script is built to be safely
interruptible and resumable (a manifest tracks which hours are already
downloaded), not to complete a 3-year backfill synchronously in one run.

Usage:
    python download_dukascopy.py --symbol XAUUSD --from 2024-01-01 --to 2024-01-08
    python download_dukascopy.py --symbol XAUUSD --from 2021-01-01 --to 2024-01-01 --resume
"""

from __future__ import annotations

import argparse
import json
import lzma
import struct
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

DATA_DIR = Path(__file__).parent / "xauusd"
MANIFEST_PATH = DATA_DIR / "_manifest.json"
DEFAULT_DELAY_SECONDS = 2.5  # conservative pacing after observing 429s at higher rates
PRICE_DIVISOR = 1000  # verified empirically, see module docstring

DUKASCOPY_URL = "https://datafeed.dukascopy.com/datafeed/{symbol}/{year}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5"


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"completed_hours": [], "empty_hours": [], "failed_hours": []}


def _save_manifest(manifest: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


def _hour_key(symbol: str, dt: datetime) -> str:
    return f"{symbol}_{dt.strftime('%Y-%m-%dT%H')}"


_TRANSIENT_RETRY_ATTEMPTS = 3
_TRANSIENT_RETRY_BASE_DELAY = 3.0  # seconds, doubles each attempt


def _fetch_hour(client: httpx.Client, symbol: str, dt: datetime) -> bytes | None:
    """Dukascopy's month field is 0-indexed (January = 00).

    Retries transient network errors (found 2026-09-22 running a real
    6-month backfill: ~34% of hours failed on first attempt, and a direct
    diagnostic call reproduced a bare `ConnectTimeout` on the TLS
    handshake -- not a 429/rate-limit response, just flaky connectivity to
    this specific host from this environment. A short retry-with-backoff
    recovers most of these; a permanent block or real rate-limit would
    still exhaust all attempts and land in failed_hours for a later pass."""
    url = DUKASCOPY_URL.format(
        symbol=symbol, year=dt.year, month=dt.month - 1, day=dt.day, hour=dt.hour
    )
    last_exc: Exception | None = None
    for attempt in range(_TRANSIENT_RETRY_ATTEMPTS):
        try:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if resp.status_code == 404:
                return b""  # a genuinely empty hour (e.g. weekend) -- Dukascopy 404s these
            resp.raise_for_status()
            return resp.content
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            last_exc = exc
            if attempt < _TRANSIENT_RETRY_ATTEMPTS - 1:
                time.sleep(_TRANSIENT_RETRY_BASE_DELAY * (2**attempt))
    raise last_exc  # exhausted retries -- a real failure, not transient flakiness


def _parse_ticks(raw_bi5: bytes, hour_start: datetime) -> list[dict]:
    if not raw_bi5:
        return []
    decompressed = lzma.decompress(raw_bi5)
    n_records = len(decompressed) // 20
    ticks = []
    for i in range(n_records):
        chunk = decompressed[i * 20 : (i + 1) * 20]
        ms, ask_raw, bid_raw, ask_vol, bid_vol = struct.unpack(">iiiff", chunk)
        ts = hour_start + timedelta(milliseconds=ms)
        ticks.append(
            {
                "ts": ts,
                "ask": ask_raw / PRICE_DIVISOR,
                "bid": bid_raw / PRICE_DIVISOR,
                "ask_vol": ask_vol,
                "bid_vol": bid_vol,
            }
        )
    return ticks


def _ticks_to_m1_bars(ticks: list[dict]) -> pd.DataFrame:
    if not ticks:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(ticks)
    # Mid price for OHLC construction -- ask/bid spread is handled separately
    # by the cost model (see engine/cost_model.py), not baked into the bars.
    df["mid"] = (df["ask"] + df["bid"]) / 2
    df["volume"] = df["ask_vol"] + df["bid_vol"]
    df = df.set_index("ts")
    bars = df["mid"].resample("1min").ohlc()
    bars["volume"] = df["volume"].resample("1min").sum()
    bars = bars.dropna(subset=["open"])
    bars = bars.reset_index()
    return bars


def download_range(symbol: str, from_date: date, to_date: date, delay: float = DEFAULT_DELAY_SECONDS) -> None:
    manifest = _load_manifest()
    completed = set(manifest["completed_hours"])
    empty = set(manifest["empty_hours"])
    failed = set(manifest["failed_hours"])

    current = datetime.combine(from_date, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(to_date, datetime.min.time(), tzinfo=UTC)

    all_bars: list[pd.DataFrame] = []
    month_key = None

    with httpx.Client() as client:
        while current < end:
            key = _hour_key(symbol, current)
            if key in completed or key in empty:
                current += timedelta(hours=1)
                continue

            try:
                raw = _fetch_hour(client, symbol, current)
                ticks = _parse_ticks(raw, current)
                bars = _ticks_to_m1_bars(ticks)
                if bars.empty:
                    empty.add(key)
                else:
                    all_bars.append(bars)
                    completed.add(key)
                    failed.discard(key)
                print(f"{key}: {len(ticks)} ticks -> {len(bars)} M1 bars")
            except Exception as exc:
                print(f"{key}: FAILED - {exc}")
                failed.add(key)

            manifest["completed_hours"] = sorted(completed)
            manifest["empty_hours"] = sorted(empty)
            manifest["failed_hours"] = sorted(failed)
            _save_manifest(manifest)

            # Flush to a monthly parquet file when the month rolls over, so a
            # long-running/interrupted backfill doesn't lose already-fetched
            # bars sitting only in memory.
            this_month = current.strftime("%Y-%m")
            if month_key is not None and this_month != month_key and all_bars:
                _flush_month(symbol, month_key, all_bars)
                all_bars = []
            month_key = this_month

            current += timedelta(hours=1)
            time.sleep(delay)

    if all_bars:
        _flush_month(symbol, month_key, all_bars)


def _flush_month(symbol: str, month_key: str, bars_list: list[pd.DataFrame]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined = pd.concat(bars_list, ignore_index=True).drop_duplicates(subset="ts").sort_values("ts")
    out_path = DATA_DIR / f"{symbol}_{month_key}.parquet"
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        combined = pd.concat([existing, combined], ignore_index=True).drop_duplicates(subset="ts").sort_values("ts")
    combined.to_parquet(out_path, index=False)
    print(f"flushed {len(combined)} bars -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--from", dest="from_date", required=True, type=date.fromisoformat)
    parser.add_argument("--to", dest="to_date", required=True, type=date.fromisoformat)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    args = parser.parse_args()
    download_range(args.symbol, args.from_date, args.to_date, args.delay)

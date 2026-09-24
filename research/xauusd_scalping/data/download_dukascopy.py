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

DEFAULT_DELAY_SECONDS = 2.5  # conservative pacing after observing 429s at higher rates

# Per-symbol Dukascopy price divisors (raw bi5 int / divisor = price).
# XAUUSD 1000 verified empirically (module docstring); 5-digit FX pairs are
# 100000 -- verified on first download by checking the parsed price against
# the pair's known level. Mirrors engine/instruments.py (kept as a literal
# here so this script stays runnable standalone, without the engine package).
PRICE_DIVISORS = {"XAUUSD": 1000, "EURUSD": 100_000, "GBPUSD": 100_000}


def _data_dir(symbol: str) -> Path:
    # One directory AND one manifest per symbol: the manifest keys hours by
    # symbol already, but a shared file would be rewritten concurrently by
    # two downloaders running side by side (e.g. XAUUSD backfill + EURUSD).
    return Path(__file__).parent / symbol.lower()

DUKASCOPY_URL = "https://datafeed.dukascopy.com/datafeed/{symbol}/{year}/{month:02d}/{day:02d}/{hour:02d}h_ticks.bi5"


def _load_manifest(symbol: str) -> dict:
    path = _data_dir(symbol) / "_manifest.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"completed_hours": [], "empty_hours": [], "failed_hours": []}


def _save_manifest(symbol: str, manifest: dict) -> None:
    _data_dir(symbol).mkdir(parents=True, exist_ok=True)
    (_data_dir(symbol) / "_manifest.json").write_text(json.dumps(manifest, indent=2))


def _hour_key(symbol: str, dt: datetime) -> str:
    return f"{symbol}_{dt.strftime('%Y-%m-%dT%H')}"


_TRANSIENT_RETRY_ATTEMPTS = 3
_TRANSIENT_RETRY_BASE_DELAY = 3.0  # seconds, doubles each attempt
# Server-side throttling. Found 2026-09-24: with two downloaders running at
# once, Dukascopy answered whole TRADING days with 503 (e.g. EURUSD all 24h
# of 2026-03-10, XAUUSD all of 2024-01-18) -- previously recorded as failed
# on the first 503, never retried. Back off hard instead.
_THROTTLE_STATUSES = {429, 503}
_THROTTLE_RETRY_DELAYS = (15.0, 45.0, 120.0)  # seconds; ~3 min worst case per hour
# Throttle events seen by _fetch_hour since the last check -- download_range
# reads and resets this to adapt its own pacing (see _next_delay).
_throttle_events = 0
_MAX_DELAY_SECONDS = 60.0
_SUCCESSES_TO_SPEED_UP = 20


def _next_delay(delay: float, base: float, throttled: bool, streak: int) -> float:
    """AIMD pacing. Found 2026-09-24: after ~a day of requests Dukascopy
    throttled this IP to ~1 hour fetched per 2 minutes on a fixed 2.5s
    delay -- nearly every request burned the full 503 backoff. Double the
    delay on any throttle (cap 60s); ease back 1s after a clean streak."""
    if throttled:
        return min(delay * 2, _MAX_DELAY_SECONDS)
    if streak >= _SUCCESSES_TO_SPEED_UP:
        return max(base, delay - 1.0)
    return delay


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
    network_attempts = 0
    throttle_attempts = 0
    while True:
        try:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if resp.status_code == 404:
                return b""  # a genuinely empty hour (e.g. weekend) -- Dukascopy 404s these
            if resp.status_code in _THROTTLE_STATUSES and throttle_attempts < len(_THROTTLE_RETRY_DELAYS):
                global _throttle_events
                _throttle_events += 1
                time.sleep(_THROTTLE_RETRY_DELAYS[throttle_attempts])
                throttle_attempts += 1
                continue
            resp.raise_for_status()
            return resp.content
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            last_exc = exc
            network_attempts += 1
            if network_attempts >= _TRANSIENT_RETRY_ATTEMPTS:
                raise last_exc  # exhausted retries -- a real failure, not transient flakiness
            time.sleep(_TRANSIENT_RETRY_BASE_DELAY * (2 ** (network_attempts - 1)))


def _market_closed(dt: datetime) -> bool:
    """Saturday (UTC) only: FX and spot gold are shut all of Saturday in
    every DST regime, so these hours are skipped without a request. Friday
    evening / Sunday are NOT skipped -- the open/close hour moves with DST,
    and guessing it wrong would silently drop real bars."""
    return dt.weekday() == 5


def _reconcile_manifest(symbol: str, manifest: dict) -> int:
    """Drops 'completed' hours whose bars are not actually on disk.

    Found 2026-09-24: hours were marked completed in the manifest as soon as
    they were fetched, but bars only reach disk on the daily flush -- so a
    kill or crash mid-day left hours the manifest claimed existed and a
    re-run would never re-fetch. Returns how many hours were un-marked."""
    completed = set(manifest["completed_hours"])
    if not completed:
        return 0
    on_disk: set[str] = set()
    for f in _data_dir(symbol).glob(f"{symbol}_*.parquet"):
        ts = pd.read_parquet(f, columns=["ts"])["ts"]
        on_disk.update(_hour_key(symbol, t.to_pydatetime()) for t in ts.dt.floor("h").unique())
    missing = completed - on_disk
    manifest["completed_hours"] = sorted(completed & on_disk)
    return len(missing)


def _parse_ticks(raw_bi5: bytes, hour_start: datetime, divisor: int = PRICE_DIVISORS["XAUUSD"]) -> list[dict]:
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
                "ask": ask_raw / divisor,
                "bid": bid_raw / divisor,
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
    divisor = PRICE_DIVISORS[symbol]
    manifest = _load_manifest(symbol)
    dropped = _reconcile_manifest(symbol, manifest)
    if dropped:
        print(f"reconcile: {dropped} hours were marked completed but had no bars on disk -- will re-fetch")
        _save_manifest(symbol, manifest)
    completed = set(manifest["completed_hours"])
    # Fetched but not yet flushed to disk -- only promoted to `completed` in
    # the manifest after _flush_month succeeds (see _reconcile_manifest).
    pending: set[str] = set()
    empty = set(manifest["empty_hours"])
    failed = set(manifest["failed_hours"])

    current = datetime.combine(from_date, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(to_date, datetime.min.time(), tzinfo=UTC)

    all_bars: list[pd.DataFrame] = []
    base_delay = delay
    clean_streak = 0
    month_key = None
    day_key = None

    with httpx.Client() as client:
        while current < end:
            key = _hour_key(symbol, current)
            if key in completed or key in empty or _market_closed(current):
                current += timedelta(hours=1)
                continue

            try:
                raw = _fetch_hour(client, symbol, current)
                ticks = _parse_ticks(raw, current, divisor)
                bars = _ticks_to_m1_bars(ticks)
                if bars.empty:
                    empty.add(key)
                else:
                    all_bars.append(bars)
                    pending.add(key)
                    failed.discard(key)
                print(f"{key}: {len(ticks)} ticks -> {len(bars)} M1 bars")
            except Exception as exc:
                print(f"{key}: FAILED - {exc}")
                failed.add(key)

            manifest["completed_hours"] = sorted(completed)
            manifest["empty_hours"] = sorted(empty)
            manifest["failed_hours"] = sorted(failed)
            _save_manifest(symbol, manifest)

            # Flush at least once a day (not just monthly) -- found 2026-09-22
            # running a real 6-month backfill in the background: a mid-run
            # kill/crash before a month boundary lost 106 real fetched hours
            # that were only ever sitting in `all_bars`, while the manifest
            # still marked them "completed" (a re-run would have silently
            # skipped re-fetching them forever, believing the data existed).
            # Flushing daily caps the loss window at <=24h of work instead of
            # up to a full month, and a completed/empty hour is only ever
            # trusted in the manifest once its bars have actually reached
            # disk via _flush_month below.
            this_month = current.strftime("%Y-%m")
            this_day = current.strftime("%Y-%m-%d")
            should_flush = all_bars and (
                (month_key is not None and this_month != month_key)
                or (day_key is not None and this_day != day_key)
            )
            if should_flush:
                _flush_month(symbol, month_key, all_bars)
                all_bars = []
                completed |= pending
                pending = set()
                manifest["completed_hours"] = sorted(completed)
                _save_manifest(symbol, manifest)
            month_key = this_month
            day_key = this_day

            global _throttle_events
            throttled = _throttle_events > 0
            _throttle_events = 0
            clean_streak = 0 if throttled else clean_streak + 1
            new_delay = _next_delay(delay, base_delay, throttled, clean_streak)
            if new_delay != delay:
                print(f"pacing: delay {delay:.1f}s -> {new_delay:.1f}s ({'throttled' if throttled else 'clean streak'})")
                if not throttled:
                    clean_streak = 0
            delay = new_delay

            current += timedelta(hours=1)
            time.sleep(delay)

    if all_bars:
        _flush_month(symbol, month_key, all_bars)
        completed |= pending
        manifest["completed_hours"] = sorted(completed)
        _save_manifest(symbol, manifest)


def _flush_month(symbol: str, month_key: str, bars_list: list[pd.DataFrame]) -> None:
    data_dir = _data_dir(symbol)
    data_dir.mkdir(parents=True, exist_ok=True)
    combined = pd.concat(bars_list, ignore_index=True).drop_duplicates(subset="ts").sort_values("ts")
    out_path = data_dir / f"{symbol}_{month_key}.parquet"
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        combined = pd.concat([existing, combined], ignore_index=True).drop_duplicates(subset="ts").sort_values("ts")
    combined.to_parquet(out_path, index=False)
    print(f"flushed {len(combined)} bars -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD", choices=sorted(PRICE_DIVISORS))
    parser.add_argument("--from", dest="from_date", required=True, type=date.fromisoformat)
    parser.add_argument("--to", dest="to_date", required=True, type=date.fromisoformat)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    args = parser.parse_args()
    download_range(args.symbol, args.from_date, args.to_date, args.delay)

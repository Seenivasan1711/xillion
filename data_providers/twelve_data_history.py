"""
Twelve Data historical bars -- Gold Sweep-Reversal's backtest data source
(Stage 2). Plugs into the existing Data Providers -> Backfill ->
BarWarehouse -> Backtest pipeline the same way NSE Bhavcopy does for
NIFTY/BANKNIFTY, so the Backtest page needs no special-casing for Gold.

Free tier confirmed 2026-09-21 with a real query: 5-min XAUUSD bars are
available back to 2021 (2020 and earlier returns a clear "no data"
error, not silently empty data). This is the SAME free API key as
brokers/twelve_data_feed.py (the live alert feed), but a separate
credential slot here, matching every other provider's convention
(e.g. Alpha Vantage FX) -- paste the same key into Settings -> Data
Providers -> "Twelve Data (Gold History)".

Chunked fetching: Twelve Data's `outputsize` caps at 5000 bars/call,
which at 5-min bars is ~17 days -- a multi-month backtest range needs
several sequential requests. Paced at roughly 8/minute (the free tier's
own rate limit) rather than firing them all at once.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import structlog

from xillion.core.data_provider_base import DataProviderCapabilities, HistoricalDataProvider
from xillion.core.events import Bar

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.twelvedata.com"
_TIMEFRAME_TO_INTERVAL = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "1d": "1day",
}
_SYMBOL_MAP = {"XAUUSD": "XAU/USD"}
_MAX_BARS_PER_CALL = 5000
_MIN_SECONDS_BETWEEN_CALLS = 8.0  # free tier: 8 requests/minute


def _map_symbol(symbol: str) -> str:
    return _SYMBOL_MAP.get(symbol, symbol)


def _chunk_days(interval: str) -> int:
    """How many days of bars one call can hold, staying under
    _MAX_BARS_PER_CALL, for a market that's roughly continuously quoted
    (gold trades ~24x5, so this is a deliberately conservative estimate,
    not an exact bar count)."""
    minutes = {
        "1min": 1,
        "5min": 5,
        "15min": 15,
        "30min": 30,
        "1h": 60,
        "1day": 24 * 60,
    }[interval]
    bars_per_day = (24 * 60) / minutes
    return max(1, int(_MAX_BARS_PER_CALL / bars_per_day * 0.9))  # 10% headroom


class TwelveDataHistoryProvider(HistoricalDataProvider):
    name = "Twelve Data (Gold History)"
    version = "1.0.0"
    description = (
        "Free intraday/daily XAUUSD bars via Twelve Data, back to 2021 on the free "
        "tier -- Gold Sweep-Reversal's backtest data source. Needs a free API key "
        "from twelvedata.com (same key brokers/twelve_data_feed.py uses for live "
        "alerts, entered separately here)."
    )
    capabilities = DataProviderCapabilities(
        supports_equity=False,
        supports_futures=False,
        supports_options=False,
        supports_forex=True,
        requires_credentials=True,
        requires_broker=False,
        max_lookback_days=None,  # confirmed data back to 2021; no known hard cutoff since
    )
    credential_fields = [
        ("api_key", "Twelve Data API key", "text"),
    ]

    async def fetch_bars(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        from_date: date,
        to_date: date,
        *,
        instrument_type: str = "equity",
        credentials: dict | None = None,
        broker=None,
    ) -> list[Bar]:
        interval = _TIMEFRAME_TO_INTERVAL.get(timeframe)
        if interval is None:
            raise ValueError(f"Twelve Data (Gold History): unsupported timeframe {timeframe!r}")
        if credentials is None or not credentials.get("api_key"):
            raise ValueError(
                "Twelve Data (Gold History) needs an API key -- configure it under "
                "Settings -> Data Providers -> 'Twelve Data (Gold History)'."
            )
        api_key = credentials["api_key"]
        td_symbol = _map_symbol(symbol)

        chunk_days = _chunk_days(interval)
        out: list[Bar] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            chunk_start = from_date
            first_call = True
            while chunk_start <= to_date:
                chunk_end = min(chunk_start + timedelta(days=chunk_days), to_date)
                if not first_call:
                    await asyncio.sleep(_MIN_SECONDS_BETWEEN_CALLS)
                first_call = False

                resp = await client.get(
                    f"{_BASE_URL}/time_series",
                    params={
                        "symbol": td_symbol,
                        "interval": interval,
                        "start_date": chunk_start.isoformat(),
                        "end_date": (chunk_end + timedelta(days=1)).isoformat(),
                        "timezone": "UTC",
                        "apikey": api_key,
                    },
                )
                data = resp.json()
                if isinstance(data, dict) and data.get("status") == "error":
                    message = data.get("message", "")
                    if "no data" in message.lower():
                        # A gap (e.g. before 2021, or a genuinely quiet
                        # stretch) -- not fatal for the overall range.
                        logger.warning(
                            "twelve_data history: no data for chunk",
                            symbol=symbol,
                            start=chunk_start.isoformat(),
                            end=chunk_end.isoformat(),
                        )
                        chunk_start = chunk_end + timedelta(days=1)
                        continue
                    raise RuntimeError(f"Twelve Data history error: {message}")

                values = data.get("values") if isinstance(data, dict) else None
                if values:
                    for row in values:
                        ts = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S")
                        out.append(
                            Bar(
                                symbol=symbol,
                                timeframe=timeframe,
                                ts=ts.replace(tzinfo=UTC),
                                open=Decimal(row["open"]),
                                high=Decimal(row["high"]),
                                low=Decimal(row["low"]),
                                close=Decimal(row["close"]),
                                # Twelve Data's FX/commodity series carries no
                                # volume field -- 0, not faked.
                                volume=int(row.get("volume") or 0),
                            )
                        )
                chunk_start = chunk_end + timedelta(days=1)

        # Adjacent chunks' end/start dates overlap by design (a day
        # boundary, not a bar boundary) so no bar is ever missed at the
        # seam -- that legitimately produces a handful of duplicate (ts)
        # rows across chunks, deduped here rather than left for the
        # warehouse to deal with.
        by_ts = {b.ts: b for b in out}
        out = sorted(by_ts.values(), key=lambda b: b.ts)
        logger.info(
            "twelve_data history: fetched",
            symbol=symbol,
            timeframe=timeframe,
            bars=len(out),
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
        )
        return out

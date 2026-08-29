"""
Alpha Vantage FX_DAILY historical data provider -- Gold Lane B1's backup
backtest data source (2026-08-29), for when the MT5 bridge
(data_providers/mt5_bridge_history.py) isn't reachable (Mac asleep,
terminal closed, bridge process not running). Free tier, needs a free API
key from alphavantage.co/support/#api-key (no card, ~20 seconds to get).

Verified 2026-08-29 against Alpha Vantage's own docs
(alphavantage.co/documentation/) and a live query against the real API
(https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=XAU&
to_symbol=USD -- accepted the parameters and returned a real API response,
just gated on a real key rather than "demo"; confirmed the general
numbered-field response shape -- "1. open"/"2. high"/"3. low"/"4. close" --
against Alpha Vantage's TIME_SERIES_DAILY endpoint, which the demo key DOES
return real data for and which follows the documented-identical convention
every Alpha Vantage time-series endpoint uses).

**Honest, stated caveat, not hidden:** the exact top-level key name for
FX_DAILY's time series object ("Time Series FX (Daily)", per Alpha
Vantage's publicly documented convention for FX endpoints) and whether a
volume field is present at all (retail FX/CFD data generally has none,
unlike equities) were NOT independently confirmed against a real
authenticated response -- the demo key doesn't cover FX. Parsed
defensively below (tries the documented FX key name, falls back to the
equity-style key name, treats a missing volume as 0) rather than assumed
correct; if Alpha Vantage's real shape differs, this raises a clear error
instead of silently returning wrong data.

Only daily bars are supported -- Alpha Vantage's free tier doesn't include
intraday FX (that's a premium-tier feature per their own docs); this
provider raises a clear error for any other requested timeframe rather
than silently ignoring it.
"""

from datetime import date, datetime

import httpx
import structlog

from xillion.core.data_provider_base import DataProviderCapabilities, HistoricalDataProvider
from xillion.core.events import Bar

logger = structlog.get_logger(__name__)

_BASE_URL = "https://www.alphavantage.co/query"
_TIME_SERIES_KEYS = ("Time Series FX (Daily)", "Time Series (Daily)")


class AlphaVantageFXProvider(HistoricalDataProvider):
    name = "Alpha Vantage FX"
    version = "1.0.0"
    description = (
        "Free daily FX/Gold (XAUUSD) bars via Alpha Vantage's FX_DAILY endpoint -- backup "
        "for when the MT5 bridge isn't reachable. Needs a free API key from "
        "alphavantage.co/support/#api-key. Daily bars only; free tier is rate-limited "
        "(check alphavantage.co for current limits before a large backfill)."
    )
    capabilities = DataProviderCapabilities(
        supports_equity=False,
        supports_futures=False,
        supports_options=False,
        supports_forex=True,
        requires_credentials=True,
        requires_broker=False,
        max_lookback_days=None,  # outputsize=full -- Alpha Vantage's own full-history option
    )
    credential_fields = [
        ("api_key", "Alpha Vantage API key", "text"),
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
        if timeframe != "1d":
            raise ValueError(
                f"Alpha Vantage FX provider only supports daily ('1d') bars on the free "
                f"tier -- got {timeframe!r}. Intraday FX is a paid-tier feature."
            )
        if credentials is None or not credentials.get("api_key"):
            raise ValueError(
                "Alpha Vantage FX provider needs an API key -- configure it under "
                "Settings -> Data Providers."
            )
        if len(symbol) != 6:
            raise ValueError(
                f"symbol must be a 6-character pair like 'XAUUSD' (from+to symbol), got {symbol!r}"
            )
        from_symbol, to_symbol = symbol[:3], symbol[3:]

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                _BASE_URL,
                params={
                    "function": "FX_DAILY",
                    "from_symbol": from_symbol,
                    "to_symbol": to_symbol,
                    "outputsize": "full",
                    "apikey": credentials["api_key"],
                },
            )
            resp.raise_for_status()
            data = resp.json()

        if "Error Message" in data:
            raise RuntimeError(f"Alpha Vantage error: {data['Error Message']}")
        if "Note" in data or "Information" in data:
            # Alpha Vantage returns 200 with one of these keys (instead of
            # an HTTP error) for both rate-limit-exceeded and
            # invalid/missing-key cases -- must not be silently treated as
            # "zero bars available".
            raise RuntimeError(
                f"Alpha Vantage did not return data: {data.get('Note') or data.get('Information')}"
            )

        series = next((data[k] for k in _TIME_SERIES_KEYS if k in data), None)
        if series is None:
            raise RuntimeError(
                f"Alpha Vantage response had none of the expected time-series keys "
                f"{_TIME_SERIES_KEYS} -- got top-level keys {list(data.keys())}"
            )

        bars: list[Bar] = []
        for day_str, ohlc in series.items():
            day = date.fromisoformat(day_str)
            if not (from_date <= day <= to_date):
                continue
            bars.append(
                Bar(
                    symbol=symbol,
                    timeframe=timeframe,
                    ts=datetime.combine(day, datetime.min.time()),
                    open=_decimal(ohlc, "1. open"),
                    high=_decimal(ohlc, "2. high"),
                    low=_decimal(ohlc, "3. low"),
                    close=_decimal(ohlc, "4. close"),
                    volume=int(float(ohlc["5. volume"])) if "5. volume" in ohlc else 0,
                )
            )
        bars.sort(key=lambda b: b.ts)
        return bars


def _decimal(ohlc: dict, key: str):
    from decimal import Decimal

    return Decimal(ohlc[key])

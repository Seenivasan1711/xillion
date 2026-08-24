"""
Kite historical data provider. Doesn't manage its own credentials or auth --
reuses whichever Zerodha broker connection is already live (Settings →
Brokers), the same way the rest of xillion treats Zerodha. If you haven't
connected Zerodha as a broker, this provider isn't usable; connect it there
first, not here.

This is a thin adapter over Broker.get_history() (already implemented in
brokers/zerodha.py) -- see docs/13-quantman-parity-roadmap.md's data-provider
comparison table for the real limits: F&O history only goes back ~1 year,
OHLC candles only (no OI/IV/Greeks time series).
"""
from datetime import date, datetime

from xillion.core.data_provider_base import DataProviderCapabilities, HistoricalDataProvider
from xillion.core.events import Bar


class KiteHistoricalProvider(HistoricalDataProvider):
    name = "Zerodha Kite"
    version = "1.0.0"
    description = (
        "Kite Connect's Historical Data API (paid add-on, ~₹500/mo). Reuses "
        "your already-connected Zerodha broker session — connect Zerodha "
        "under Settings → Brokers first. F&O history ~1 year, equity/index "
        "5+ years; OHLC candles only, no OI/IV/Greeks."
    )
    capabilities = DataProviderCapabilities(
        supports_equity=True,
        supports_futures=True,
        supports_options=True,
        supports_forex=False,
        requires_credentials=False,  # reuses the Zerodha broker's own credentials
        requires_broker=True,
        max_lookback_days=365,
    )

    async def fetch_bars(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        from_date: date,
        to_date: date,
        *,
        instrument_type: str = "equity",
        credentials=None,
        broker=None,
    ) -> list[Bar]:
        if broker is None:
            raise ValueError(
                "Zerodha Kite provider needs a connected Zerodha broker — "
                "connect one under Settings → Brokers first."
            )

        qualified = f"{exchange}:{symbol}" if exchange else symbol
        from_ts = datetime.combine(from_date, datetime.min.time())
        to_ts = datetime.combine(to_date, datetime.max.time())
        bars: list[Bar] = await broker.get_history(qualified, timeframe, from_ts, to_ts)
        return bars

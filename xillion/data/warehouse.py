"""
BarWarehouse -- the "own the historical data" layer (CP2 / Goal #1).

Given a provider and a requested (symbol, exchange, timeframe, date range),
checks what's already cached in Postgres, fetches only the missing gap from
the provider, persists it, and returns the full requested range from the DB.
A second call for the same range costs zero provider HTTP calls.

For whole-file-bulk providers (NSE bhavcopy today), one fetch persists every
instrument traded that exchange/day -- so a later request for a *different*
symbol on an already-fetched day is also free. That's the "own our historical
data instead of paying a vendor per symbol" lever.
"""
from datetime import date, datetime, timedelta
from typing import Optional

import structlog

from xillion.core.data_provider_base import HistoricalDataProvider
from xillion.core.events import Bar
from xillion.data.coverage import WILDCARD_SYMBOL, BarCoverageRepository, compute_gaps
from xillion.data.repository import BarRepository

logger = structlog.get_logger(__name__)


class BarWarehouse:
    def __init__(self, bar_repo: BarRepository, coverage_repo: BarCoverageRepository) -> None:
        self._bars = bar_repo
        self._coverage = coverage_repo

    async def get_bars(
        self,
        provider: HistoricalDataProvider,
        symbol: str,
        exchange: str,
        timeframe: str,
        from_date: date,
        to_date: date,
        *,
        instrument_type: str = "option",
        credentials: Optional[dict] = None,
        broker=None,
        underlying_filter: Optional[set[str]] = None,
    ) -> list[Bar]:
        bulk = provider.capabilities.supports_whole_file_bulk
        if bulk and underlying_filter:
            # A filtered bulk run only persists a subset of the exchange's
            # instruments -- it must NOT share the unfiltered WILDCARD_SYMBOL
            # coverage key, or a later *unfiltered* request for this same
            # date range would wrongly think it's already fully covered and
            # skip re-fetching the underlyings this filter excluded.
            coverage_symbol = f"{WILDCARD_SYMBOL}:{','.join(sorted(underlying_filter))}"
        else:
            coverage_symbol = WILDCARD_SYMBOL if bulk else symbol

        existing = await self._coverage.get(coverage_symbol, exchange, timeframe, provider.name)
        gaps = compute_gaps(existing, from_date, to_date)

        for gap_from, gap_to in gaps:
            if bulk:
                fetched = await self._fetch_bulk_range(
                    provider, exchange, timeframe, gap_from, gap_to,
                    credentials=credentials, broker=broker, underlying_filter=underlying_filter,
                )
            else:
                fetched = await provider.fetch_bars(
                    symbol, exchange, timeframe, gap_from, gap_to,
                    instrument_type=instrument_type, credentials=credentials, broker=broker,
                )
            if fetched:
                await self._bars.upsert_bars(fetched, exchange=exchange)
            # Mark the gap covered even if the provider returned nothing for
            # it (e.g. a holiday-only range) -- otherwise it's re-fetched
            # forever. See BarCoverage docstring.
            await self._coverage.extend(coverage_symbol, exchange, timeframe, provider.name, gap_from, gap_to)
            logger.info(
                "warehouse gap fetched",
                provider=provider.name, symbol=coverage_symbol, exchange=exchange,
                timeframe=timeframe, gap_from=str(gap_from), gap_to=str(gap_to),
                bars_fetched=len(fetched),
            )

        from_ts = datetime.combine(from_date, datetime.min.time())
        to_ts = datetime.combine(to_date, datetime.max.time())
        return await self._bars.get_bars(symbol, timeframe, from_ts, to_ts, exchange=exchange)

    async def _fetch_bulk_range(
        self,
        provider: HistoricalDataProvider,
        exchange: str,
        timeframe: str,
        gap_from: date,
        gap_to: date,
        *,
        credentials: Optional[dict],
        broker,
        underlying_filter: Optional[set[str]] = None,
    ) -> list[Bar]:
        all_bars: list[Bar] = []
        day = gap_from
        while day <= gap_to:
            if day.weekday() < 5:
                day_bars = await provider.fetch_all_bars_for_day(
                    exchange, timeframe, day, credentials=credentials, broker=broker,
                    underlying_filter=underlying_filter,
                )
                all_bars.extend(day_bars)
            day += timedelta(days=1)
        return all_bars

"""
BarWarehouse: the CP2 "own the data" verification criterion --
run the same backtest twice, second run makes zero provider calls -- plus
the whole-file-bulk lever (one bhavcopy fetch covers every symbol that day).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from xillion.core.data_provider_base import DataProviderCapabilities, HistoricalDataProvider
from xillion.core.events import Bar
from xillion.data.coverage import BarCoverageRepository
from xillion.data.repository import BarRepository
from xillion.data.warehouse import BarWarehouse
from xillion.db.session import get_session_factory, init_db


class _CountingProvider(HistoricalDataProvider):
    name = "Counting Fake"
    capabilities = DataProviderCapabilities(requires_credentials=False)

    def __init__(self) -> None:
        self.fetch_calls: list[tuple] = []

    async def fetch_bars(
        self,
        symbol,
        exchange,
        timeframe,
        from_date,
        to_date,
        *,
        instrument_type="option",
        credentials=None,
        broker=None,
    ):
        self.fetch_calls.append((symbol, from_date, to_date))
        bars = []
        day = from_date
        while day <= to_date:
            if day.weekday() < 5:
                bars.append(
                    Bar(
                        symbol=symbol,
                        timeframe=timeframe,
                        ts=datetime.combine(day, datetime.min.time()),
                        open=Decimal(100),
                        high=Decimal(101),
                        low=Decimal(99),
                        close=Decimal(100),
                        volume=10,
                    )
                )
            day += timedelta(days=1)
        return bars


class _CountingBulkProvider(HistoricalDataProvider):
    name = "Counting Bulk Fake"
    capabilities = DataProviderCapabilities(
        requires_credentials=False, supports_whole_file_bulk=True
    )

    def __init__(self) -> None:
        self.bulk_calls: list[date] = []

    async def fetch_all_bars_for_day(
        self, exchange, timeframe, day, *, credentials=None, broker=None, underlying_filter=None
    ):
        self.bulk_calls.append(day)
        return [
            Bar(
                symbol="SYM_A",
                timeframe=timeframe,
                ts=datetime.combine(day, datetime.min.time()),
                open=Decimal(1),
                high=Decimal(1),
                low=Decimal(1),
                close=Decimal(1),
                volume=1,
            ),
            Bar(
                symbol="SYM_B",
                timeframe=timeframe,
                ts=datetime.combine(day, datetime.min.time()),
                open=Decimal(2),
                high=Decimal(2),
                low=Decimal(2),
                close=Decimal(2),
                volume=1,
            ),
        ]


def _warehouse() -> BarWarehouse:
    factory = get_session_factory()
    return BarWarehouse(BarRepository(factory), BarCoverageRepository(factory))


@pytest.mark.asyncio
async def test_second_request_for_same_range_makes_zero_provider_calls():
    await init_db()
    provider = _CountingProvider()
    warehouse = _warehouse()

    first = await warehouse.get_bars(
        provider, "WAREHOUSE_SYM_1", "NFO", "1d", date(2026, 8, 3), date(2026, 8, 7)
    )
    assert len(first) > 0
    assert len(provider.fetch_calls) == 1

    second = await warehouse.get_bars(
        provider, "WAREHOUSE_SYM_1", "NFO", "1d", date(2026, 8, 3), date(2026, 8, 7)
    )
    assert second == first
    assert len(provider.fetch_calls) == 1  # no new fetch on the second, identical request


@pytest.mark.asyncio
async def test_only_the_gap_is_fetched_on_a_widened_range():
    await init_db()
    provider = _CountingProvider()
    warehouse = _warehouse()

    await warehouse.get_bars(
        provider, "WAREHOUSE_SYM_2", "NFO", "1d", date(2026, 8, 3), date(2026, 8, 5)
    )
    assert len(provider.fetch_calls) == 1

    # Widen only at the tail -- the already-covered head must not be re-fetched.
    bars = await warehouse.get_bars(
        provider, "WAREHOUSE_SYM_2", "NFO", "1d", date(2026, 8, 3), date(2026, 8, 7)
    )
    assert len(provider.fetch_calls) == 2
    gap_call = provider.fetch_calls[1]
    assert gap_call[1] == date(2026, 8, 6)  # only the new tail was requested
    assert gap_call[2] == date(2026, 8, 7)
    assert len(bars) >= 3  # full requested range still returned from the DB


@pytest.mark.asyncio
async def test_whole_file_bulk_covers_every_symbol_from_one_fetch():
    await init_db()
    provider = _CountingBulkProvider()
    warehouse = _warehouse()

    a_bars = await warehouse.get_bars(
        provider, "SYM_A", "NFO", "1d", date(2026, 8, 10), date(2026, 8, 10)
    )
    assert len(a_bars) == 1
    assert len(provider.bulk_calls) == 1

    # A different symbol, same day: already persisted by the first bulk fetch.
    b_bars = await warehouse.get_bars(
        provider, "SYM_B", "NFO", "1d", date(2026, 8, 10), date(2026, 8, 10)
    )
    assert len(b_bars) == 1
    assert b_bars[0].close == Decimal(2)
    assert len(provider.bulk_calls) == 1  # no second network call


@pytest.mark.asyncio
async def test_filtered_bulk_fetch_uses_a_separate_coverage_key_from_unfiltered():
    """A real backfill scoped with underlying_filter only persists a subset
    of the exchange's contracts for that day -- it must not mark the
    unfiltered WILDCARD_SYMBOL coverage as covered too, or a later
    full-market request for the same date range would wrongly think it's
    already complete and silently skip re-fetching the excluded contracts."""
    await init_db()
    provider = _CountingBulkProvider()
    warehouse = _warehouse()

    filtered = await warehouse.get_bars(
        provider,
        "SYM_A",
        "NFO",
        "1d",
        date(2026, 8, 11),
        date(2026, 8, 11),
        underlying_filter={"SYM_A"},
    )
    assert len(filtered) == 1
    assert len(provider.bulk_calls) == 1

    # Same day, no filter this time -- must NOT be considered already
    # covered by the filtered fetch above, so it triggers its own bulk call.
    unfiltered = await warehouse.get_bars(
        provider,
        "SYM_B",
        "NFO",
        "1d",
        date(2026, 8, 11),
        date(2026, 8, 11),
    )
    assert len(unfiltered) == 1
    assert len(provider.bulk_calls) == 2  # a genuinely new fetch, not skipped


@pytest.mark.asyncio
async def test_gap_covering_a_holiday_is_not_refetched():
    """A weekday with no bar (holiday, or provider 404) must still count as
    covered once its containing range has been fetched -- otherwise every
    later backtest re-hits the provider for that one day forever."""
    await init_db()

    class _HolidayProvider(HistoricalDataProvider):
        name = "Holiday Fake"
        capabilities = DataProviderCapabilities(requires_credentials=False)

        def __init__(self):
            self.fetch_calls = []

        async def fetch_bars(self, symbol, exchange, timeframe, from_date, to_date, **kw):
            self.fetch_calls.append((from_date, to_date))
            return []  # simulates every day in range being a holiday

    provider = _HolidayProvider()
    warehouse = _warehouse()

    await warehouse.get_bars(
        provider, "HOLIDAY_SYM", "NFO", "1d", date(2026, 8, 3), date(2026, 8, 5)
    )
    await warehouse.get_bars(
        provider, "HOLIDAY_SYM", "NFO", "1d", date(2026, 8, 3), date(2026, 8, 5)
    )

    assert len(provider.fetch_calls) == 1

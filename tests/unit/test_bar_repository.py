"""BarRepository: bulk upsert round-trip and the exchange-filter bug fix.

Before CP2, get_bars() accepted an `exchange` parameter but never filtered
on it, so NSE and NFO rows for the same symbol/timeframe/ts could cross-
contaminate a query. This asserts the filter is now applied.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from xillion.core.events import Bar
from xillion.data.repository import BarRepository
from xillion.db.session import get_session_factory, init_db


def _bar(symbol: str, ts: datetime, close: str) -> Bar:
    return Bar(
        symbol=symbol,
        timeframe="1d",
        ts=ts,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1000,
    )


@pytest.mark.asyncio
async def test_upsert_and_get_round_trip():
    await init_db()
    repo = BarRepository(get_session_factory())

    ts = datetime(2026, 8, 1)
    await repo.upsert_bars([_bar("NIFTY_TEST_RT", ts, "100")], exchange="NFO")

    bars = await repo.get_bars(
        "NIFTY_TEST_RT", "1d", datetime(2026, 7, 1), datetime(2026, 9, 1), exchange="NFO"
    )
    assert len(bars) == 1
    assert bars[0].close == Decimal("100")


@pytest.mark.asyncio
async def test_upsert_is_idempotent_and_updates_on_conflict():
    await init_db()
    repo = BarRepository(get_session_factory())
    ts = datetime(2026, 8, 2)

    await repo.upsert_bars([_bar("NIFTY_TEST_CONFLICT", ts, "100")], exchange="NFO")
    await repo.upsert_bars(
        [_bar("NIFTY_TEST_CONFLICT", ts, "150")], exchange="NFO"
    )  # same PK, new close

    bars = await repo.get_bars(
        "NIFTY_TEST_CONFLICT", "1d", datetime(2026, 7, 1), datetime(2026, 9, 1), exchange="NFO"
    )
    assert len(bars) == 1  # not duplicated
    assert bars[0].close == Decimal("150")  # updated, not ignored


@pytest.mark.asyncio
async def test_get_bars_filters_by_exchange():
    await init_db()
    repo = BarRepository(get_session_factory())
    ts = datetime(2026, 8, 3)

    await repo.upsert_bars([_bar("SAME_SYMBOL_DIFF_EXCH", ts, "10")], exchange="NSE")
    await repo.upsert_bars([_bar("SAME_SYMBOL_DIFF_EXCH", ts, "20")], exchange="NFO")

    nse_bars = await repo.get_bars(
        "SAME_SYMBOL_DIFF_EXCH", "1d", datetime(2026, 7, 1), datetime(2026, 9, 1), exchange="NSE"
    )
    nfo_bars = await repo.get_bars(
        "SAME_SYMBOL_DIFF_EXCH", "1d", datetime(2026, 7, 1), datetime(2026, 9, 1), exchange="NFO"
    )

    assert len(nse_bars) == 1 and nse_bars[0].close == Decimal("10")
    assert len(nfo_bars) == 1 and nfo_bars[0].close == Decimal("20")


@pytest.mark.asyncio
async def test_upsert_empty_list_is_a_noop():
    await init_db()
    repo = BarRepository(get_session_factory())
    await repo.upsert_bars([], exchange="NFO")  # must not raise


@pytest.mark.asyncio
async def test_upsert_batches_large_row_counts():
    """A whole-file bhavcopy fetch persists hundreds-to-thousands of
    contracts in one call. SQLite's default build caps bound params per
    statement at 999 (9 cols/row -> ~111 rows) -- this failed against real
    data with 'too many SQL variables' before upsert_bars batched internally."""
    await init_db()
    repo = BarRepository(get_session_factory())
    ts = datetime(2026, 8, 1)
    bars = [
        _bar(f"BULK_SYM_{i}", ts, str(i)) for i in range(350)
    ]  # well over one SQLite statement's worth

    await repo.upsert_bars(bars, exchange="NFO")

    got = await repo.get_bars(
        "BULK_SYM_200", "1d", datetime(2026, 7, 1), datetime(2026, 9, 1), exchange="NFO"
    )
    assert len(got) == 1
    assert got[0].close == Decimal("200")

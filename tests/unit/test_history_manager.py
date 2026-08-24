"""
HistoryManager: in-memory cache with a DB fallback for lookback the cache
doesn't have yet -- the gap CP2 closes was that `repository` was accepted
in __init__ but never read from.
"""
from datetime import datetime
from decimal import Decimal

import pytest

from xillion.core.events import Bar
from xillion.data.history import HistoryManager
from xillion.data.repository import BarRepository
from xillion.db.session import get_session_factory, init_db


def _bar(ts: datetime, close: str) -> Bar:
    return Bar(
        symbol="HIST_SYM", timeframe="1d", ts=ts,
        open=Decimal(close), high=Decimal(close), low=Decimal(close),
        close=Decimal(close), volume=1,
    )


@pytest.mark.asyncio
async def test_falls_back_to_db_when_in_memory_cache_is_short():
    await init_db()
    repo = BarRepository(get_session_factory())
    db_bars = [_bar(datetime(2026, 8, d), str(d)) for d in range(1, 6)]  # 5 db bars
    await repo.upsert_bars(db_bars, exchange="NSE")

    live_bars = [_bar(datetime(2026, 8, 10), "10")]  # only 1 bar has arrived live so far
    manager = HistoryManager(repository=repo)
    manager.preload("HIST_SYM", "1d", live_bars)

    bars = await manager.get_bars("HIST_SYM", "1d", lookback=3)
    assert len(bars) == 3  # backfilled from DB to satisfy the requested lookback
    assert [b.close for b in bars] == [Decimal("4"), Decimal("5"), Decimal("10")]


@pytest.mark.asyncio
async def test_no_repository_means_in_memory_only_as_before():
    manager = HistoryManager(repository=None)
    manager.preload("HIST_SYM_2", "1d", [_bar(datetime(2026, 8, 1), "1")])
    bars = await manager.get_bars("HIST_SYM_2", "1d", lookback=50)
    assert len(bars) == 1  # no repo -> no backfill, same behaviour as pre-CP2


@pytest.mark.asyncio
async def test_sufficient_in_memory_cache_skips_db_entirely():
    await init_db()
    repo = BarRepository(get_session_factory())

    class _ExplodingRepo(BarRepository):
        async def get_bars(self, *a, **kw):
            raise AssertionError("DB should not be queried when the cache already has enough bars")

    manager = HistoryManager(repository=_ExplodingRepo(get_session_factory()))
    manager.preload("HIST_SYM_3", "1d", [_bar(datetime(2026, 8, d), str(d)) for d in range(1, 4)])

    bars = await manager.get_bars("HIST_SYM_3", "1d", lookback=2)
    assert len(bars) == 2

"""Tests for the tick-to-bar aggregator."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from xillion.core.events import Tick
from xillion.data.aggregator import TickAggregator, _bar_open_time


def _tick(symbol: str, price: float, ts: datetime) -> Tick:
    return Tick(symbol=symbol, ltp=Decimal(str(price)), ltt=ts)


def _ts(minute: int, second: int = 0) -> datetime:
    return datetime(2024, 1, 15, 9, minute, second, tzinfo=timezone.utc)


def test_bar_open_time_1m():
    ts = datetime(2024, 1, 15, 9, 15, 42, tzinfo=timezone.utc)
    result = _bar_open_time(ts, 60)
    assert result == datetime(2024, 1, 15, 9, 15, 0, tzinfo=timezone.utc)


def test_bar_open_time_5m():
    ts = datetime(2024, 1, 15, 9, 17, 30, tzinfo=timezone.utc)
    result = _bar_open_time(ts, 300)
    assert result == datetime(2024, 1, 15, 9, 15, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_single_bar_no_close():
    agg = TickAggregator()
    agg.subscribe("NIFTY", "1m")
    tick = _tick("NIFTY", 21000.0, _ts(15, 0))
    closed = await agg.on_tick(tick)
    assert closed == []  # first bar not yet closed


@pytest.mark.asyncio
async def test_bar_closes_on_next_period():
    agg = TickAggregator()
    agg.subscribe("NIFTY", "1m")

    # Ticks within the same minute
    closed = await agg.on_tick(_tick("NIFTY", 21000.0, _ts(15, 0)))
    assert closed == []
    closed = await agg.on_tick(_tick("NIFTY", 21050.0, _ts(15, 30)))
    assert closed == []

    # Next minute tick — should close the bar
    closed = await agg.on_tick(_tick("NIFTY", 21020.0, _ts(16, 0)))
    assert len(closed) == 1
    bar = closed[0]
    assert bar.symbol == "NIFTY"
    assert bar.timeframe == "1m"
    assert float(bar.open) == 21000.0
    assert float(bar.high) == 21050.0
    assert float(bar.close) == 21050.0


@pytest.mark.asyncio
async def test_multiple_timeframes():
    agg = TickAggregator()
    agg.subscribe("NIFTY", "1m")
    agg.subscribe("NIFTY", "5m")

    # Tick at 9:15:00 — starts both bars
    await agg.on_tick(_tick("NIFTY", 21000.0, _ts(15, 0)))
    # Tick at 9:16:00 — closes 1m bar, 5m still open
    closed = await agg.on_tick(_tick("NIFTY", 21100.0, _ts(16, 0)))
    one_min = [b for b in closed if b.timeframe == "1m"]
    five_min = [b for b in closed if b.timeframe == "5m"]
    assert len(one_min) == 1
    assert len(five_min) == 0

    # Tick at 9:20:00 — closes 5m bar
    closed = await agg.on_tick(_tick("NIFTY", 21200.0, _ts(20, 0)))
    five_min = [b for b in closed if b.timeframe == "5m"]
    assert len(five_min) == 1


@pytest.mark.asyncio
async def test_unknown_symbol_ignored():
    agg = TickAggregator()
    agg.subscribe("NIFTY", "1m")
    # Tick for a symbol we didn't subscribe to — silently no output
    closed = await agg.on_tick(_tick("BANKNIFTY", 45000.0, _ts(15, 0)))
    assert closed == []

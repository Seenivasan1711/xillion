"""
Tick -> Bar aggregation (CP9): nothing called MarketDataBus.publish_bar()
outside a backtest replay before this, so every on_bar-subscribed strategy
sat idle in live/paper mode forever, with no error. Bucketing, OHLC
correctness, and the cumulative-volume-delta handling (Zerodha ticks report
day-cumulative volume, not a per-tick trade size) are hand-checked here.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from xillion.core.events import Bar, Tick
from xillion.data.bar_aggregator import BarAggregator, _bucket_start
from xillion.data.bus import MarketDataBus

START = datetime(2026, 1, 1, 9, 15, 0, tzinfo=UTC)


def _tick(symbol: str, ltp: str, ts: datetime, volume: int | None = None) -> Tick:
    return Tick(symbol=symbol, ltp=Decimal(ltp), ltt=ts, volume=volume)


def test_bucket_start_rounds_down_to_the_timeframe():
    ts = datetime(2026, 1, 1, 9, 17, 43, tzinfo=UTC)
    assert _bucket_start(ts, 300) == datetime(2026, 1, 1, 9, 15, 0, tzinfo=UTC)  # 5m
    assert _bucket_start(ts, 60) == datetime(2026, 1, 1, 9, 17, 0, tzinfo=UTC)  # 1m


@pytest.mark.asyncio
async def test_no_bar_published_until_the_next_bucket_starts():
    bus = MarketDataBus()
    published: list[Bar] = []

    async def _capture(bar):
        published.append(bar)

    bus.subscribe_bars("NIFTY", "5m", _capture)
    agg = BarAggregator(bus)

    await agg.on_tick(_tick("NIFTY", "100", START))
    await agg.on_tick(_tick("NIFTY", "105", START + timedelta(minutes=2)))
    assert published == []  # still inside the same 5m bucket


@pytest.mark.asyncio
async def test_bar_publishes_with_correct_ohlc_when_bucket_closes():
    bus = MarketDataBus()
    published: list[Bar] = []

    async def _capture(bar):
        published.append(bar)

    bus.subscribe_bars("NIFTY", "5m", _capture)
    agg = BarAggregator(bus)

    await agg.on_tick(_tick("NIFTY", "100", START))  # open
    await agg.on_tick(_tick("NIFTY", "110", START + timedelta(minutes=1)))  # high
    await agg.on_tick(_tick("NIFTY", "95", START + timedelta(minutes=2)))  # low
    await agg.on_tick(_tick("NIFTY", "105", START + timedelta(minutes=4)))  # close (still bucket 1)
    await agg.on_tick(
        _tick("NIFTY", "200", START + timedelta(minutes=5))
    )  # first tick of bucket 2 -> closes bucket 1

    assert len(published) == 1
    bar = published[0]
    assert bar.ts == START
    assert bar.open == Decimal("100")
    assert bar.high == Decimal("110")
    assert bar.low == Decimal("95")
    assert bar.close == Decimal("105")


@pytest.mark.asyncio
async def test_volume_is_the_cumulative_delta_not_a_sum_of_raw_ticks():
    """Zerodha-shaped ticks report cumulative day volume, not a per-tick
    trade size -- summing raw tick.volume would wildly overstate a bar."""
    bus = MarketDataBus()
    published: list[Bar] = []

    async def _capture(bar):
        published.append(bar)

    bus.subscribe_bars("NIFTY", "5m", _capture)
    agg = BarAggregator(bus)

    await agg.on_tick(_tick("NIFTY", "100", START, volume=10_000))
    await agg.on_tick(_tick("NIFTY", "101", START + timedelta(minutes=1), volume=10_500))
    await agg.on_tick(_tick("NIFTY", "102", START + timedelta(minutes=2), volume=11_200))
    await agg.on_tick(
        _tick("NIFTY", "103", START + timedelta(minutes=5), volume=12_000)
    )  # closes bucket 1

    assert published[0].volume == 1200  # 11200 - 10000, not 10000+10500+11200


@pytest.mark.asyncio
async def test_multiple_timeframes_for_the_same_symbol_aggregate_independently():
    bus = MarketDataBus()
    published_5m: list[Bar] = []
    published_15m: list[Bar] = []

    async def _capture_5m(bar):
        published_5m.append(bar)

    async def _capture_15m(bar):
        published_15m.append(bar)

    bus.subscribe_bars("NIFTY", "5m", _capture_5m)
    bus.subscribe_bars("NIFTY", "15m", _capture_15m)
    agg = BarAggregator(bus)

    await agg.on_tick(_tick("NIFTY", "100", START))
    await agg.on_tick(
        _tick("NIFTY", "101", START + timedelta(minutes=6))
    )  # closes the 5m bucket only
    assert len(published_5m) == 1
    assert len(published_15m) == 0

    await agg.on_tick(
        _tick("NIFTY", "102", START + timedelta(minutes=16))
    )  # closes the 15m bucket too
    assert len(published_15m) == 1


@pytest.mark.asyncio
async def test_unrecognised_timeframe_is_skipped_not_guessed():
    bus = MarketDataBus()
    published = []

    async def _capture(bar):
        published.append(bar)

    bus.subscribe_bars("NIFTY", "7m", _capture)  # not a real supported timeframe
    agg = BarAggregator(bus)

    await agg.on_tick(_tick("NIFTY", "100", START))
    await agg.on_tick(_tick("NIFTY", "101", START + timedelta(minutes=10)))
    assert published == []  # no crash, no fabricated bar


@pytest.mark.asyncio
async def test_a_late_out_of_order_tick_does_not_reopen_a_closed_bucket():
    bus = MarketDataBus()
    published: list[Bar] = []

    async def _capture(bar):
        published.append(bar)

    bus.subscribe_bars("NIFTY", "5m", _capture)
    agg = BarAggregator(bus)

    await agg.on_tick(_tick("NIFTY", "100", START))
    await agg.on_tick(
        _tick("NIFTY", "200", START + timedelta(minutes=5))
    )  # closes bucket 1 at close=100
    await agg.on_tick(
        _tick("NIFTY", "999", START + timedelta(minutes=1))
    )  # late tick, belongs to bucket 1

    assert published[0].close == Decimal("100")  # unaffected by the late tick
    assert len(published) == 1  # the late tick did not trigger a second publish

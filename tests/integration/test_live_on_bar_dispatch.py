"""
End-to-end: a live/paper on_bar strategy actually receives bars (CP9).
Before BarAggregator + the ctx.history() wiring in StrategyRunner._handle_bar,
an on_bar-subscribed strategy correctly subscribed via subscribe_bars() but
nothing published a single bar in live/paper mode -- it would sit idle
forever with no error. This drives the exact path _tick_broadcaster uses:
ticks in, BarAggregator.on_tick(), bus fan-out to the runner.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from brokers._dummy import DummyBroker
from xillion.core.events import Bar, Tick
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy
from xillion.data.bar_aggregator import BarAggregator
from xillion.data.bus import MarketDataBus
from xillion.engine.strategy_engine import StrategyEngine

START = datetime(2026, 1, 1, 9, 15, 0, tzinfo=UTC)


class _RecordingOnBarStrategy(Strategy):
    name = "Live On Bar Dispatch Test Strategy"
    timeframe = "5m"
    instruments = ["NIFTY"]

    def __init__(self):
        self.bars_seen: list[Bar] = []
        self.history_lengths: list[int] = []

    async def on_bar(self, bar, ctx):
        self.bars_seen.append(bar)
        history = await ctx.history(bar.symbol, bar.timeframe, lookback=10)
        self.history_lengths.append(len(history))


def _tick(symbol: str, ltp: str, ts: datetime) -> Tick:
    return Tick(symbol=symbol, ltp=Decimal(ltp), ltt=ts)


@pytest.mark.asyncio
async def test_on_bar_fires_for_a_live_instance_via_real_ticks(monkeypatch):
    monkeypatch.setattr("xillion.engine.strategy_engine.is_market_open", lambda *a, **k: True)
    from xillion.db.session import init_db

    await init_db()

    registry = PluginRegistry()
    registry.strategies[_RecordingOnBarStrategy.name] = _RecordingOnBarStrategy
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)

    runner = await engine.spawn(
        instance_id="live-onbar-test-1",
        strategy_name=_RecordingOnBarStrategy.name,
        broker=DummyBroker(),
        instruments=["NIFTY"],
        timeframe="5m",
        capital=Decimal("100000"),
        params={},
        mode="paper",
    )
    strategy: _RecordingOnBarStrategy = runner._strategy
    aggregator = BarAggregator(bus)

    # Simulate what _tick_broadcaster does in main.py: publish_tick + feed
    # the same tick to the aggregator.
    async def _drive(ltp: str, ts: datetime):
        tick = _tick("NIFTY", ltp, ts)
        await bus.publish_tick(tick)
        await aggregator.on_tick(tick)

    assert strategy.bars_seen == []  # nothing yet -- still inside the first bucket

    await _drive("100", START)
    await _drive("105", START + timedelta(minutes=2))
    await _drive("110", START + timedelta(minutes=6))  # closes the first 5m bucket

    assert len(strategy.bars_seen) == 1
    assert strategy.bars_seen[0].close == Decimal("105")
    assert strategy.history_lengths == [
        1
    ]  # the bar that just closed is already visible to ctx.history()

    await _drive("120", START + timedelta(minutes=11))  # closes the second bucket
    assert len(strategy.bars_seen) == 2
    assert strategy.history_lengths == [1, 2]  # history accumulates across bars

"""
Integration test: alert-mode strategy dispatch is gated on market hours.
Uses a monkeypatched clock so the test is deterministic regardless of when
it actually runs.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from brokers._dummy import DummyBroker
from xillion.core.events import Tick
from xillion.core.plugin_loader import PluginLoader
from xillion.core.risk import RiskManager
from xillion.data.bus import MarketDataBus
from xillion.db.session import init_db
from xillion.engine.strategy_engine import StrategyEngine


class _FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def alert(self, title: str, body: str, severity: str = "info") -> None:
        self.messages.append((title, body))


def _tick(symbol: str, ltp: float) -> Tick:
    return Tick(symbol=symbol, ltp=Decimal(str(ltp)), ltt=datetime.now(UTC))


@pytest.mark.asyncio
async def test_alert_mode_skips_dispatch_when_market_closed(monkeypatch):
    monkeypatch.setattr("xillion.engine.strategy_engine.is_market_open", lambda *a, **k: False)
    await init_db()

    loader = PluginLoader()
    registry = await loader.discover_all()

    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)

    notifier = _FakeNotifier()
    instance_id = "test-market-closed"

    await engine.spawn(
        instance_id=instance_id,
        strategy_name="Nifty Spot Alert",
        broker=DummyBroker(),
        instruments=["NIFTY 50"],
        timeframe="1m",
        capital=Decimal("100000"),
        params={"level": 25000.0, "direction": "above"},
        mode="alert",
        notifier=notifier,
    )

    # Would cross the level if the market were open -- but it's gated closed.
    await bus.publish_tick(_tick("NIFTY 50", 24990.0))
    await bus.publish_tick(_tick("NIFTY 50", 25010.0))

    assert notifier.messages == []
    await engine.stop_instance(instance_id)


@pytest.mark.asyncio
async def test_paper_mode_is_not_gated_by_market_hours(monkeypatch):
    """Only alert mode is gated in this phase (paper/live gating is a
    documented fast-follow, not required yet) -- confirm paper mode still
    dispatches ticks even when the market-hours check would say closed."""
    monkeypatch.setattr("xillion.engine.strategy_engine.is_market_open", lambda *a, **k: False)
    await init_db()

    loader = PluginLoader()
    registry = await loader.discover_all()

    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)

    broker = DummyBroker()
    instance_id = "test-paper-not-gated"

    await engine.spawn(
        instance_id=instance_id,
        strategy_name="Nifty Spot Alert",
        broker=broker,
        instruments=["NIFTY 50"],
        timeframe="1m",
        capital=Decimal("100000"),
        params={"level": 25000.0, "direction": "above"},
        mode="paper",
    )

    await bus.publish_tick(_tick("NIFTY 50", 24990.0))
    await bus.publish_tick(_tick("NIFTY 50", 25010.0))

    # Paper mode routes through ExecutionRouter -> broker.place_order.
    assert any(call == "place_order" for call, _ in broker.calls)
    await engine.stop_instance(instance_id)

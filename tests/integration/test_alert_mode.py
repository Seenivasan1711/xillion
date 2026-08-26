"""
Integration test: alert mode's entire signal pipeline -- tick in -> strategy
crosses a level -> Telegram notify + SignalLog row -- with zero order
execution. Validates Phases 4 + 6 together, independent of the options
instrument resolver (Phases 1-3).
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from brokers._dummy import DummyBroker
from xillion.core.events import Tick
from xillion.core.plugin_loader import PluginLoader
from xillion.core.risk import RiskManager
from xillion.data.bus import MarketDataBus
from xillion.db.models import OrderRecord, SignalLog
from xillion.db.session import get_session_factory, init_db
from xillion.engine.strategy_engine import StrategyEngine


class _FakeNotifier:
    """Stand-in for TelegramNotifier -- records calls instead of hitting the network."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def alert(self, title: str, body: str, severity: str = "info") -> None:
        self.messages.append((title, body))


def _tick(symbol: str, ltp: float) -> Tick:
    return Tick(symbol=symbol, ltp=Decimal(str(ltp)), ltt=datetime.now(UTC))


@pytest.mark.asyncio
async def test_alert_mode_notifies_and_logs_without_placing_orders(monkeypatch):
    # This test exercises the signal pipeline itself, not market-hours
    # gating (which has its own dedicated test) -- pin the clock open so the
    # test doesn't flake depending on when it happens to run.
    monkeypatch.setattr("xillion.engine.strategy_engine.is_market_open", lambda *a, **k: True)
    await init_db()

    loader = PluginLoader()
    registry = await loader.discover_all()
    assert "Nifty Spot Alert" in registry.strategies

    bus = MarketDataBus()
    risk = RiskManager()
    engine = StrategyEngine(bus=bus, risk_manager=risk)
    engine.set_registry(registry)

    notifier = _FakeNotifier()
    broker = DummyBroker()
    instance_id = "test-alert-instance"

    await engine.spawn(
        instance_id=instance_id,
        strategy_name="Nifty Spot Alert",
        broker=broker,
        instruments=["NIFTY 50"],
        timeframe="1m",
        capital=Decimal("100000"),
        params={"level": 25000.0, "direction": "above"},
        mode="alert",
        notifier=notifier,
    )

    # Baseline tick below the level, then a tick that crosses above it.
    await bus.publish_tick(_tick("NIFTY 50", 24990.0))
    await bus.publish_tick(_tick("NIFTY 50", 25010.0))

    # Zero calls reached the broker's place_order -- the entire point of alert mode.
    assert not any(call == "place_order" for call, _ in broker.calls)

    # Telegram got exactly one alert.
    assert len(notifier.messages) == 1
    title, body = notifier.messages[0]
    assert "BUY" in body

    # A SignalLog row was written; no OrderRecord (alert mode persists no orders/fills).
    async with get_session_factory()() as session:
        signals = (
            (
                await session.execute(
                    select(SignalLog).where(SignalLog.strategy_instance_id == instance_id)
                )
            )
            .scalars()
            .all()
        )
        orders = (
            (
                await session.execute(
                    select(OrderRecord).where(OrderRecord.strategy_instance_id == instance_id)
                )
            )
            .scalars()
            .all()
        )

    assert len(signals) == 1
    assert signals[0].notified is True
    assert signals[0].mode == "alert"
    assert signals[0].side == "BUY"
    assert orders == []

    await engine.stop_instance(instance_id)


@pytest.mark.asyncio
async def test_alert_mode_ignores_wrong_direction_cross(monkeypatch):
    monkeypatch.setattr("xillion.engine.strategy_engine.is_market_open", lambda *a, **k: True)
    await init_db()

    loader = PluginLoader()
    registry = await loader.discover_all()

    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)

    notifier = _FakeNotifier()
    instance_id = "test-alert-instance-2"

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

    # Crosses DOWN through the level -- strategy is only watching for "above".
    await bus.publish_tick(_tick("NIFTY 50", 25010.0))
    await bus.publish_tick(_tick("NIFTY 50", 24990.0))

    assert notifier.messages == []
    await engine.stop_instance(instance_id)

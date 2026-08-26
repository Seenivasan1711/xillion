"""
Self-failure alerting (CP9): a strategy crashing mid-session with real
orders possibly still open must not be a silent event the user only
discovers by happening to check the UI or Logs page. Before this, on_start/
on_bar/on_tick exceptions were caught and logged but never notified, and
on_tick specifically didn't even set status="error"/last_error the way
on_bar and on_start already did.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from brokers._dummy import DummyBroker
from xillion.core.events import Bar, Tick
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy
from xillion.data.bus import MarketDataBus
from xillion.engine.strategy_engine import StrategyEngine

NOW = datetime(2026, 1, 1, 9, 20, 0, tzinfo=UTC)


class _FakeNotifier:
    def __init__(self):
        self.alerts: list[dict] = []

    async def alert(self, title, body, severity="info"):
        self.alerts.append({"title": title, "body": body, "severity": severity})


class _RaisingOnBarStrategy(Strategy):
    name = "Raising On Bar Test Strategy"
    timeframe = "5m"
    instruments = ["NIFTY"]

    async def on_bar(self, bar, ctx):
        raise RuntimeError("bad math")


class _RaisingOnTickStrategy(Strategy):
    name = "Raising On Tick Test Strategy"
    timeframe = "5m"
    instruments = ["NIFTY"]

    async def on_tick(self, tick, ctx):
        raise RuntimeError("bad tick handling")


class _RaisingOnStartStrategy(Strategy):
    name = "Raising On Start Test Strategy"
    timeframe = "5m"
    instruments = ["NIFTY"]

    async def on_start(self, ctx):
        raise RuntimeError("bad setup")


async def _spawn(strategy_cls, instance_id, notifier):
    registry = PluginRegistry()
    registry.strategies[strategy_cls.name] = strategy_cls
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)
    runner = await engine.spawn(
        instance_id=instance_id,
        strategy_name=strategy_cls.name,
        broker=DummyBroker(),
        instruments=["NIFTY"],
        timeframe="5m",
        capital=Decimal("100000"),
        params={},
        mode="paper",
        notifier=notifier,
    )
    return runner, bus


async def _settle():
    import asyncio

    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_on_bar_exception_alerts_and_sets_error_status():
    notifier = _FakeNotifier()
    runner, bus = await _spawn(_RaisingOnBarStrategy, "fail-onbar-1", notifier)

    await bus.publish_bar(
        Bar(
            symbol="NIFTY",
            timeframe="5m",
            ts=NOW,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=0,
        )
    )
    await _settle()

    assert runner.status == "error"
    assert "bad math" in runner.last_error
    assert len(notifier.alerts) == 1
    assert notifier.alerts[0]["severity"] == "error"
    assert "on_bar" in notifier.alerts[0]["title"]


@pytest.mark.asyncio
async def test_on_tick_exception_alerts_and_sets_error_status():
    """Before this, on_tick's except block logged the failure but never
    set status/last_error the way on_bar and on_start already did -- a
    tick-only strategy crashing looked identical to one running fine."""
    notifier = _FakeNotifier()
    runner, bus = await _spawn(_RaisingOnTickStrategy, "fail-ontick-1", notifier)

    await bus.publish_tick(Tick(symbol="NIFTY", ltp=Decimal("100"), ltt=NOW))
    await _settle()

    assert runner.status == "error"
    assert "bad tick handling" in runner.last_error
    assert len(notifier.alerts) == 1
    assert "on_tick" in notifier.alerts[0]["title"]


@pytest.mark.asyncio
async def test_on_start_exception_alerts():
    notifier = _FakeNotifier()
    registry = PluginRegistry()
    registry.strategies[_RaisingOnStartStrategy.name] = _RaisingOnStartStrategy
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)

    runner = await engine.spawn(
        instance_id="fail-onstart-1",
        strategy_name=_RaisingOnStartStrategy.name,
        broker=DummyBroker(),
        instruments=["NIFTY"],
        timeframe="5m",
        capital=Decimal("100000"),
        params={},
        mode="paper",
        notifier=notifier,
    )
    await _settle()

    assert runner.status == "error"
    assert "bad setup" in runner.last_error
    assert len(notifier.alerts) == 1
    assert "failed to start" in notifier.alerts[0]["title"]


@pytest.mark.asyncio
async def test_no_notifier_configured_does_not_crash_on_failure():
    """Telegram not set up yet must not prevent the error status/logging
    from happening -- notification is a bonus on top, not a dependency."""
    runner, bus = await _spawn(_RaisingOnBarStrategy, "fail-onbar-no-notifier", None)

    await bus.publish_bar(
        Bar(
            symbol="NIFTY",
            timeframe="5m",
            ts=NOW,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=0,
        )
    )
    await _settle()

    assert runner.status == "error"
    assert "bad math" in runner.last_error

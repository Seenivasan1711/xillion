"""
Pre-trade AI confidence hook (CP8): runs as a background task AFTER the
alert already fired and the signal_log row already persisted -- a slow (or
down) confidence backend must never delay the alert. Measured against a
real local model (qwen3:8b via Ollama): 30-60s+ per call is realistic, far
too slow to sit in the critical path of a live alert.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from brokers._dummy import DummyBroker
from xillion.core.events import Side, Tick
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy, StrategyContext
from xillion.data.bus import MarketDataBus
from xillion.db.models import SignalLog
from xillion.db.session import get_session_factory, init_db
from xillion.engine.strategy_engine import StrategyEngine


class _FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def alert(self, title: str, body: str, severity: str = "info") -> None:
        self.messages.append((title, body))


class _EntryStrategy(Strategy):
    name = "AI Confidence Hook Test Strategy"
    timeframe = "1m"
    instruments = ["NIFTY 50"]

    async def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        if not ctx.state.get("entered"):
            ctx.state["entered"] = True
            await ctx.alert_entry(
                tick.symbol,
                Side.BUY,
                price=tick.ltp,
                target=tick.ltp + 100,
                stop_loss=tick.ltp - 50,
                tag="hook_test",
            )


def _tick(symbol: str, ltp: float) -> Tick:
    return Tick(symbol=symbol, ltp=Decimal(str(ltp)), ltt=datetime.now(UTC))


@pytest.mark.asyncio
async def test_alert_fires_and_persists_before_confidence_resolves(monkeypatch):
    """A slow confidence backend must not delay the alert or the initial
    signal_log write -- both must already be done by the time publish_tick
    returns, well before the (here, artificially slow) confidence call
    finishes."""
    monkeypatch.setattr("xillion.engine.strategy_engine.is_market_open", lambda *a, **k: True)
    await init_db()

    resolved = asyncio.Event()

    async def _slow_confidence(*args, **kwargs):
        await asyncio.sleep(0.2)  # stands in for a real 30-60s local-model call
        resolved.set()
        return 77.0

    monkeypatch.setattr("xillion.notifications.ai_confidence.get_confidence", _slow_confidence)

    registry = PluginRegistry()
    registry.strategies[_EntryStrategy.name] = _EntryStrategy
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)

    notifier = _FakeNotifier()
    instance_id = "test-ai-confidence-hook"
    await engine.spawn(
        instance_id=instance_id,
        strategy_name=_EntryStrategy.name,
        broker=DummyBroker(),
        instruments=["NIFTY 50"],
        timeframe="1m",
        capital=Decimal("100000"),
        params={},
        mode="alert",
        notifier=notifier,
    )

    await bus.publish_tick(_tick("NIFTY 50", 25000.0))

    # By the time publish_tick returns, the alert must already be sent and
    # the row persisted -- the confidence call (0.2s) has not resolved yet.
    assert not resolved.is_set()
    assert len(notifier.messages) == 1

    async with get_session_factory()() as session:
        row = (
            await session.execute(
                select(SignalLog).where(SignalLog.strategy_instance_id == instance_id)
            )
        ).scalar_one()
    assert row.ai_confidence is None  # not yet -- the background task hasn't finished

    await asyncio.wait_for(resolved.wait(), timeout=2)
    await asyncio.sleep(0.05)  # let the background task's DB write land

    async with get_session_factory()() as session:
        row = (
            await session.execute(
                select(SignalLog).where(SignalLog.strategy_instance_id == instance_id)
            )
        ).scalar_one()
    assert row.ai_confidence == 77.0  # filled in after the fact


@pytest.mark.asyncio
async def test_exit_signals_never_trigger_a_confidence_lookup(monkeypatch):
    monkeypatch.setattr("xillion.engine.strategy_engine.is_market_open", lambda *a, **k: True)
    await init_db()

    called = {"n": 0}

    async def _counting_confidence(*args, **kwargs):
        called["n"] += 1
        return 50.0

    monkeypatch.setattr("xillion.notifications.ai_confidence.get_confidence", _counting_confidence)

    class _EntryThenExit(Strategy):
        name = "AI Confidence Exit Test Strategy"
        timeframe = "1m"
        instruments = ["NIFTY 50"]

        async def on_tick(self, tick, ctx):
            step = ctx.state.get("step", 0)
            if step == 0:
                await ctx.alert_entry(tick.symbol, Side.BUY, price=tick.ltp, tag="t")
            elif step == 1:
                await ctx.alert_exit(tick.symbol, Side.SELL, price=tick.ltp, tag="t")
            ctx.state["step"] = step + 1

    registry = PluginRegistry()
    registry.strategies[_EntryThenExit.name] = _EntryThenExit
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)

    await engine.spawn(
        instance_id="test-ai-confidence-exit",
        strategy_name=_EntryThenExit.name,
        broker=DummyBroker(),
        instruments=["NIFTY 50"],
        timeframe="1m",
        capital=Decimal("100000"),
        params={},
        mode="alert",
    )

    await bus.publish_tick(_tick("NIFTY 50", 25000.0))  # ENTER -> 1 lookup
    await asyncio.sleep(0.05)
    await bus.publish_tick(_tick("NIFTY 50", 25100.0))  # EXIT -> no lookup
    await asyncio.sleep(0.05)

    assert called["n"] == 1

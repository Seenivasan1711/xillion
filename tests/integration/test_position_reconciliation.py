"""
Position reconciliation on startup (CP9, "hard gate before real money"):
self._positions is always constructed empty, and PositionRecord in the DB
is only ever written when a trade CLOSES -- never while one is still open.
Before this, restarting a live instance always believed it was flat, even
with real money sitting in a real open position.
"""

from decimal import Decimal

import pytest

from brokers._dummy import DummyBroker
from xillion.core.events import Position
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy
from xillion.data.bus import MarketDataBus
from xillion.engine.strategy_engine import StrategyEngine


class _NoopStrategy(Strategy):
    name = "Reconciliation Test Strategy"
    timeframe = "5m"
    instruments = ["NIFTY", "BANKNIFTY"]


def _broker_position(symbol: str, qty: int, avg: str = "100") -> Position:
    return Position(
        symbol=symbol,
        quantity=qty,
        avg_price=Decimal(avg),
        realised_pnl=Decimal("0"),
        unrealised_pnl=Decimal("0"),
        last_price=Decimal(avg),
    )


async def _spawn(mode: str, broker, instance_id: str):
    registry = PluginRegistry()
    registry.strategies[_NoopStrategy.name] = _NoopStrategy
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)
    return await engine.spawn(
        instance_id=instance_id,
        strategy_name=_NoopStrategy.name,
        broker=broker,
        instruments=["NIFTY", "BANKNIFTY"],
        timeframe="5m",
        capital=Decimal("100000"),
        params={},
        mode=mode,
    )


@pytest.mark.asyncio
async def test_live_instance_restores_a_real_open_position_on_start(monkeypatch):
    broker = DummyBroker()
    monkeypatch.setattr(
        broker, "get_positions", lambda: _async_list([_broker_position("NIFTY", 65)])
    )

    runner = await _spawn("live", broker, "reconcile-test-1")

    pos = runner._ctx.position("NIFTY")
    assert pos is not None
    assert pos.quantity == 65
    assert pos.avg_price == Decimal("100")


@pytest.mark.asyncio
async def test_symbols_outside_the_instance_configuration_are_ignored(monkeypatch):
    """The broker account may hold positions from a totally different
    instance or manual trade -- only this instance's configured symbols
    should be attributed to it."""
    broker = DummyBroker()
    monkeypatch.setattr(
        broker,
        "get_positions",
        lambda: _async_list(
            [
                _broker_position("NIFTY", 65),
                _broker_position("RELIANCE", 10),  # not in this instance's instruments
            ]
        ),
    )

    runner = await _spawn("live", broker, "reconcile-test-2")

    assert runner._ctx.position("NIFTY") is not None
    assert runner._ctx.position("RELIANCE") is None


@pytest.mark.asyncio
async def test_zero_quantity_broker_positions_are_not_restored(monkeypatch):
    broker = DummyBroker()
    monkeypatch.setattr(
        broker, "get_positions", lambda: _async_list([_broker_position("NIFTY", 0)])
    )

    runner = await _spawn("live", broker, "reconcile-test-3")

    assert runner._ctx.position("NIFTY") is None


@pytest.mark.asyncio
async def test_paper_mode_does_not_reconcile_even_if_broker_has_positions(monkeypatch):
    """Paper mode's own simulated positions correctly start flat on
    restart -- reconciling from a real broker here would be wrong."""
    broker = DummyBroker()
    monkeypatch.setattr(
        broker, "get_positions", lambda: _async_list([_broker_position("NIFTY", 65)])
    )

    runner = await _spawn("paper", broker, "reconcile-test-4")

    assert runner._ctx.position("NIFTY") is None


@pytest.mark.asyncio
async def test_broker_fetch_failure_does_not_crash_startup(monkeypatch):
    broker = DummyBroker()

    async def _boom():
        raise RuntimeError("Kite API down")

    monkeypatch.setattr(broker, "get_positions", _boom)

    runner = await _spawn("live", broker, "reconcile-test-5")

    assert runner.status == "running"  # startup still succeeded
    assert runner._ctx.position("NIFTY") is None  # just nothing restored


async def _async_list(items):
    return items

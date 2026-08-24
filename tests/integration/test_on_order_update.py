"""
Strategy.on_order_update (CP9): declared in the base class since before this
session, never called by anything. Fires as a fire-and-forget task right
after place_order()'s own order-state transition, same pattern as
on_trade_close.
"""
import asyncio
from decimal import Decimal

import pytest

from brokers._dummy import DummyBroker
from xillion.core.events import Order, OrderRequest, OrderType, Side
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy
from xillion.data.bus import MarketDataBus
from xillion.engine.strategy_engine import StrategyEngine


class _OrderUpdateTrackingStrategy(Strategy):
    name = "Order Update Test Strategy"
    timeframe = "1m"
    instruments = ["NIFTY"]

    def __init__(self):
        self.updates: list[Order] = []

    async def on_order_update(self, order, ctx):
        self.updates.append(order)


class _RaisingOnOrderUpdateStrategy(Strategy):
    name = "Raising Order Update Test Strategy"
    timeframe = "1m"
    instruments = ["NIFTY"]

    async def on_order_update(self, order, ctx):
        raise RuntimeError("boom")


async def _spawn(strategy_cls, instance_id):
    registry = PluginRegistry()
    registry.strategies[strategy_cls.name] = strategy_cls
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)
    runner = await engine.spawn(
        instance_id=instance_id, strategy_name=strategy_cls.name,
        broker=DummyBroker(), instruments=["NIFTY"], timeframe="1m",
        capital=Decimal("100000"), params={}, mode="paper",
    )
    return runner


@pytest.mark.asyncio
async def test_on_order_update_is_called_after_a_real_order():
    runner = await _spawn(_OrderUpdateTrackingStrategy, "order-update-test-1")
    strategy: _OrderUpdateTrackingStrategy = runner._strategy

    await runner._ctx.place_order(OrderRequest(
        symbol="NIFTY", side=Side.BUY, quantity=1, order_type=OrderType.MARKET,
    ))
    await asyncio.sleep(0.05)  # let the fire-and-forget task run

    assert len(strategy.updates) == 1
    assert strategy.updates[0].symbol == "NIFTY"
    assert strategy.updates[0].side == Side.BUY


@pytest.mark.asyncio
async def test_a_raising_on_order_update_does_not_break_place_order():
    runner = await _spawn(_RaisingOnOrderUpdateStrategy, "order-update-test-2")

    order = await runner._ctx.place_order(OrderRequest(
        symbol="NIFTY", side=Side.BUY, quantity=1, order_type=OrderType.MARKET,
    ))
    await asyncio.sleep(0.05)  # let the raising task run and be caught

    assert order.status.value != "REJECTED"  # place_order itself succeeded regardless


@pytest.mark.asyncio
async def test_alert_mode_never_calls_on_order_update():
    """Alert mode never reaches ExecutionRouter.submit() at all -- there's
    no real order to report a status change for."""
    registry = PluginRegistry()
    registry.strategies[_OrderUpdateTrackingStrategy.name] = _OrderUpdateTrackingStrategy
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)
    runner = await engine.spawn(
        instance_id="order-update-test-3", strategy_name=_OrderUpdateTrackingStrategy.name,
        broker=DummyBroker(), instruments=["NIFTY"], timeframe="1m",
        capital=Decimal("100000"), params={}, mode="alert",
    )
    strategy: _OrderUpdateTrackingStrategy = runner._strategy

    await runner._ctx.place_order(OrderRequest(
        symbol="NIFTY", side=Side.BUY, quantity=1, order_type=OrderType.MARKET,
    ))
    await asyncio.sleep(0.05)

    assert strategy.updates == []

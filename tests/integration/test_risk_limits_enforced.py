"""
Per-strategy risk limits, spawn to enforcement (CP9): StrategyEngine.spawn()
previously never read risk_limits at all -- a strategy instance's
"max open positions" / "daily loss %" configured in the UI had zero effect
on real orders, silently, forever. This drives a real spawned instance
through ctx.buy() and confirms the configured limit actually rejects.
"""

from decimal import Decimal

import pytest

from brokers._dummy import DummyBroker
from xillion.core.events import OrderRequest, OrderType, Position, Side
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy
from xillion.data.bus import MarketDataBus
from xillion.engine.strategy_engine import StrategyEngine


class _AlwaysBuyStrategy(Strategy):
    name = "Risk Limits Test Strategy"
    timeframe = "1m"
    instruments = ["NIFTY"]

    async def on_bar(self, bar, ctx):
        await ctx.buy(bar.symbol, 1)


async def _spawn(engine, bus, instance_id, risk_limits, capital="100000"):
    registry = PluginRegistry()
    registry.strategies[_AlwaysBuyStrategy.name] = _AlwaysBuyStrategy
    engine.set_registry(registry)
    return await engine.spawn(
        instance_id=instance_id,
        strategy_name=_AlwaysBuyStrategy.name,
        broker=DummyBroker(),
        instruments=["NIFTY"],
        timeframe="1m",
        capital=Decimal(capital),
        params={},
        mode="paper",
        risk_limits=risk_limits,
    )


@pytest.mark.asyncio
async def test_max_open_positions_from_ui_config_actually_rejects_real_orders():
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    runner = await _spawn(engine, bus, "risk-limit-test-1", {"max_open_positions": 1})

    # First buy opens a position -- approved.
    order1 = await runner._ctx.place_order(
        OrderRequest(
            symbol="NIFTY",
            side=Side.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
        )
    )
    assert order1.status.value != "REJECTED"

    # Simulate the position now being open so a second BUY on a DIFFERENT
    # symbol (a genuinely new position, not adding to the first) hits the cap.
    runner._ctx._positions["NIFTY"] = Position(
        symbol="NIFTY",
        quantity=1,
        avg_price=Decimal("100"),
        realised_pnl=Decimal("0"),
        unrealised_pnl=Decimal("0"),
        last_price=Decimal("100"),
    )
    order2 = await runner._ctx.place_order(
        OrderRequest(
            symbol="BANKNIFTY",
            side=Side.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
        )
    )
    assert order2.status.value == "REJECTED"
    assert "positions" in order2.rejection_reason


@pytest.mark.asyncio
async def test_hot_reload_tightens_limit_on_a_running_instance_without_restart():
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    runner = await _spawn(engine, bus, "risk-limit-test-2", {"max_open_positions": 5})

    runner._ctx._positions["NIFTY"] = Position(
        symbol="NIFTY",
        quantity=1,
        avg_price=Decimal("100"),
        realised_pnl=Decimal("0"),
        unrealised_pnl=Decimal("0"),
        last_price=Decimal("100"),
    )
    # Under the original limit (5) -- approved.
    order1 = await runner._ctx.place_order(
        OrderRequest(
            symbol="BANKNIFTY",
            side=Side.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
        )
    )
    assert order1.status.value != "REJECTED"

    # Hot-reload to a tighter limit -- no restart, no re-spawn.
    updated = engine.update_risk_config("risk-limit-test-2", {"max_open_positions": 1})
    assert updated is True

    order2 = await runner._ctx.place_order(
        OrderRequest(
            symbol="FINNIFTY",
            side=Side.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
        )
    )
    assert order2.status.value == "REJECTED"
    assert "positions" in order2.rejection_reason


@pytest.mark.asyncio
async def test_update_risk_config_on_a_non_running_instance_returns_false():
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    assert engine.update_risk_config("does-not-exist", {"max_open_positions": 1}) is False

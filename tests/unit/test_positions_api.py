"""
GET /positions (CP7, pulled forward from CP9): aggregates open positions
across every running strategy instance. Tested via the pure
collect_open_positions() function against a real spawned runner (DummyBroker
fills instantly), not a hand-built fake position object.
"""

from datetime import UTC

import pytest

from brokers._dummy import DummyBroker
from xillion.api.positions import collect_open_positions
from xillion.core.events import Tick
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy
from xillion.data.bus import MarketDataBus
from xillion.db.session import init_db
from xillion.engine.strategy_engine import StrategyEngine


class _BuyOnceStrategy(Strategy):
    name = "Positions Test Strategy"
    timeframe = "1m"
    instruments = ["POS_TEST_SYM"]

    async def on_tick(self, tick, ctx):
        if not ctx.state.get("bought"):
            ctx.state["bought"] = True
            await ctx.buy(tick.symbol, 5)


def _tick(symbol: str, ltp: str):
    from datetime import datetime
    from decimal import Decimal

    return Tick(symbol=symbol, ltp=Decimal(ltp), ltt=datetime.now(UTC))


@pytest.mark.asyncio
async def test_collect_open_positions_reflects_a_real_fill(monkeypatch):
    monkeypatch.setattr("xillion.engine.strategy_engine.is_market_open", lambda *a, **k: True)
    await init_db()

    registry = PluginRegistry()
    registry.strategies[_BuyOnceStrategy.name] = _BuyOnceStrategy

    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)

    from decimal import Decimal

    await engine.spawn(
        instance_id="positions-test-instance",
        strategy_name=_BuyOnceStrategy.name,
        broker=DummyBroker(default_fill_price=Decimal("250")),
        instruments=["POS_TEST_SYM"],
        timeframe="1m",
        capital=Decimal("100000"),
        params={},
        mode="paper",
        instance_name="Positions Test Instance",
    )

    await bus.publish_tick(_tick("POS_TEST_SYM", "250"))

    positions = collect_open_positions(engine.list_runners())
    assert len(positions) == 1
    p = positions[0]
    assert p["symbol"] == "POS_TEST_SYM"
    assert p["quantity"] == 5
    assert p["avg_price"] == 250.0
    assert p["instance_id"] == "positions-test-instance"
    assert p["instance_name"] == "Positions Test Instance"


@pytest.mark.asyncio
async def test_collect_open_positions_excludes_flat_symbols():
    class _EmptyRunner:
        _instance_id = "x"

        class _ctx:
            _instance_name = "x"
            mode = "paper"

            @staticmethod
            def positions():
                return []

    assert collect_open_positions([_EmptyRunner()]) == []

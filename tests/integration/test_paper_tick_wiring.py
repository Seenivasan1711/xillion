"""
Paper mode's live tick feed used to be hardcoded to the literal string
"Zerodha Primary" in start_instance_core, a second Zerodha-only spot the
CP15 broker-selection fix (_resolve_broker) didn't cover -- a Dhan-only
instance never got ticks even once Dhan was connected. Also fixes two
follow-on gaps found while wiring the real fix: PaperBroker.on_tick was
never actually subscribed to the bus (the wiring _resolve_broker sketched
was dead code), and DhanBroker's tick_stream() was never drained by a
broadcaster the way ZerodhaBroker's is.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI

from xillion.core.events import Tick
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy
from xillion.data.bus import MarketDataBus
from xillion.db.models import BrokerClass, BrokerConnection, StrategyClass, StrategyInstance
from xillion.db.session import get_session_factory, init_db
from xillion.engine.strategy_engine import StrategyEngine


class _NoopStrategy(Strategy):
    timeframe = "5m"
    instruments = ["NIFTY"]


class _FakeDataBroker:
    def __init__(self):
        self.subscribed: list[str] = []

    async def subscribe_ticks(self, symbols: list[str]) -> None:
        self.subscribed.extend(symbols)


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _make_app(connection_name: str, data_broker) -> FastAPI:
    app = FastAPI()
    registry = PluginRegistry()

    class _FakeLoader:
        def __init__(self, reg):
            self.registry = reg

    app.state.plugin_loader = _FakeLoader(registry)
    bus = MarketDataBus()
    app.state.bus = bus
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)
    app.state.strategy_engine = engine
    app.state.broker_instances = {connection_name: {"instance": data_broker, "status": "connected"}}
    app.state.telegram = None
    return app


async def _seed_instance(app: FastAPI, instance_id: str, connection_name: str) -> None:
    await init_db()
    strategy_name = f"Paper Tick Wiring Test Strategy {instance_id}"
    app.state.plugin_loader.registry.strategies[strategy_name] = _NoopStrategy
    factory = get_session_factory()
    async with factory() as db:
        bc = BrokerClass(
            name=f"BrokerClass {instance_id}",
            module_path="x",
            class_name="X",
            version="1.0.0",
            capabilities_json="{}",
            discovered_at=_now(),
            last_seen_at=_now(),
        )
        db.add(bc)
        await db.flush()
        conn = BrokerConnection(
            broker_class_id=bc.id,
            name=connection_name,
            credentials_ref="ENV",
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
        db.add(conn)
        sc = StrategyClass(
            name=strategy_name,
            module_path="x",
            class_name="X",
            version="1.0.0",
            params_schema_json="{}",
            code_hash="abc",
            discovered_at=_now(),
            last_seen_at=_now(),
        )
        db.add(sc)
        await db.flush()
        db.add(
            StrategyInstance(
                id=instance_id,
                strategy_class_id=sc.id,
                strategy_class_version="1.0.0",
                name=f"Instance {instance_id}",
                mode="paper",
                status="idle",
                broker_connection_id=conn.id,
                instruments_json='["NIFTY"]',
                timeframe="5m",
                params_json="{}",
                capital_allocation=100000,
                risk_limits_json="{}",
                auto_start=False,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_paper_mode_subscribes_ticks_from_dhan_not_a_hardcoded_zerodha():
    dhan = _FakeDataBroker()
    app = await _make_app("Dhan Primary", dhan)
    await _seed_instance(app, "paper-tick-1", "Dhan Primary")

    factory = get_session_factory()
    async with factory() as db:
        from xillion.api.instances import start_instance_core

        result = await start_instance_core(app, db, "paper-tick-1")

    assert dhan.subscribed == ["NIFTY"]
    assert result["tick_source"] == "Dhan Primary"
    assert result["warning"] is None


@pytest.mark.asyncio
async def test_paper_brokers_last_price_actually_updates_from_bus_ticks():
    """The real behavioural gap: PaperBroker.on_tick was never wired to the
    bus, so its _last_prices (used for fills and get_quote) silently never
    updated in production regardless of which broker supplied the feed."""
    dhan = _FakeDataBroker()
    app = await _make_app("Dhan Primary", dhan)
    await _seed_instance(app, "paper-tick-2", "Dhan Primary")

    factory = get_session_factory()
    async with factory() as db:
        from xillion.api.instances import start_instance_core

        await start_instance_core(app, db, "paper-tick-2")

    runner = app.state.strategy_engine.get_runner("paper-tick-2")
    paper_broker = runner._ctx._broker

    await app.state.bus.publish_tick(
        Tick(symbol="NIFTY", ltp=Decimal("24500"), ltt=datetime.now(UTC))
    )

    assert paper_broker._last_prices["NIFTY"] == Decimal("24500")


@pytest.mark.asyncio
async def test_stopping_a_paper_instance_unsubscribes_its_bus_handler():
    """Without cleanup, every restart leaks a handler holding a reference
    to the discarded PaperBroker from the previous run."""
    dhan = _FakeDataBroker()
    app = await _make_app("Dhan Primary", dhan)
    await _seed_instance(app, "paper-tick-3", "Dhan Primary")

    factory = get_session_factory()
    async with factory() as db:
        from xillion.api.instances import start_instance_core, stop_instance_core

        await start_instance_core(app, db, "paper-tick-3")
        assert len(app.state.bus._tick_subscribers["NIFTY"]) == 2  # strategy runner + paper broker

        await stop_instance_core(app, db, "paper-tick-3")

    assert "paper-tick-3" not in getattr(app.state, "paper_tick_handlers", {})
    # Only the strategy runner's own subscription remains after its stop()
    # unsubscribes bar/tick handlers too -- but stop_instance's engine call
    # already tears that one down, so nothing should be left for this symbol.
    assert len(app.state.bus._tick_subscribers["NIFTY"]) == 0


@pytest.mark.asyncio
async def test_no_connected_broker_leaves_the_instance_idle_with_a_named_warning():
    app = await _make_app("Dhan Primary", _FakeDataBroker())
    app.state.broker_instances = {}  # nothing connected
    await _seed_instance(app, "paper-tick-4", "Dhan Primary")

    factory = get_session_factory()
    async with factory() as db:
        from xillion.api.instances import start_instance_core

        result = await start_instance_core(app, db, "paper-tick-4")

    assert result["tick_source"] == "none"
    assert "Dhan Primary" in result["warning"]

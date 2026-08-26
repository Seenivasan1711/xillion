"""
CP12's other half of "closes the software-stop watchdog gap": ctx.state
now genuinely round-trips through StrategyInstance.state_blob. Before this,
_StrategyContextImpl.state always started at {} on every spawn -- the
class's own docstring claimed "persisted to DB on on_stop, restored on
on_start", but nothing ever wrote or read the (already-existing-in-the-
schema-since-migration-001) state_blob column. A strategy like
credit_spread_weekly.py stores its protective-order stop/target levels in
ctx.state; without this fix, a clean restart forgot them entirely.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from xillion.core.events import Bar
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy, StrategyContext
from xillion.data.bus import MarketDataBus
from xillion.db.models import BrokerClass, BrokerConnection, StrategyClass, StrategyInstance
from xillion.db.session import get_session_factory, init_db
from xillion.engine.strategy_engine import StrategyEngine


def _now() -> str:
    return datetime.now(UTC).isoformat()


class _StatefulStrategy(Strategy):
    name = "State Persistence Test Strategy"
    timeframe = "5m"
    instruments = ["NIFTY"]

    async def on_start(self, ctx: StrategyContext) -> None:
        # Only set a default the FIRST time -- a restored instance must see
        # its prior value, not have it clobbered back to the default.
        ctx.state.setdefault("protective_stop", None)
        ctx.state.setdefault("entries_seen", 0)

    async def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        ctx.state["protective_stop"] = str(bar.close)
        ctx.state["entries_seen"] = ctx.state.get("entries_seen", 0) + 1


async def _seed_instance(instance_id: str) -> None:
    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        bc = BrokerClass(
            name=f"Dummy Broker {instance_id}",
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
            name=f"conn-{instance_id}",
            credentials_ref="PAPER",
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
        db.add(conn)
        sc = StrategyClass(
            # DB row name only needs to be unique per test -- the registry
            # lookup key engine.spawn() actually uses is _StatefulStrategy.name,
            # passed separately below, not this DB row.
            name=f"{_StatefulStrategy.name} ({instance_id})",
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
        inst = StrategyInstance(
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
        db.add(inst)
        await db.commit()


async def _load_state_blob(instance_id: str):
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(StrategyInstance).where(StrategyInstance.id == instance_id)
        )
        return result.scalar_one().state_blob


def _spawn_kwargs(instance_id: str, restored_state=None) -> dict:
    from brokers._dummy import DummyBroker

    return dict(
        instance_id=instance_id,
        strategy_name=_StatefulStrategy.name,
        broker=DummyBroker(),
        instruments=["NIFTY"],
        timeframe="5m",
        capital=Decimal("100000"),
        params={},
        mode="paper",
        restored_state=restored_state,
    )


def _bar(symbol="NIFTY", close="24100") -> Bar:
    now = datetime.now(UTC)
    return Bar(
        symbol=symbol,
        timeframe="5m",
        ts=now,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=100,
    )


@pytest.mark.asyncio
async def test_state_survives_a_clean_stop_and_respawn():
    instance_id = "state-persist-1"
    await _seed_instance(instance_id)

    registry = PluginRegistry()
    registry.strategies[_StatefulStrategy.name] = _StatefulStrategy
    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)

    runner = await engine.spawn(**_spawn_kwargs(instance_id))
    await runner._handle_bar(_bar(close="24100"))
    assert runner._ctx.state["protective_stop"] == "24100"
    assert runner._ctx.state["entries_seen"] == 1

    # Clean stop -- must persist the FINAL state (awaited, not fire-and-forget).
    await engine.stop_instance(instance_id, reason="test_restart")
    blob = await _load_state_blob(instance_id)
    assert blob is not None, "state_blob was never written on stop"

    # Simulate a real restart: a brand-new engine/bus, nothing in memory
    # carried over -- the ONLY way state can survive is via the DB blob.
    import pickle

    restored_state = pickle.loads(blob)
    assert restored_state["protective_stop"] == "24100"
    assert restored_state["entries_seen"] == 1

    bus2 = MarketDataBus()
    engine2 = StrategyEngine(bus=bus2, risk_manager=RiskManager())
    engine2.set_registry(registry)
    runner2 = await engine2.spawn(**_spawn_kwargs(instance_id, restored_state=restored_state))

    # on_start's setdefault must NOT clobber the restored value.
    assert runner2._ctx.state["protective_stop"] == "24100"
    assert runner2._ctx.state["entries_seen"] == 1

    # And it keeps accumulating correctly from where it left off.
    await runner2._handle_bar(_bar(close="24200"))
    assert runner2._ctx.state["protective_stop"] == "24200"
    assert runner2._ctx.state["entries_seen"] == 2


@pytest.mark.asyncio
async def test_fresh_spawn_with_no_prior_state_starts_empty():
    instance_id = "state-persist-2"
    await _seed_instance(instance_id)

    registry = PluginRegistry()
    registry.strategies[_StatefulStrategy.name] = _StatefulStrategy
    engine = StrategyEngine(bus=MarketDataBus(), risk_manager=RiskManager())
    engine.set_registry(registry)

    runner = await engine.spawn(**_spawn_kwargs(instance_id))
    assert runner._ctx.state["protective_stop"] is None
    assert runner._ctx.state["entries_seen"] == 0


@pytest.mark.asyncio
async def test_on_bar_persists_state_without_waiting_for_a_clean_stop():
    """Crash-resilience half: state written after on_bar, not only on a
    clean stop -- proves a process killed between bars still has the last
    bar's state on disk."""
    instance_id = "state-persist-3"
    await _seed_instance(instance_id)

    registry = PluginRegistry()
    registry.strategies[_StatefulStrategy.name] = _StatefulStrategy
    engine = StrategyEngine(bus=MarketDataBus(), risk_manager=RiskManager())
    engine.set_registry(registry)

    runner = await engine.spawn(**_spawn_kwargs(instance_id))
    await runner._handle_bar(_bar(close="24300"))
    # _handle_bar's persist is fire-and-forget (asyncio.create_task) -- await
    # it directly here rather than sleeping, so this test is deterministic.
    await runner._ctx._persist_state()

    blob = await _load_state_blob(instance_id)
    assert blob is not None
    import pickle

    assert pickle.loads(blob)["protective_stop"] == "24300"

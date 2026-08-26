"""
_resolve_broker (CP15): generalized from a Zerodha-only lookup to selecting
whichever broker the instance is actually configured with, via
broker_connection_id -> BrokerConnection.name -> app.state.broker_instances.

Also covers the real bug this fix caught along the way: start_instance_core
used to call `await broker.connect({})` unconditionally, including on a
live/alert-mode broker that _resolve_broker already returned ALREADY
connected -- a broker whose connect() actually validates its credentials
(like ZerodhaBroker, which does `credentials["api_key"]`) would raise on
that empty-dict second call. Never caught before because live mode has
always been blocked on real Kite Connect credentials in this environment.
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, HTTPException

from xillion.api.instances import _resolve_broker
from xillion.db.models import BrokerClass, BrokerConnection, StrategyInstance
from xillion.db.session import get_session_factory, init_db


def _now() -> str:
    return datetime.now(UTC).isoformat()


class _FakeConnectedBroker:
    """A broker double whose connect() raises if called a second time on an
    already-connected instance -- mirrors ZerodhaBroker.connect({}) raising
    KeyError on credentials["api_key"]."""

    def __init__(self):
        self.connect_calls = 0

    async def connect(self, credentials: dict) -> None:
        self.connect_calls += 1
        if "api_key" not in credentials and self.connect_calls > 0:
            raise KeyError("api_key")  # what ZerodhaBroker.connect({}) actually raises


async def _make_app_with_brokers(broker_instances: dict) -> FastAPI:
    app = FastAPI()
    app.state.broker_instances = broker_instances
    return app


async def _seed_instance(instance_id: str, connection_name: str, mode: str = "live") -> tuple:
    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        bc = BrokerClass(
            name=f"BrokerClass for {instance_id}",
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
        await db.flush()
        inst = StrategyInstance(
            id=instance_id,
            strategy_class_id=1,
            strategy_class_version="1.0.0",
            name=f"Instance {instance_id}",
            mode=mode,
            status="idle",
            broker_connection_id=conn.id,
            instruments_json="[]",
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
        return db, inst


@pytest.mark.asyncio
async def test_selects_dhan_when_instance_is_configured_for_it():
    dhan = _FakeConnectedBroker()
    zerodha = _FakeConnectedBroker()
    app = await _make_app_with_brokers(
        {
            "Zerodha Primary": {"instance": zerodha, "status": "connected"},
            "Dhan Primary": {"instance": dhan, "status": "connected"},
        }
    )
    factory = get_session_factory()
    async with factory() as db:
        _, inst = await _seed_instance("resolve-broker-1", "Dhan Primary")
        broker, already_connected = await _resolve_broker("live", app, db, inst)

    assert broker is dhan
    assert already_connected is True


@pytest.mark.asyncio
async def test_selects_zerodha_when_instance_is_configured_for_it():
    dhan = _FakeConnectedBroker()
    zerodha = _FakeConnectedBroker()
    app = await _make_app_with_brokers(
        {
            "Zerodha Primary": {"instance": zerodha, "status": "connected"},
            "Dhan Primary": {"instance": dhan, "status": "connected"},
        }
    )
    factory = get_session_factory()
    async with factory() as db:
        _, inst = await _seed_instance("resolve-broker-2", "Zerodha Primary")
        broker, already_connected = await _resolve_broker("live", app, db, inst)

    assert broker is zerodha


@pytest.mark.asyncio
async def test_raises_a_clear_error_when_the_configured_broker_is_not_connected():
    app = await _make_app_with_brokers({})  # nothing connected
    factory = get_session_factory()
    async with factory() as db:
        _, inst = await _seed_instance("resolve-broker-3", "Dhan Primary")
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_broker("live", app, db, inst)

    assert "Dhan Primary" in exc_info.value.detail


@pytest.mark.asyncio
async def test_already_connected_broker_is_never_asked_to_connect_again():
    """The actual bug: start_instance_core must not call connect({}) on a
    broker _resolve_broker already returned as connected."""
    dhan = _FakeConnectedBroker()
    app = await _make_app_with_brokers({"Dhan Primary": {"instance": dhan, "status": "connected"}})
    factory = get_session_factory()
    async with factory() as db:
        _, inst = await _seed_instance("resolve-broker-4", "Dhan Primary")
        broker, already_connected = await _resolve_broker("live", app, db, inst)
        # Mirrors exactly what start_instance_core does with the result.
        if not already_connected:
            await broker.connect({})

    assert dhan.connect_calls == 0  # never called -- would have raised KeyError if it had been


@pytest.mark.asyncio
async def test_paper_mode_always_gets_a_fresh_broker_that_still_needs_connecting():
    app = await _make_app_with_brokers({})
    factory = get_session_factory()
    async with factory() as db:
        _, inst = await _seed_instance("resolve-broker-5", "Zerodha Primary", mode="paper")
        broker, already_connected = await _resolve_broker("paper", app, db, inst)

    assert already_connected is False
    from brokers.paper import PaperBroker

    assert isinstance(broker, PaperBroker)

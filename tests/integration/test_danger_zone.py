"""
/settings/reset-data and /settings/wipe -- previously missing entirely
(the Settings > Risk and > Danger zone tabs 404'd on every call, a
pre-existing gap found while checking whether anything else was broken
before a full manual test pass). reset-data must clear trade/log/run data
while preserving credentials, connections, and strategy configs; wipe
clears everything, including app_user, so GET /auth/setup-status naturally
reports "needs setup" afterward -- the existing first-run flow, not a
separate mode.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from xillion.api.settings import RiskLimits, get_risk_limits, put_risk_limits, reset_data, wipe_everything
from xillion.db.models import (
    AppUser,
    BrokerClass,
    BrokerConnection,
    OrderRecord,
    SignalLog,
    StrategyClass,
    StrategyInstance,
)
from xillion.db.session import get_session_factory, init_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _user(suffix: str = "default") -> AppUser:
    return AppUser(username=f"test-user-{suffix}", password_hash="x", created_at=_now())


async def _seed_everything(instance_id: str) -> None:
    await init_db()
    factory = get_session_factory()
    async with factory() as db:
        bc = BrokerClass(
            name=f"BC {instance_id}", module_path="x", class_name="X", version="1.0.0",
            capabilities_json="{}", discovered_at=_now(), last_seen_at=_now(),
        )
        db.add(bc)
        await db.flush()
        conn = BrokerConnection(
            broker_class_id=bc.id, name=f"conn-{instance_id}", credentials_ref="ENV",
            is_active=True, created_at=_now(), updated_at=_now(),
        )
        db.add(conn)
        sc = StrategyClass(
            name=f"SC {instance_id}", module_path="x", class_name="X", version="1.0.0",
            params_schema_json="{}", code_hash="abc", discovered_at=_now(), last_seen_at=_now(),
        )
        db.add(sc)
        await db.flush()
        inst = StrategyInstance(
            id=instance_id, strategy_class_id=sc.id, strategy_class_version="1.0.0",
            name=f"Instance {instance_id}", mode="paper", status="idle",
            broker_connection_id=conn.id, instruments_json="[]", timeframe="5m",
            params_json="{}", capital_allocation=100000, risk_limits_json="{}",
            auto_start=False, created_at=_now(), updated_at=_now(),
        )
        db.add(inst)
        db.add(OrderRecord(
            id=f"order-{instance_id}",
            broker_connection_id=conn.id, strategy_instance_id=instance_id,
            symbol="NIFTY", exchange="NFO", side="BUY", quantity=1, order_type="MARKET",
            status="FILLED", submitted_at=_now(), updated_at=_now(),
        ))
        db.add(SignalLog(
            strategy_instance_id=instance_id, ts=_now(), underlying_symbol="NIFTY",
            signal_type="ENTER", tag="t", side="BUY", price=100.0,
            message="BUY ENTER", mode="paper", notified=False,
        ))
        db.add(_user(instance_id))
        await db.commit()


@pytest.mark.asyncio
async def test_reset_data_clears_trade_history_but_preserves_settings():
    await _seed_everything("danger-1")
    factory = get_session_factory()

    async with factory() as db:
        result = await reset_data(db=db, user=_user())
        assert result["reset"] is True

    async with factory() as db:
        assert (await db.execute(select(func.count(OrderRecord.id)))).scalar() == 0
        assert (await db.execute(select(func.count(SignalLog.id)))).scalar() == 0
        # Settings/config survive: instance, connection, class registrations.
        assert (await db.execute(select(func.count(StrategyInstance.id)))).scalar() == 1
        assert (await db.execute(select(func.count(BrokerConnection.id)))).scalar() == 1
        assert (await db.execute(select(func.count(BrokerClass.id)))).scalar() == 1


@pytest.mark.asyncio
async def test_wipe_clears_absolutely_everything_including_users():
    await _seed_everything("danger-2")
    factory = get_session_factory()

    async with factory() as db:
        result = await wipe_everything(db=db, user=_user())
        assert result["wiped"] is True

    async with factory() as db:
        assert (await db.execute(select(func.count(AppUser.id)))).scalar() == 0
        assert (await db.execute(select(func.count(StrategyInstance.id)))).scalar() == 0
        assert (await db.execute(select(func.count(BrokerConnection.id)))).scalar() == 0
        assert (await db.execute(select(func.count(OrderRecord.id)))).scalar() == 0


@pytest.mark.asyncio
async def test_risk_limits_round_trip():
    await init_db()
    factory = get_session_factory()

    async with factory() as db:
        before = await get_risk_limits(db=db, user=_user())
        assert before.daily_loss_pct == 2.0  # default

    async with factory() as db:
        body = RiskLimits(daily_loss_pct=5.0, max_open_positions=3, ops_limit=20, burst_window=30)
        result = await put_risk_limits(body, db=db, user=_user())
        assert result["saved"] is True

    async with factory() as db:
        after = await get_risk_limits(db=db, user=_user())
        assert after.daily_loss_pct == 5.0
        assert after.max_open_positions == 3

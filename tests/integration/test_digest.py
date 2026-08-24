"""
Daily/weekly digest (CP10): build_digest reuses the same FIFO fill-matching
GET /api/trades already does, since that's the only place real live/paper
P&L lives (see xillion/engine/digest.py's docstring for why build_journal
from CP6 isn't the right source here). format_digest_message is the
Telegram-facing rendering -- hand-checked against real numbers, not just
"doesn't crash".
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from xillion.db.models import BrokerClass, BrokerConnection, FillRecord, OrderRecord, StrategyInstance
from xillion.db.session import get_session_factory, init_db
from xillion.engine.digest import build_digest, format_digest_message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _seed_broker_connection(db) -> int:
    # id(db) collides across sessions once the earlier object is GC'd and a
    # new one is allocated at the same address -- genuinely observed as a
    # flaky UNIQUE-constraint failure across test functions in this file.
    unique = uuid4().hex
    bc = BrokerClass(
        name=f"Digest Test Broker {unique}", module_path="x", class_name="X", version="1.0.0",
        capabilities_json="{}", discovered_at=_now(), last_seen_at=_now(),
    )
    db.add(bc)
    await db.flush()
    conn = BrokerConnection(
        broker_class_id=bc.id, name=f"digest-conn-{unique}", credentials_ref="PAPER",
        is_active=True, created_at=_now(), updated_at=_now(),
    )
    db.add(conn)
    await db.flush()
    return conn.id


async def _seed_instance(db, instance_id: str, name: str, broker_connection_id: int, status: str = "running") -> None:
    db.add(StrategyInstance(
        id=instance_id, strategy_class_id=1, strategy_class_version="1.0.0",
        name=name, mode="paper", status=status,
        broker_connection_id=broker_connection_id, instruments_json="[]", timeframe="5m",
        params_json="{}", capital_allocation=100000, risk_limits_json="{}",
        created_at=_now(), updated_at=_now(),
    ))


async def _seed_round_trip(db, order_prefix: str, instance_id: str, broker_connection_id: int,
                            symbol: str, entry_price: str, exit_price: str, qty: int, ts: datetime) -> None:
    buy_order = OrderRecord(
        id=f"{order_prefix}-buy", broker_connection_id=broker_connection_id, strategy_instance_id=instance_id,
        symbol=symbol, exchange="NSE", side="BUY", quantity=qty, filled_quantity=qty,
        order_type="MARKET", status="FILLED", avg_fill_price=float(entry_price),
        submitted_at=_now(), updated_at=_now(),
    )
    sell_order = OrderRecord(
        id=f"{order_prefix}-sell", broker_connection_id=broker_connection_id, strategy_instance_id=instance_id,
        symbol=symbol, exchange="NSE", side="SELL", quantity=qty, filled_quantity=qty,
        order_type="MARKET", status="FILLED", avg_fill_price=float(exit_price),
        submitted_at=_now(), updated_at=_now(),
    )
    db.add(buy_order)
    db.add(sell_order)
    await db.flush()
    db.add(FillRecord(
        order_id=buy_order.id, symbol=symbol, side="BUY", quantity=qty, price=float(entry_price),
        ts=ts.isoformat(),
    ))
    db.add(FillRecord(
        order_id=sell_order.id, symbol=symbol, side="SELL", quantity=qty, price=float(exit_price),
        ts=(ts + timedelta(minutes=5)).isoformat(),
    ))


@pytest.mark.asyncio
async def test_build_digest_computes_real_pnl_from_fills():
    await init_db()
    factory = get_session_factory()
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    async with factory() as db:
        conn_id = await _seed_broker_connection(db)
        await _seed_instance(db, "digest-inst-1", "Digest Test Strategy A", conn_id)
        # Winning trade: bought at 100, sold at 110, qty 10 -> +100
        await _seed_round_trip(db, "digest-t1", "digest-inst-1", conn_id, "NIFTY", "100", "110", 10, datetime.now(timezone.utc))
        # Losing trade: bought at 100, sold at 95, qty 10 -> -50
        await _seed_round_trip(db, "digest-t2", "digest-inst-1", conn_id, "NIFTY", "100", "95", 10, datetime.now(timezone.utc))
        await db.commit()

    report = await build_digest(factory, since=since, period_label="Daily")

    assert report.trade_count == 2
    assert report.win_count == 1
    assert report.loss_count == 1
    assert report.total_pnl == 50.0  # +100 - 50
    assert report.by_instance["Digest Test Strategy A"] == 50.0


@pytest.mark.asyncio
async def test_build_digest_excludes_trades_outside_the_period():
    await init_db()
    factory = get_session_factory()
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    old_ts = datetime.now(timezone.utc) - timedelta(days=3)

    async with factory() as db:
        conn_id = await _seed_broker_connection(db)
        await _seed_instance(db, "digest-inst-2", "Digest Test Strategy B", conn_id)
        await _seed_round_trip(db, "digest-old", "digest-inst-2", conn_id, "NIFTY", "100", "200", 1, old_ts)
        await db.commit()

    report = await build_digest(factory, since=since, period_label="Daily")

    # Scoped to this test's own instance -- other tests in this module
    # share the same SQLite file and may have recent trades of their own.
    assert "Digest Test Strategy B" not in report.by_instance


@pytest.mark.asyncio
async def test_build_digest_reports_errored_and_running_instances():
    await init_db()
    factory = get_session_factory()
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    async with factory() as db:
        conn_id = await _seed_broker_connection(db)
        await _seed_instance(db, "digest-running-1", "Running Instance", conn_id, status="running")
        await _seed_instance(db, "digest-errored-1", "Errored Instance", conn_id, status="error")
        await db.commit()

    report = await build_digest(factory, since=since, period_label="Daily")

    assert "Running Instance" in report.running_instances
    assert "Errored Instance" in report.errored_instances
    assert "Running Instance" not in report.errored_instances


def test_format_digest_message_with_no_trades():
    from xillion.engine.digest import DigestReport
    report = DigestReport(
        period_label="Daily", since="2026-01-01T00:00:00+00:00",
        trade_count=0, win_count=0, loss_count=0, total_pnl=0.0,
    )
    msg = format_digest_message(report)
    assert "No closed trades" in msg
    assert "Nothing currently running" in msg


def test_format_digest_message_with_trades_and_errors():
    from xillion.engine.digest import DigestReport
    report = DigestReport(
        period_label="Weekly", since="2026-01-01T00:00:00+00:00",
        trade_count=3, win_count=2, loss_count=1, total_pnl=250.5,
        by_instance={"Strat A": 300.0, "Strat B": -49.5},
        error_count=4, running_instances=["Strat A"], errored_instances=["Strat B"],
    )
    msg = format_digest_message(report)
    assert "3 trade(s)" in msg
    assert "2W/1L" in msg
    assert "+₹250.50" in msg
    assert "Strat A: +₹300.00" in msg
    assert "Strat B: -₹49.50" in msg
    assert "In error state: Strat B" in msg
    assert "4 error/critical log line(s)" in msg

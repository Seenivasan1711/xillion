"""
M01 broker reconciliation (CP14). Positions-only scope -- see
xillion/engine/reconciliation.py's module docstring for what's honestly
NOT covered (orders/fills/funds reconciliation).
"""
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from brokers._dummy import DummyBroker
from xillion.core.events import Position
from xillion.db.models import PositionRecord, ReconciliationReport as ReconciliationReportRecord
from xillion.db.session import get_session_factory, init_db
from xillion.engine.reconciliation import run_reconciliation


def _pos(symbol: str, qty: int) -> Position:
    return Position(
        symbol=symbol, quantity=qty, avg_price=Decimal("100"),
        realised_pnl=Decimal("0"), unrealised_pnl=Decimal("0"), last_price=Decimal("100"),
    )


async def _seed_position_record(instance_id: str, symbol: str, qty: int) -> None:
    factory = get_session_factory()
    async with factory() as session:
        session.add(PositionRecord(
            strategy_instance_id=instance_id, symbol=symbol, quantity=qty,
            avg_price=100.0, realised_pnl=0.0, last_price=100.0,
            updated_at=datetime.now(timezone.utc).isoformat(),
        ))
        await session.commit()


@pytest.mark.asyncio
async def test_flat_on_both_sides_is_clean():
    await init_db()
    broker = DummyBroker()  # get_positions() -> []
    result = await run_reconciliation(broker, "Test Broker", get_session_factory)
    assert result.status == "CLEAN"
    assert result.position_mismatches == []
    assert result.eod_open_positions == []


@pytest.mark.asyncio
async def test_broker_position_we_have_no_record_of_is_a_discrepancy():
    await init_db()
    broker = DummyBroker()

    async def get_positions():
        return [_pos("RECON_SYM_1", 65)]
    broker.get_positions = get_positions

    result = await run_reconciliation(broker, "Test Broker", get_session_factory)
    assert result.status == "DISCREPANCY"
    assert any(m.symbol == "RECON_SYM_1" and m.issue == "broker_only" for m in result.position_mismatches)
    assert "RECON_SYM_1" in result.eod_open_positions


@pytest.mark.asyncio
async def test_our_open_position_the_broker_does_not_have_is_a_discrepancy():
    await init_db()
    await _seed_position_record("recon-instance-1", "RECON_SYM_2", 65)
    broker = DummyBroker()  # broker shows nothing

    result = await run_reconciliation(broker, "Test Broker", get_session_factory)
    assert result.status == "DISCREPANCY"
    assert any(m.symbol == "RECON_SYM_2" and m.issue == "internal_only" for m in result.position_mismatches)


@pytest.mark.asyncio
async def test_matching_but_still_open_position_is_still_a_discrepancy_at_eod():
    """Intraday strategies must be FLAT at EOD -- an open position both
    sides AGREE on is still wrong for M01's purposes, just not a data-
    integrity mismatch."""
    await init_db()
    await _seed_position_record("recon-instance-2", "RECON_SYM_3", 65)
    broker = DummyBroker()

    async def get_positions():
        return [_pos("RECON_SYM_3", 65)]
    broker.get_positions = get_positions

    result = await run_reconciliation(broker, "Test Broker", get_session_factory)
    assert result.status == "DISCREPANCY"
    # Both sides agree on RECON_SYM_3 specifically -- no data mismatch for it
    # (PositionRecord is a live-state table, not date-scoped, so other
    # tests' seeded symbols may also appear here; assert on this test's own
    # symbol only, not on the result being empty).
    assert not any(m.symbol == "RECON_SYM_3" for m in result.position_mismatches)
    assert "RECON_SYM_3" in result.eod_open_positions  # but still open at EOD


@pytest.mark.asyncio
async def test_quantity_mismatch_is_flagged():
    await init_db()
    await _seed_position_record("recon-instance-3", "RECON_SYM_4", 65)
    broker = DummyBroker()

    async def get_positions():
        return [_pos("RECON_SYM_4", 130)]  # broker shows double our quantity
    broker.get_positions = get_positions

    result = await run_reconciliation(broker, "Test Broker", get_session_factory)
    assert result.status == "DISCREPANCY"
    mismatch = next(m for m in result.position_mismatches if m.symbol == "RECON_SYM_4")
    assert mismatch.issue == "quantity_mismatch"
    assert mismatch.broker_qty == 130
    assert mismatch.internal_qty == 65


@pytest.mark.asyncio
async def test_broker_fetch_failure_is_a_failed_report_not_a_crash():
    await init_db()
    broker = DummyBroker()

    async def failing_get_positions():
        raise RuntimeError("broker down")
    broker.get_positions = failing_get_positions

    result = await run_reconciliation(broker, "Test Broker", get_session_factory)
    assert result.status == "FAILED"
    assert "broker down" in result.notes[0]


@pytest.mark.asyncio
async def test_discrepancy_triggers_a_critical_alert():
    await init_db()
    broker = DummyBroker()

    async def get_positions():
        return [_pos("RECON_SYM_5", 65)]
    broker.get_positions = get_positions

    alerts = []
    async def notify(title, body, severity):
        alerts.append((title, severity))

    await run_reconciliation(broker, "Test Broker", get_session_factory, notify=notify)
    assert any(severity == "critical" for _, severity in alerts)


@pytest.mark.asyncio
async def test_result_is_persisted_to_the_database_matching_what_was_returned():
    """PositionRecord is live-state, not date-scoped, so other tests'
    seeded symbols may still be present here -- this asserts the persisted
    row is internally consistent with what run_reconciliation returned,
    not that the account happens to be globally flat."""
    await init_db()
    broker = DummyBroker()
    result = await run_reconciliation(broker, "Persist Test Broker", get_session_factory)

    factory = get_session_factory()
    async with factory() as session:
        db_result = await session.execute(
            select(ReconciliationReportRecord).where(
                ReconciliationReportRecord.broker_name == "Persist Test Broker"
            )
        )
        row = db_result.scalars().first()
    assert row is not None
    assert row.status == result.status
    assert json.loads(row.eod_open_positions_json) == result.eod_open_positions

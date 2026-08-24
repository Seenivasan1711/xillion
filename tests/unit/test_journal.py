"""
Strategy journal (CP6): outcome classification only claims stopped_out /
target_hit when the exit price actually crossed that specific recorded
level -- anything else (manual exit between the two, no target/stop ever
set) stays unclassified rather than guessing.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from xillion.db.models import BacktestRun, BacktestTrade, SignalLog, StrategyClass, StrategyInstance
from xillion.db.session import get_session_factory, init_db
from xillion.engine.journal import (
    STILL_OPEN,
    UNCLASSIFIED,
    build_journal,
    classify_signal_outcome,
    classify_trade_outcome,
)


def test_long_stopped_out():
    assert classify_signal_outcome("BUY", exit_price=95.0, target_price=110.0, stop_loss_price=95.0) == "stopped_out"


def test_long_target_hit():
    assert classify_signal_outcome("BUY", exit_price=110.0, target_price=110.0, stop_loss_price=95.0) == "target_hit"


def test_long_manual_exit_between_levels_is_unclassified():
    assert classify_signal_outcome("BUY", exit_price=102.0, target_price=110.0, stop_loss_price=95.0) == UNCLASSIFIED


def test_short_stopped_out():
    assert classify_signal_outcome("SELL", exit_price=105.0, target_price=90.0, stop_loss_price=105.0) == "stopped_out"


def test_short_target_hit():
    assert classify_signal_outcome("SELL", exit_price=90.0, target_price=90.0, stop_loss_price=105.0) == "target_hit"


def test_no_exit_yet_is_still_open():
    assert classify_signal_outcome("BUY", exit_price=None, target_price=110.0, stop_loss_price=95.0) == STILL_OPEN


def test_no_target_or_stop_recorded_is_unclassified_not_guessed():
    assert classify_signal_outcome("BUY", exit_price=102.0, target_price=None, stop_loss_price=None) == UNCLASSIFIED


def test_trade_outcome_win_and_loss():
    assert classify_trade_outcome(500.0) == "win"
    assert classify_trade_outcome(-500.0) == "loss"
    assert classify_trade_outcome(0.0) == "loss"  # break-even is not a win
    assert classify_trade_outcome(None) == UNCLASSIFIED


async def _seed_instance(instance_id: str) -> None:
    factory = get_session_factory()
    now = datetime.now(timezone.utc).isoformat()
    async with factory() as session:
        session.add(StrategyInstance(
            id=instance_id, strategy_class_id=1, strategy_class_version="1.0.0",
            name="Journal Test Instance", mode="alert", status="running",
            broker_connection_id=1, instruments_json="[]", timeframe="1m",
            params_json="{}", capital_allocation=100000, risk_limits_json="{}",
            created_at=now, updated_at=now,
        ))
        await session.commit()


@pytest.mark.asyncio
async def test_build_journal_combines_signal_log_and_backtest_trade():
    await init_db()
    instance_id = "test-journal-instance"
    await _seed_instance(instance_id)
    factory = get_session_factory()
    now = datetime.now(timezone.utc).isoformat()

    async with factory() as session:
        entry = SignalLog(
            strategy_instance_id=instance_id, ts=now, underlying_symbol="JOURNAL_SYM",
            signal_type="ENTER", tag="setup_1", target_price=110.0, stop_loss_price=95.0,
            side="BUY", price=100.0, message="m", mode="alert", notified=True,
        )
        session.add(entry)
        await session.flush()
        session.add(SignalLog(
            strategy_instance_id=instance_id, ts=now, underlying_symbol="JOURNAL_SYM",
            signal_type="EXIT", tag="setup_1", parent_signal_id=entry.id,
            side="SELL", price=95.0, message="m", mode="alert", notified=True,
        ))

        session.add(StrategyClass(
            name="Journal Test Strategy", module_path="x.py", class_name="X", version="1.0.0",
            params_schema_json="[]", code_hash="abc", discovered_at=now, last_seen_at=now,
        ))
        await session.flush()
        cls_id = (await session.execute(
            select(StrategyClass.id).where(StrategyClass.name == "Journal Test Strategy")
        )).scalar_one()

        session.add(BacktestRun(
            id="journal-run-1", strategy_class_id=cls_id, strategy_class_version="1.0.0",
            params_json="{}", instruments_json="[]", timeframe="1d",
            from_ts=now, to_ts=now, initial_capital=100000, slippage_bps=0,
            status="done", started_at=now, finished_at=now,
        ))
        session.add(BacktestTrade(
            run_id="journal-run-1", symbol="JOURNAL_SYM", side="LONG", quantity=1,
            entry_ts=now, entry_price=100.0, exit_ts=now, exit_price=90.0, pnl=-10.0, tag="t",
        ))
        await session.commit()

    journal = await build_journal(factory, strategy_instance_id=instance_id)
    signal_entries = [j for j in journal if j.source == "signal_log"]
    assert len(signal_entries) == 1
    assert signal_entries[0].outcome == "stopped_out"

    journal_by_class = await build_journal(factory, strategy_class_id=cls_id)
    trade_entries = [j for j in journal_by_class if j.source == "backtest_trade"]
    assert len(trade_entries) == 1
    assert trade_entries[0].outcome == "loss"
    assert trade_entries[0].pnl == -10.0

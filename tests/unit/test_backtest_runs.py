"""
BacktestRun/BacktestTrade persistence (CP3): the tables existed since the
initial migrations but nothing ever wrote to them, so no backtest history
was queryable. This proves the round trip and the "unregistered strategy"
skip path.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from xillion.data.backtest_runs import get_backtest_run, list_backtest_runs, persist_backtest_run
from xillion.db.models import StrategyClass
from xillion.db.session import get_session_factory, init_db
from xillion.engine.backtest_engine import BacktestResult


def _result(run_id: str, strategy_name: str, trades: list[dict]) -> BacktestResult:
    return BacktestResult(
        run_id=run_id,
        strategy_name=strategy_name,
        params={"fast": 10, "slow": 20},
        instruments=["NIFTY_TEST"],
        timeframe="1d",
        from_ts=datetime(2026, 1, 1, tzinfo=UTC),
        to_ts=datetime(2026, 6, 1, tzinfo=UTC),
        initial_capital=100000.0,
        slippage_bps=5,
        metrics={"total_return_pct": 12.5, "sharpe_ratio": 1.2},
        equity_curve=[100000.0, 101000.0, 112500.0],
        trades=trades,
        status="done",
    )


async def _seed_strategy_class(name: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            StrategyClass(
                name=name,
                module_path="strategies/x.py",
                class_name="X",
                version="1.0.0",
                params_schema_json="[]",
                code_hash="abc",
                discovered_at="now",
                last_seen_at="now",
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_persist_and_list_and_get_round_trip():
    await init_db()
    await _seed_strategy_class("Backtest Run Test Strategy")

    trades = [
        {
            "symbol": "NIFTY_TEST",
            "side": "BUY",
            "quantity": 65,
            "entry_ts": "2026-01-05T00:00:00",
            "entry_price": Decimal("100"),
            "exit_ts": "2026-01-10T00:00:00",
            "exit_price": Decimal("110"),
            "pnl": Decimal("650"),
            "tag": "sma_cross",
        },
    ]
    result = _result("run-persist-1", "Backtest Run Test Strategy", trades)

    saved = await persist_backtest_run(get_session_factory(), result)
    assert saved is True

    runs = await list_backtest_runs(get_session_factory())
    assert any(r.id == "run-persist-1" for r in runs)

    run, trade_rows = await get_backtest_run(get_session_factory(), "run-persist-1")
    assert run is not None
    assert run.status == "done"
    assert len(trade_rows) == 1
    assert trade_rows[0].symbol == "NIFTY_TEST"
    assert trade_rows[0].pnl == Decimal("650")


@pytest.mark.asyncio
async def test_persist_skips_unregistered_strategy_without_raising():
    await init_db()
    result = _result("run-persist-2", "Totally Unregistered Strategy", [])
    saved = await persist_backtest_run(get_session_factory(), result)
    assert saved is False

    run, _ = await get_backtest_run(get_session_factory(), "run-persist-2")
    assert run is None


@pytest.mark.asyncio
async def test_get_backtest_run_returns_none_for_unknown_id():
    await init_db()
    run, trades = await get_backtest_run(get_session_factory(), "does-not-exist")
    assert run is None
    assert trades == []

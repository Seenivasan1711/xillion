"""
Persists BacktestResult into backtest_run / backtest_trade. Both tables
existed since the initial migrations, but nothing ever wrote to them, so no
backtest history was queryable -- every result only ever lived in the HTTP
response and was gone the moment the tab closed (CP3).
"""
import json
from datetime import datetime, timezone

from sqlalchemy import select

from xillion.db.models import BacktestRun, BacktestTrade, StrategyClass
from xillion.engine.backtest_engine import BacktestResult


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def persist_backtest_run(
    session_factory,
    result: BacktestResult,
    *,
    fee_config_json: str | None = None,
) -> bool:
    """Write `result` to backtest_run/backtest_trade. Returns False (and
    persists nothing) if the strategy isn't registered in the DB -- e.g. an
    ad-hoc test double -- rather than failing the backtest response over a
    history-tracking side effect."""
    async with session_factory() as session:
        strategy_row = (
            await session.execute(select(StrategyClass).where(StrategyClass.name == result.strategy_name))
        ).scalar_one_or_none()
        if strategy_row is None:
            return False

        now = _now_iso()
        session.add(
            BacktestRun(
                id=result.run_id,
                strategy_class_id=strategy_row.id,
                strategy_class_version=strategy_row.version,
                params_json=json.dumps(result.params),
                instruments_json=json.dumps(result.instruments),
                timeframe=result.timeframe,
                from_ts=result.from_ts.isoformat(),
                to_ts=result.to_ts.isoformat(),
                initial_capital=result.initial_capital,
                slippage_bps=result.slippage_bps,
                fee_config_json=fee_config_json,
                metrics_json=json.dumps(result.metrics),
                equity_curve_json=json.dumps(result.equity_curve),
                status=result.status,
                started_at=now,
                finished_at=now,
                error=result.error,
            )
        )

        for t in result.trades:
            session.add(
                BacktestTrade(
                    run_id=result.run_id,
                    symbol=t.get("symbol") or (result.instruments[0] if result.instruments else ""),
                    side=t.get("side") or "",
                    quantity=int(t.get("quantity") or 0),
                    entry_ts=t.get("entry_ts") or now,
                    entry_price=t.get("entry_price"),
                    exit_ts=t.get("exit_ts"),
                    exit_price=t.get("exit_price"),
                    pnl=t.get("pnl"),
                    tag=t.get("tag"),
                )
            )

        await session.commit()
        return True


async def list_backtest_runs(session_factory, *, limit: int = 50) -> list[BacktestRun]:
    async with session_factory() as session:
        result = await session.execute(
            select(BacktestRun).order_by(BacktestRun.started_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


async def get_backtest_run(session_factory, run_id: str) -> tuple[BacktestRun | None, list[BacktestTrade]]:
    async with session_factory() as session:
        run = await session.get(BacktestRun, run_id)
        if run is None:
            return None, []
        trades_result = await session.execute(
            select(BacktestTrade).where(BacktestTrade.run_id == run_id).order_by(BacktestTrade.entry_ts)
        )
        return run, list(trades_result.scalars().all())

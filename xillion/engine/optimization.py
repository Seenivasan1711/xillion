"""
Parameter optimization (CP5): grid search over a parameter grid, and
walk-forward validation -- the check that actually catches overfitting. A
strategy whose backtest metrics look great on the whole history but whose
best-in-sample parameters fail on data they weren't picked against is
curve-fit to that specific history, not a real edge.
"""

import itertools
from dataclasses import dataclass, field
from datetime import datetime

from xillion.core.events import Bar
from xillion.core.strategy_base import Strategy
from xillion.engine.backtest_engine import BacktestEngine, FeeConfig


@dataclass
class GridResult:
    params: dict
    metrics: dict
    trade_count: int


def _sort_key(result: "GridResult", rank_by: str):
    value = result.metrics.get(rank_by)
    return (value is not None, value if value is not None else 0.0)


async def grid_search(
    strategy_cls: type[Strategy],
    bars: list[Bar],
    instruments: list[str],
    timeframe: str,
    initial_capital: float,
    param_grid: dict[str, list],
    base_params: dict | None = None,
    slippage_bps: int = 5,
    fee_config: FeeConfig | None = None,
    rank_by: str = "sharpe_ratio",
) -> list[GridResult]:
    """Backtest every combination in param_grid's Cartesian product over
    the SAME bars, ranked by `rank_by` descending (missing/None sorts last).
    An empty param_grid runs `base_params` alone -- one "combination"."""
    base_params = base_params or {}
    keys = list(param_grid.keys())
    combos = list(itertools.product(*(param_grid[k] for k in keys))) if keys else [()]

    engine = BacktestEngine()
    results: list[GridResult] = []
    for combo in combos:
        params = {**base_params, **dict(zip(keys, combo, strict=False))}
        result = await engine.run(
            strategy=strategy_cls(),
            bars=bars,
            instruments=instruments,
            timeframe=timeframe,
            initial_capital=initial_capital,
            params=params,
            slippage_bps=slippage_bps,
            fee_config=fee_config,
        )
        results.append(
            GridResult(params=params, metrics=result.metrics, trade_count=len(result.trades))
        )

    results.sort(key=lambda r: _sort_key(r, rank_by), reverse=True)
    return results


@dataclass
class WalkForwardFold:
    train_from: datetime
    train_to: datetime
    test_from: datetime
    test_to: datetime
    best_params: dict
    in_sample_metrics: dict
    out_of_sample_metrics: dict


@dataclass
class WalkForwardResult:
    rank_by: str
    folds: list[WalkForwardFold] = field(default_factory=list)
    avg_in_sample: float | None = None
    avg_out_of_sample: float | None = None
    is_likely_overfit: bool = False


def _avg(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


async def walk_forward(
    strategy_cls: type[Strategy],
    bars: list[Bar],
    instruments: list[str],
    timeframe: str,
    initial_capital: float,
    param_grid: dict[str, list],
    n_folds: int = 4,
    train_ratio: float = 0.7,
    base_params: dict | None = None,
    slippage_bps: int = 5,
    fee_config: FeeConfig | None = None,
    rank_by: str = "sharpe_ratio",
) -> WalkForwardResult:
    """Split the history into `n_folds` sequential chunks; in each, pick the
    best params on the first `train_ratio` (in-sample) via grid_search, then
    backtest that SAME pick on the remaining tail (out-of-sample) it was
    never fitted against. Folds with too little data on either side are
    skipped rather than raising -- optimization on a handful of bars is
    meaningless, not an error.
    """
    sorted_bars = sorted(bars, key=lambda b: b.ts)
    fold_size = len(sorted_bars) // n_folds
    engine = BacktestEngine()
    folds: list[WalkForwardFold] = []

    for i in range(n_folds):
        start = i * fold_size
        end = (i + 1) * fold_size if i < n_folds - 1 else len(sorted_bars)
        fold_bars = sorted_bars[start:end]
        split = int(len(fold_bars) * train_ratio)
        train_bars, test_bars = fold_bars[:split], fold_bars[split:]
        if len(train_bars) < 2 or len(test_bars) < 2:
            continue

        grid_results = await grid_search(
            strategy_cls,
            train_bars,
            instruments,
            timeframe,
            initial_capital,
            param_grid,
            base_params,
            slippage_bps,
            fee_config,
            rank_by,
        )
        if not grid_results:
            continue
        best = grid_results[0]

        test_result = await engine.run(
            strategy=strategy_cls(),
            bars=test_bars,
            instruments=instruments,
            timeframe=timeframe,
            initial_capital=initial_capital,
            params=best.params,
            slippage_bps=slippage_bps,
            fee_config=fee_config,
        )

        folds.append(
            WalkForwardFold(
                train_from=train_bars[0].ts,
                train_to=train_bars[-1].ts,
                test_from=test_bars[0].ts,
                test_to=test_bars[-1].ts,
                best_params=best.params,
                in_sample_metrics=best.metrics,
                out_of_sample_metrics=test_result.metrics,
            )
        )

    avg_in = _avg([f.in_sample_metrics.get(rank_by) for f in folds])
    avg_out = _avg([f.out_of_sample_metrics.get(rank_by) for f in folds])

    # Overfit heuristic: in-sample looked good but out-of-sample didn't hold
    # up -- either it collapsed to well under half, or flipped to a loss
    # entirely, or (worst case) there was nothing usable out-of-sample at all.
    is_likely_overfit = (
        avg_in is not None
        and avg_in > 0
        and (avg_out is None or avg_out <= 0 or avg_out < avg_in * 0.5)
    )

    return WalkForwardResult(
        rank_by=rank_by,
        folds=folds,
        avg_in_sample=avg_in,
        avg_out_of_sample=avg_out,
        is_likely_overfit=is_likely_overfit,
    )

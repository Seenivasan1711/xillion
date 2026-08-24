"""
Parameter optimization (CP5): grid search picks the objectively winning
param on synthetic data with a known answer, and walk-forward catches a
parameter that wins in-sample but doesn't generalize -- constructed with a
deliberate regime change (uptrend then a hard downtrend) so the "long"
direction is provably the in-sample winner and provably loses out-of-sample.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from xillion.core.events import Bar
from xillion.core.strategy_base import ParamSpec, Strategy
from xillion.engine.backtest_engine import FeeConfig
from xillion.engine.optimization import grid_search, walk_forward

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _bars(closes: list[float], symbol="OPT_TEST") -> list[Bar]:
    return [
        Bar(symbol=symbol, timeframe="1d", ts=START + timedelta(days=i),
            open=Decimal(str(c)), high=Decimal(str(c)), low=Decimal(str(c)),
            close=Decimal(str(c)), volume=100)
        for i, c in enumerate(closes)
    ]


class _DirectionHoldStrategy(Strategy):
    """Enters once on the first bar per `direction` and holds -- deliberately
    simple so grid_search/walk_forward tests aren't entangled with indicator
    correctness, which has its own test file."""
    name = "Direction Hold Test Strategy"
    timeframe = "1d"
    params_schema = [ParamSpec("direction", "choice", default="long", choices=["long", "short"])]

    async def on_bar(self, bar, ctx):
        if ctx.state.get("done"):
            return
        if ctx.params["direction"] == "long":
            await ctx.buy(bar.symbol, 1)
        else:
            await ctx.sell(bar.symbol, 1)
        ctx.state["done"] = True


@pytest.mark.asyncio
async def test_grid_search_picks_the_objectively_winning_param():
    uptrend = _bars([100 + i for i in range(20)])  # steady rise: long should win

    results = await grid_search(
        _DirectionHoldStrategy, uptrend, ["OPT_TEST"], "1d", 100000.0,
        param_grid={"direction": ["long", "short"]},
        slippage_bps=0, fee_config=FeeConfig.zero(), rank_by="total_return_pct",
    )

    assert len(results) == 2
    assert results[0].params["direction"] == "long"
    assert results[0].metrics["total_return_pct"] > 0
    assert results[1].params["direction"] == "short"
    assert results[1].metrics["total_return_pct"] < results[0].metrics["total_return_pct"]


@pytest.mark.asyncio
async def test_grid_search_picks_short_on_a_downtrend():
    downtrend = _bars([120 - i for i in range(20)])

    results = await grid_search(
        _DirectionHoldStrategy, downtrend, ["OPT_TEST"], "1d", 100000.0,
        param_grid={"direction": ["long", "short"]},
        slippage_bps=0, fee_config=FeeConfig.zero(), rank_by="total_return_pct",
    )

    assert results[0].params["direction"] == "short"
    assert results[0].metrics["total_return_pct"] > 0


@pytest.mark.asyncio
async def test_walk_forward_flags_a_parameter_that_does_not_generalize():
    # Train window: steady uptrend (100 -> 119) -- "long" wins in-sample.
    # Test window: sharp reversal downtrend (119 -> 60) -- "long" loses badly out-of-sample.
    train = [100 + i for i in range(20)]
    test = [119 - i * 3 for i in range(20)]
    bars = _bars(train + test)

    result = await walk_forward(
        _DirectionHoldStrategy, bars, ["OPT_TEST"], "1d", 100000.0,
        param_grid={"direction": ["long", "short"]},
        n_folds=1, train_ratio=0.5,
        slippage_bps=0, fee_config=FeeConfig.zero(), rank_by="total_return_pct",
    )

    assert len(result.folds) == 1
    fold = result.folds[0]
    assert fold.best_params["direction"] == "long"  # correctly the in-sample winner
    assert fold.in_sample_metrics["total_return_pct"] > 0
    assert fold.out_of_sample_metrics["total_return_pct"] < 0  # but loses on the regime change
    assert result.is_likely_overfit is True


@pytest.mark.asyncio
async def test_walk_forward_does_not_flag_a_parameter_that_generalizes():
    # Same steady uptrend all the way through -- "long" wins both in- and
    # out-of-sample, so this must NOT be flagged as overfit.
    bars = _bars([100 + i for i in range(40)])

    result = await walk_forward(
        _DirectionHoldStrategy, bars, ["OPT_TEST"], "1d", 100000.0,
        param_grid={"direction": ["long", "short"]},
        n_folds=1, train_ratio=0.5,
        slippage_bps=0, fee_config=FeeConfig.zero(), rank_by="total_return_pct",
    )

    assert result.avg_in_sample > 0
    assert result.avg_out_of_sample > 0
    assert result.is_likely_overfit is False


@pytest.mark.asyncio
async def test_grid_search_with_empty_grid_runs_base_params_once():
    bars = _bars([100 + i for i in range(10)])
    results = await grid_search(
        _DirectionHoldStrategy, bars, ["OPT_TEST"], "1d", 100000.0,
        param_grid={}, base_params={"direction": "long"},
        slippage_bps=0, fee_config=FeeConfig.zero(),
    )
    assert len(results) == 1
    assert results[0].params == {"direction": "long"}

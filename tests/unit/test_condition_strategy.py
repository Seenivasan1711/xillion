"""
ConditionStrategy end-to-end (CP5): a strategy built entirely from
metric/operator/threshold JSON, run through the real BacktestEngine -- the
same engine CP1 hardened, so this proves the Strategy Builder produces a
strategy that actually trades correctly, not just that condition.py's
functions return the right booleans in isolation.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from strategies.condition_strategy import ConditionStrategy
from xillion.core.events import Bar
from xillion.engine.backtest_engine import BacktestEngine, FeeConfig

START = datetime(2026, 6, 1, 9, 15, tzinfo=timezone.utc)


def _bars(closes: list[float], symbol="COND_TEST") -> list[Bar]:
    return [
        Bar(symbol=symbol, timeframe="1d", ts=START + timedelta(days=i),
            open=Decimal(str(c)), high=Decimal(str(c)), low=Decimal(str(c)),
            close=Decimal(str(c)), volume=100)
        for i, c in enumerate(closes)
    ]


@pytest.mark.asyncio
async def test_entry_and_exit_conditions_produce_a_real_trade():
    # Dip then spike -> close crosses above sma(3) around bar 4 (entry).
    # Later drop below 10 -> exit.
    closes = [10, 9, 8, 7, 20, 19, 18, 9]
    bars = _bars(closes)

    params = {
        "entry_conditions": [
            {"metric": {"name": "close"}, "operator": "crosses_above", "other_metric": {"name": "sma", "period": 3}},
        ],
        "exit_conditions": [
            {"metric": {"name": "close"}, "operator": "<", "threshold": 10},
        ],
        "direction": "long",
        "qty": 1,
        "lookback": 20,
    }

    engine = BacktestEngine()
    result = await engine.run(
        strategy=ConditionStrategy(),
        bars=bars,
        instruments=["COND_TEST"],
        timeframe="1d",
        initial_capital=100000.0,
        params=params,
        slippage_bps=0,
        fee_config=FeeConfig.zero(),
    )

    assert result.status == "done"
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade["side"] == "LONG"
    assert trade["entry_price"] == pytest.approx(20.0)  # entry bar's close, zero slippage
    assert trade["exit_price"] == pytest.approx(9.0)     # exit bar's close
    assert trade["pnl"] == pytest.approx(-11.0)           # bought at 20, sold at 9, qty 1, zero fees


@pytest.mark.asyncio
async def test_short_direction_enters_with_sell_and_exits_with_buy():
    # Spike then drop -> close crosses below sma(3) around bar 4 (short entry).
    closes = [10, 11, 12, 13, 5, 6, 7, 20]
    bars = _bars(closes, symbol="COND_SHORT")

    params = {
        "entry_conditions": [
            {"metric": {"name": "close"}, "operator": "crosses_below", "other_metric": {"name": "sma", "period": 3}},
        ],
        "exit_conditions": [
            {"metric": {"name": "close"}, "operator": ">", "threshold": 15},
        ],
        "direction": "short",
        "qty": 1,
        "lookback": 20,
    }

    engine = BacktestEngine()
    result = await engine.run(
        strategy=ConditionStrategy(),
        bars=bars,
        instruments=["COND_SHORT"],
        timeframe="1d",
        initial_capital=100000.0,
        params=params,
        slippage_bps=0,
        fee_config=FeeConfig.zero(),
    )

    assert result.status == "done"
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade["side"] == "SHORT"  # short entry sells first
    assert trade["entry_price"] == pytest.approx(5.0)
    assert trade["exit_price"] == pytest.approx(20.0)
    assert trade["pnl"] == pytest.approx(-15.0)  # sold at 5, had to buy back at 20 -- a losing short


@pytest.mark.asyncio
async def test_no_trade_when_conditions_never_fire():
    bars = _bars([10, 10, 10, 10, 10])  # flat line -- no crossover ever happens

    params = {
        "entry_conditions": [
            {"metric": {"name": "close"}, "operator": "crosses_above", "other_metric": {"name": "sma", "period": 3}},
        ],
        "exit_conditions": [{"metric": {"name": "close"}, "operator": "<", "threshold": 5}],
        "direction": "long",
        "qty": 1,
        "lookback": 20,
    }

    engine = BacktestEngine()
    result = await engine.run(
        strategy=ConditionStrategy(),
        bars=bars,
        instruments=["COND_TEST"],
        timeframe="1d",
        initial_capital=100000.0,
        params=params,
        slippage_bps=0,
        fee_config=FeeConfig.zero(),
    )

    assert result.status == "done"
    assert len(result.trades) == 0


@pytest.mark.asyncio
async def test_empty_conditions_never_trade():
    """An empty entry_conditions list must never be treated as 'always
    enter' -- that would fire on every single bar."""
    bars = _bars([10, 20, 30, 5, 50])

    params = {
        "entry_conditions": [],
        "exit_conditions": [],
        "direction": "long",
        "qty": 1,
        "lookback": 20,
    }

    engine = BacktestEngine()
    result = await engine.run(
        strategy=ConditionStrategy(),
        bars=bars,
        instruments=["COND_TEST"],
        timeframe="1d",
        initial_capital=100000.0,
        params=params,
        slippage_bps=0,
        fee_config=FeeConfig.zero(),
    )

    assert len(result.trades) == 0

"""
Integration test: SMA Cross strategy against a synthetic tick stream.
Verifies that the strategy places the right orders through the DummyBroker.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from xillion.core.events import Bar, Side
from xillion.engine.backtest_engine import BacktestEngine


def _bar(symbol: str, close: float, minute: int) -> Bar:
    base = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
    ts = base + timedelta(minutes=minute * 15)
    price = Decimal(str(close))
    return Bar(
        symbol=symbol,
        timeframe="15m",
        ts=ts,
        open=price,
        high=price * Decimal("1.001"),
        low=price * Decimal("0.999"),
        close=price,
        volume=1000,
    )


def _make_bars_with_crossover() -> list[Bar]:
    """
    Generate a bar series where:
    - Bars 0-29: flat at 20000 (both SMAs settle to same value)
    - Bars 30-50: sharp rise to 21000 (fast SMA crosses ABOVE slow SMA → BUY signal)
    - Bars 51-80: sharp fall to 19000 (fast SMA crosses BELOW slow SMA → SELL signal)
    """
    bars: list[Bar] = []
    for i in range(30):
        bars.append(_bar("NIFTY", 20000.0, i))
    for i in range(30, 51):
        price = 20000.0 + (i - 30) * 50.0  # rises to 21000
        bars.append(_bar("NIFTY", price, i))
    for i in range(51, 81):
        price = 21000.0 - (i - 50) * 60.0  # falls to 19200
        bars.append(_bar("NIFTY", price, i))
    return bars


@pytest.mark.asyncio
async def test_sma_cross_places_orders_on_synthetic_data():
    from strategies.example_sma_cross import SMACrossStrategy

    bars = _make_bars_with_crossover()
    engine = BacktestEngine()
    strategy = SMACrossStrategy()
    result = await engine.run(
        strategy=strategy,
        bars=bars,
        instruments=["NIFTY"],
        timeframe="15m",
        initial_capital=100_000.0,
        params={"fast": 10, "slow": 30, "qty": 1},
        slippage_bps=5,
    )
    assert result.status == "done", f"Backtest failed: {result.error}"
    assert len(result.trades) >= 1, "Expected at least one round-trip trade"


@pytest.mark.asyncio
async def test_sma_cross_equity_curve_has_correct_length():
    from strategies.example_sma_cross import SMACrossStrategy

    bars = _make_bars_with_crossover()
    engine = BacktestEngine()
    result = await engine.run(
        strategy=SMACrossStrategy(),
        bars=bars,
        instruments=["NIFTY"],
        timeframe="15m",
        initial_capital=100_000.0,
        params={"fast": 10, "slow": 30, "qty": 1},
    )
    assert len(result.equity_curve) == len(bars) + 1  # initial + one per bar


@pytest.mark.asyncio
async def test_warmup_bars_produce_no_trades():
    """With only 5 bars (< slow period 30), no trades should be placed."""
    from strategies.example_sma_cross import SMACrossStrategy

    bars = [_bar("NIFTY", 21000 + i * 10, i) for i in range(5)]
    engine = BacktestEngine()
    result = await engine.run(
        strategy=SMACrossStrategy(),
        bars=bars,
        instruments=["NIFTY"],
        timeframe="15m",
        initial_capital=100_000.0,
        params={"fast": 10, "slow": 30, "qty": 1},
    )
    assert result.status == "done"
    assert result.trades == []

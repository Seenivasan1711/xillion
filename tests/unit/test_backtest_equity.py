"""
Backtest equity-curve and short-selling regressions.

These pin down the bugs found in the 2026-08 audit:
  - equity() returned cash only, so the curve was FLAT while a position was
    open and max drawdown / Sharpe / Sortino were computed off a curve that
    never moved mid-trade;
  - selling with no position credited cash and tracked no short, so
    premium-selling strategies could not be backtested at all;
  - P&L ignored the contract multiplier.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from xillion.core.contracts import ContractSpec
from xillion.core.events import Bar
from xillion.core.strategy_base import Strategy
from xillion.engine.backtest_engine import BacktestEngine, FeeConfig

START = datetime(2026, 6, 1, 9, 15, tzinfo=UTC)


def _bars(closes, symbol="TEST", timeframe="1d"):
    return [
        Bar(
            symbol=symbol,
            timeframe=timeframe,
            ts=START + timedelta(days=i),
            open=Decimal(str(c)),
            high=Decimal(str(c)),
            low=Decimal(str(c)),
            close=Decimal(str(c)),
            volume=100,
        )
        for i, c in enumerate(closes)
    ]


class BuyAndHold(Strategy):
    name = "Buy And Hold"
    timeframe = "1d"

    async def on_bar(self, bar, ctx):
        if ctx.state.get("done"):
            return
        await ctx.buy(bar.symbol, 1)
        ctx.state["done"] = True


class ShortAndHold(Strategy):
    name = "Short And Hold"
    timeframe = "1d"

    async def on_bar(self, bar, ctx):
        if ctx.state.get("done"):
            return
        await ctx.sell(bar.symbol, 1)
        ctx.state["done"] = True


async def _run(strategy, closes, **kw):
    return await BacktestEngine().run(
        strategy=strategy,
        bars=_bars(closes),
        instruments=["TEST"],
        timeframe="1d",
        initial_capital=100_000.0,
        params={},
        slippage_bps=0,
        fee_config=FeeConfig.zero(),
        **kw,
    )


@pytest.mark.asyncio
async def test_equity_curve_tracks_unrealised_gain():
    """Buy at 100, price rises to 130 while still held. Equity must rise with
    it — previously it stayed pinned at the cash value."""
    result = await _run(BuyAndHold(), [100, 110, 120, 130])
    curve = result.equity_curve
    assert curve[-1] > curve[1], "equity did not move while a position was open"
    assert curve[-1] == pytest.approx(100_030.0)  # +30 unrealised on 1 unit


@pytest.mark.asyncio
async def test_drawdown_is_detected_mid_hold():
    """A dip while holding must produce a non-zero max drawdown. With a
    cash-only equity curve this was always 0 and the metric was useless."""
    result = await _run(BuyAndHold(), [100, 120, 80, 110])
    assert result.metrics["max_drawdown"] > 0
    assert result.metrics["max_drawdown_pct"] > 0


@pytest.mark.asyncio
async def test_short_position_is_tracked_and_profits_when_price_falls():
    result = await _run(ShortAndHold(), [100, 90, 80])
    assert result.equity_curve[-1] == pytest.approx(100_020.0)  # short 1 from 100 → 80


@pytest.mark.asyncio
async def test_short_loses_when_price_rises():
    result = await _run(ShortAndHold(), [100, 110, 120])
    assert result.equity_curve[-1] == pytest.approx(99_980.0)


@pytest.mark.asyncio
async def test_contract_multiplier_scales_equity():
    """Same price path, lot size 65 → 65x the P&L."""
    contracts = {"TEST": ContractSpec(symbol="TEST", multiplier=65)}
    result = await _run(BuyAndHold(), [100, 110], contracts=contracts)
    # +10 move on 1 lot of 65 = +650
    assert result.equity_curve[-1] == pytest.approx(100_650.0)


@pytest.mark.asyncio
async def test_zero_fee_config_is_exact():
    """With no fees and no slippage the arithmetic must be exact, so any
    future fee-model change shows up as a clean diff here."""
    result = await _run(BuyAndHold(), [100, 100])
    assert result.equity_curve[-1] == pytest.approx(100_000.0)


@pytest.mark.asyncio
async def test_sortino_is_json_safe_with_no_downside():
    """A strictly-rising curve has no downside deviation. That used to yield
    float('inf'), which is not valid JSON and broke the API response."""
    result = await _run(BuyAndHold(), [100, 110, 120, 130])
    assert result.metrics["sortino_ratio"] is None

"""
GoldSweepReversal through the REAL BacktestEngine (not the hand-built
FakeContext in test_gold_sweep_reversal.py) -- this is what actually
caught two real bugs 2026-09-22 that the FakeContext tests couldn't:
_BacktestContext had no notify() override (crashed on the very first
paper/backtest-mode entry with a bare NotImplementedError), and
BacktestEngine only ever synthesized on_tick ticks for dynamically-
resolved option legs, never for a plain strategy's own primary symbol --
so a non-options strategy's SL/TP monitoring (which lives entirely in
on_tick) never ran in backtest at all, and a position that opened never
closed.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from strategies.gold_sweep_reversal import GoldSweepReversal
from xillion.core.events import Bar
from xillion.core.strategy_base import fill_param_defaults
from xillion.engine.backtest_engine import BacktestEngine

SYMBOL = "XAUUSD"
TF = "5m"


def _bar(ts: datetime, o: float, h: float, low: float, c: float) -> Bar:
    return Bar(
        symbol=SYMBOL,
        timeframe=TF,
        ts=ts,
        open=Decimal(str(o)),
        high=Decimal(str(h)),
        low=Decimal(str(low)),
        close=Decimal(str(c)),
        volume=0,
    )


def _london(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 6, hour, minute, tzinfo=UTC)


def _bars_for_a_clean_win() -> list[Bar]:
    bars = []
    prev_day = datetime(2026, 1, 5, tzinfo=UTC)
    bars.append(_bar(prev_day.replace(hour=10), 2600, 2650, 2595, 2620))  # PD high
    bars.append(_bar(prev_day.replace(hour=14), 2610, 2615, 2590, 2600))  # PD low
    today_asian = datetime(2026, 1, 6, tzinfo=UTC)
    bars.append(_bar(today_asian.replace(hour=2), 2615, 2630, 2612, 2620))  # Asian high
    bars.append(_bar(today_asian.replace(hour=5), 2618, 2622, 2610, 2615))  # Asian low
    # Sweep Asian High (2630), reclaim -> SHORT entry at 2629.0, sl=2632.5, tp=2621.5
    bars.append(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5))
    bars.append(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0))
    bars.append(_bar(_london(9, 10), 2626, 2627, 2624, 2625.0))
    # This bar's close (2621.0) is at/through tp (2621.5) -- on_tick closes it.
    bars.append(_bar(_london(9, 15), 2622, 2623, 2619, 2621.0))
    return bars


@pytest.mark.asyncio
async def test_real_backtest_engine_opens_and_closes_a_position():
    strategy = GoldSweepReversal()
    engine = BacktestEngine()
    params = fill_param_defaults(GoldSweepReversal, {})

    result = await engine.run(
        strategy=strategy,
        bars=_bars_for_a_clean_win(),
        instruments=[SYMBOL],
        timeframe=TF,
        initial_capital=5000.0,
        params=params,
        slippage_bps=0,
    )

    assert result.status == "done", result.error
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade["side"] == "SHORT"  # ClosedTrade records SELL-to-open as "SHORT"
    assert trade["symbol"] == SYMBOL
    assert trade["entry_price"] == pytest.approx(2629.0)
    # Closed via on_tick at the bar whose close reached tp (2621.5) --
    # exit price is that bar's close (2621.0), bar-close precision only.
    assert trade["exit_price"] == pytest.approx(2621.0)
    assert trade["pnl"] > 0  # a real win, not just "didn't crash"
    assert trade["tag"] == "Asian High"

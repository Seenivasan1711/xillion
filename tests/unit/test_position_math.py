"""
Position arithmetic — the shared core used by BOTH the live engine and the
backtest engine. These are the parity tests: if this file passes, a strategy
computes the same position and P&L whether it is backtesting or trading live.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from xillion.core.events import Side
from xillion.engine.position_math import PositionState, apply_fill

TS = datetime(2026, 6, 1, 9, 15, tzinfo=timezone.utc)


def _fill(state, side, qty, price, multiplier=1):
    return apply_fill(
        state, symbol="TEST", side=side, quantity=qty,
        price=Decimal(str(price)), ts=TS, multiplier=multiplier,
    )


def test_open_long():
    out = _fill(None, Side.BUY, 10, 100)
    assert out.state.qty == 10
    assert out.state.avg_price == Decimal("100")
    assert out.closed_trade is None


def test_open_short_from_flat():
    """A sell with no existing position must create a SHORT, not vanish.
    The backtest engine used to just credit cash and track nothing here."""
    out = _fill(None, Side.SELL, 10, 100)
    assert out.state.qty == -10
    assert out.state.avg_price == Decimal("100")
    assert out.closed_trade is None


def test_average_in_long():
    state = _fill(None, Side.BUY, 10, 100).state
    out = _fill(state, Side.BUY, 10, 120)
    assert out.state.qty == 20
    assert out.state.avg_price == Decimal("110")   # (100*10 + 120*10) / 20
    assert out.closed_trade is None


def test_average_in_short():
    state = _fill(None, Side.SELL, 10, 100).state
    out = _fill(state, Side.SELL, 10, 120)
    assert out.state.qty == -20
    assert out.state.avg_price == Decimal("110")


def test_close_long_for_profit():
    state = _fill(None, Side.BUY, 10, 100).state
    out = _fill(state, Side.SELL, 10, 110)
    assert out.state.qty == 0
    assert out.closed_trade is not None
    assert out.closed_trade.pnl == pytest.approx(100.0)   # 10 * 10
    assert out.closed_trade.side == "LONG"


def test_close_short_for_profit():
    """Shorts profit when price FALLS — the sign handling that was missing."""
    state = _fill(None, Side.SELL, 10, 100).state
    out = _fill(state, Side.BUY, 10, 90)
    assert out.state.qty == 0
    assert out.closed_trade.pnl == pytest.approx(100.0)   # (90-100) * 10 * -1
    assert out.closed_trade.side == "SHORT"


def test_close_short_for_loss():
    state = _fill(None, Side.SELL, 10, 100).state
    out = _fill(state, Side.BUY, 10, 110)
    assert out.closed_trade.pnl == pytest.approx(-100.0)


def test_partial_reduce_keeps_avg_price():
    state = _fill(None, Side.BUY, 10, 100).state
    out = _fill(state, Side.SELL, 4, 110)
    assert out.state.qty == 6
    assert out.state.avg_price == Decimal("100")          # unchanged
    assert out.closed_trade.quantity == 4
    assert out.closed_trade.pnl == pytest.approx(40.0)


def test_reversal_reprices_remainder():
    """Long 10 → sell 15 leaves a SHORT 5 that must be priced at the new fill.
    The live engine only reset avg_price when flat, so a reversal used to
    leave the new short carrying the old long's entry price — mispricing
    every subsequent P&L on that position."""
    state = _fill(None, Side.BUY, 10, 100).state
    out = _fill(state, Side.SELL, 15, 110)
    assert out.state.qty == -5
    assert out.state.avg_price == Decimal("110")           # repriced, not 100
    assert out.closed_trade.quantity == 10
    assert out.closed_trade.pnl == pytest.approx(100.0)


def test_multiplier_scales_pnl():
    """NIFTY options trade in lots of 65 — a 10-point move on 1 lot is ₹650,
    not ₹10. Without this, every derivative backtest was wrong by the lot size."""
    state = _fill(None, Side.BUY, 1, 100, multiplier=65).state
    out = _fill(state, Side.SELL, 1, 110, multiplier=65)
    assert out.closed_trade.pnl == pytest.approx(650.0)


def test_rejects_non_positive_quantity():
    with pytest.raises(ValueError):
        _fill(None, Side.BUY, 0, 100)

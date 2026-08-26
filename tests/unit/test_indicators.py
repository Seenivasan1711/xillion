"""
Indicator library (CP5): hand-checked values where the arithmetic is small
enough to verify by hand, structural/compositional checks where it isn't
(MACD), and directional invariants for the genuinely stateful ones
(Supertrend) rather than risking a transcription error in a 35-point
hand-computed EMA chain.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from xillion.core.events import Bar
from xillion.engine import indicators as ind


def _bars(ohlcs: list[tuple[float, float, float, float]]) -> list[Bar]:
    ts = datetime(2026, 1, 1)
    out = []
    for i, (o, h, lo, c) in enumerate(ohlcs):
        out.append(
            Bar(
                symbol="X",
                timeframe="1d",
                ts=ts + timedelta(days=i),
                open=Decimal(str(o)),
                high=Decimal(str(h)),
                low=Decimal(str(lo)),
                close=Decimal(str(c)),
                volume=1000,
            )
        )
    return out


def test_sma_hand_checked():
    assert ind.sma([1, 2, 3, 4, 5], 3) == pytest.approx(4.0)  # (3+4+5)/3
    assert ind.sma([1, 2], 3) is None  # not enough data


def test_ema_hand_checked():
    # period=3 -> k=0.5: 1, 1.5, 2.25, 3.125, 4.0625
    assert ind.ema([1, 2, 3, 4, 5], 3) == pytest.approx(4.0625)
    assert ind.ema([1, 2], 3) is None


def test_rsi_hand_checked():
    # changes [2,-1,2,-1,2] -> gains sum 6 (avg 1.2), losses sum 2 (avg 0.4)
    # rs=3.0 -> rsi = 100 - 100/4 = 75.0
    assert ind.rsi([10, 12, 11, 13, 12, 14], 5) == pytest.approx(75.0)


def test_rsi_all_gains_is_100():
    assert ind.rsi(list(range(1, 12)), 10) == pytest.approx(100.0)


def test_rsi_not_enough_data():
    assert ind.rsi([1, 2, 3], 10) is None


def test_atr_hand_checked():
    bars = _bars(
        [
            (9, 10, 8, 9),
            (8, 9, 7, 8),  # TR = max(9-7, |9-9|, |7-9|) = 2
            (9, 13, 9, 12),  # TR = max(13-9, |13-8|, |9-8|) = 5
        ]
    )
    assert ind.atr(bars, 2) == pytest.approx(3.5)  # (2+5)/2
    assert ind.atr(bars, 5) is None


def test_vwap_hand_checked():
    bars = _bars([(10, 10, 10, 10), (10, 10, 10, 20)])
    # equal weight closes normally, but volume differs per bar via _bars (all 1000) -> plain average
    assert ind.vwap(bars, 2) == pytest.approx(15.0)


def test_bollinger_hand_checked():
    lower, mid, upper = ind.bollinger([1, 2, 3, 4, 5], 5, num_std=2.0)
    assert mid == pytest.approx(3.0)
    assert lower == pytest.approx(3.0 - 2 * (2**0.5))
    assert upper == pytest.approx(3.0 + 2 * (2**0.5))


def test_bollinger_not_enough_data():
    assert ind.bollinger([1, 2], 5) is None


def test_macd_matches_its_own_ema_composition():
    closes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    fast, slow, signal = 3, 6, 2
    line, sig, hist = ind.macd(closes, fast, slow, signal)

    fast_series = ind.ema_series(closes, fast)
    slow_series = ind.ema_series(closes, slow)
    macd_series = [f - s for f, s in zip(fast_series, slow_series, strict=False)]
    expected_signal_series = ind.ema_series(macd_series, signal)

    assert line == pytest.approx(macd_series[-1])
    assert sig == pytest.approx(expected_signal_series[-1])
    assert hist == pytest.approx(line - sig)


def test_macd_not_enough_data():
    assert ind.macd([1, 2, 3], fast=12, slow=26, signal=9) is None


def test_supertrend_uptrend_stays_below_price():
    # Steadily rising closes with tight ranges -> supertrend should read "up"
    # with its value sitting below the current close (support line).
    bars = _bars([(100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(30)])
    value, trend = ind.supertrend(bars, period=10, multiplier=2.0)
    assert trend == "up"
    assert value < float(bars[-1].close)


def test_supertrend_downtrend_stays_above_price():
    bars = _bars([(100 - i, 101 - i, 99 - i, 99.5 - i) for i in range(30)])
    value, trend = ind.supertrend(bars, period=10, multiplier=2.0)
    assert trend == "down"
    assert value > float(bars[-1].close)


def test_supertrend_not_enough_data():
    assert ind.supertrend(_bars([(1, 2, 0, 1)] * 3), period=10) is None

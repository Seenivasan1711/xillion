"""
Technical indicators shared by every condition-based strategy (CP5) --
pure functions over plain float lists or Bar lists, so they're trivially
hand-checkable and reusable outside any particular strategy's on_bar loop.

RSI here is deliberately the same simple (non-Wilder) formula
strategies/rsi_threshold_alert.py already used before this module existed --
introducing a second, differently-smoothed RSI would silently change that
strategy's signals if it were ever switched to import this one. Everything
else is new with CP5's condition builder.
"""
from typing import Optional

from xillion.core.events import Bar


def sma(closes: list[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def ema_series(values: list[float], period: int) -> list[float]:
    """Full EMA series -- needed internally because EMA is recursive (each
    value depends on the previous EMA), not a fixed window like SMA."""
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def ema(closes: list[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    return ema_series(closes, period)[-1]


def rsi(closes: list[float], period: int) -> Optional[float]:
    """Simple (non-Wilder) RSI over the last `period` changes in `closes`."""
    if len(closes) < period + 1:
        return None
    window = closes[-(period + 1):]
    changes = [window[i] - window[i - 1] for i in range(1, len(window))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def true_range_series(bars: list[Bar]) -> list[float]:
    trs = []
    for i in range(1, len(bars)):
        high, low = float(bars[i].high), float(bars[i].low)
        prev_close = float(bars[i - 1].close)
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return trs


def atr(bars: list[Bar], period: int) -> Optional[float]:
    """Average True Range -- simple (unweighted) mean of the last `period`
    true ranges, consistent with this module's non-Wilder RSI choice."""
    trs = true_range_series(bars)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def vwap(bars: list[Bar], period: int) -> Optional[float]:
    """Rolling volume-weighted average price over the last `period` bars.
    Not session-anchored (a true VWAP resets at the start of each trading
    day) -- that needs the market-calendar session boundaries CP10 will
    thread through the platform. This is the honest approximation until
    then: good enough for a condition check, not for an execution benchmark."""
    if len(bars) < period:
        return None
    window = bars[-period:]
    total_volume = sum(b.volume for b in window)
    if total_volume == 0:
        return None
    return sum(float(b.close) * b.volume for b in window) / total_volume


def bollinger(closes: list[float], period: int, num_std: float = 2.0) -> Optional[tuple[float, float, float]]:
    """Returns (lower, mid, upper)."""
    if len(closes) < period:
        return None
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((c - mid) ** 2 for c in window) / period
    std = variance ** 0.5
    return (mid - num_std * std, mid, mid + num_std * std)


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> Optional[tuple[float, float, float]]:
    """Returns (macd_line, signal_line, histogram)."""
    if len(closes) < slow + signal:
        return None
    fast_ema = ema_series(closes, fast)
    slow_ema = ema_series(closes, slow)
    macd_line_series = [f - s for f, s in zip(fast_ema, slow_ema)]
    signal_series = ema_series(macd_line_series, signal)
    macd_line = macd_line_series[-1]
    signal_line = signal_series[-1]
    return (macd_line, signal_line, macd_line - signal_line)


def supertrend(bars: list[Bar], period: int = 10, multiplier: float = 3.0) -> Optional[tuple[float, str]]:
    """Returns (supertrend_value, trend) where trend is 'up' or 'down'.
    Recomputed from scratch over the given window each call (not
    incrementally maintained) -- fine for the lookback windows
    ConditionStrategy asks for."""
    trs = true_range_series(bars)
    if len(trs) < period:
        return None

    atr_series: list[Optional[float]] = []
    for i in range(len(trs)):
        atr_series.append(sum(trs[i - period + 1:i + 1]) / period if i + 1 >= period else None)

    trend = "up"
    prev_upper: Optional[float] = None
    prev_lower: Optional[float] = None
    st_value: Optional[float] = None

    for i in range(1, len(bars)):
        atr_val = atr_series[i - 1]
        if atr_val is None:
            continue
        high, low, close = float(bars[i].high), float(bars[i].low), float(bars[i].close)
        prev_close = float(bars[i - 1].close)
        hl2 = (high + low) / 2
        basic_upper = hl2 + multiplier * atr_val
        basic_lower = hl2 - multiplier * atr_val

        if prev_upper is None:
            final_upper, final_lower = basic_upper, basic_lower
        else:
            final_upper = basic_upper if (basic_upper < prev_upper or prev_close > prev_upper) else prev_upper
            final_lower = basic_lower if (basic_lower > prev_lower or prev_close < prev_lower) else prev_lower

        if st_value is None:
            trend = "up" if close > final_upper else "down"
        elif trend == "up":
            trend = "down" if close < final_lower else "up"
        else:
            trend = "up" if close > final_upper else "down"

        st_value = final_lower if trend == "up" else final_upper
        prev_upper, prev_lower = final_upper, final_lower

    if st_value is None:
        return None
    return (st_value, trend)

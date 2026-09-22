"""
Indicator signal calculators -- the CONFIDENCE layer, not the primary
trigger, per Rakesh's explicit direction (2026-09-22): "keep the best
indicator things as well just in case for better confident level markup
later." These are the same indicators v1's shortlist (01_shortlist.md) led
with directly (VWAP sigma-bands, EMA, ADX, ATR, RSI, Bollinger-width) --
kept here as independently-callable building blocks a strategy (or a
future LLM/JEV orchestrator) can compose into a confidence score
(confidence.py), rather than discarded just because none of the v2
strategies use them as the primary entry trigger anymore.

Every method is a pure function of the bars it's given -- no hidden state,
no dependency on another method having run first.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar


@dataclass(frozen=True)
class VwapBandResult:
    vwap: float
    std_dev: float
    sigma_distance: float  # how many std-devs the last close is from VWAP (signed)


class IndicatorSignals:
    def vwap_sigma_bands(self, bars: list[Bar]) -> VwapBandResult:
        """Session VWAP + its rolling standard deviation, computed over
        `bars` as given (caller passes only the current session's bars for
        a true session VWAP -- this method doesn't do session-boundary
        detection itself, matching every other method's "pure function of
        what you hand it" contract)."""
        if not bars:
            return VwapBandResult(vwap=0.0, std_dev=0.0, sigma_distance=0.0)
        typical = [(b.high + b.low + b.close) / 3.0 for b in bars]
        volumes = [max(b.volume, 1e-9) for b in bars]
        total_vol = sum(volumes)
        vwap = sum(t * v for t, v in zip(typical, volumes, strict=True)) / total_vol
        variance = sum(v * (t - vwap) ** 2 for t, v in zip(typical, volumes, strict=True)) / total_vol
        std_dev = variance**0.5
        last_close = bars[-1].close
        sigma_distance = (last_close - vwap) / std_dev if std_dev > 0 else 0.0
        return VwapBandResult(vwap=vwap, std_dev=std_dev, sigma_distance=sigma_distance)

    def ema(self, bars: list[Bar], period: int) -> float:
        """Standard exponential moving average of closes, seeded with a
        simple average of the first `period` bars."""
        closes = [b.close for b in bars]
        if len(closes) < period:
            return closes[-1] if closes else 0.0
        k = 2.0 / (period + 1)
        ema_val = sum(closes[:period]) / period
        for c in closes[period:]:
            ema_val = c * k + ema_val * (1 - k)
        return ema_val

    def atr(self, bars: list[Bar], period: int = 14) -> float:
        """Wilder's ATR: average of the last `period` true ranges."""
        if len(bars) < period + 1:
            return 0.0
        trs = []
        for i in range(len(bars) - period, len(bars)):
            prev_close = bars[i - 1].close
            b = bars[i]
            tr = max(b.high - b.low, abs(b.high - prev_close), abs(b.low - prev_close))
            trs.append(tr)
        return sum(trs) / len(trs)

    def atr_percentile(self, bars: list[Bar], period: int = 14, lookback: int = 100) -> float:
        """Where the CURRENT ATR(period) ranks (0.0-1.0) against the
        distribution of ATR values over the trailing `lookback` bars --
        the "ATR percentile terciles" input the cost model's
        `vol_bucket_for()` and several strategies' confidence layers need."""
        if len(bars) < period + lookback:
            return 0.5  # not enough history -- neutral default, not a guess dressed as data
        history = []
        for end in range(len(bars) - lookback, len(bars) + 1):
            history.append(self.atr(bars[:end], period))
        current = history[-1]
        if not history or max(history) == min(history):
            return 0.5
        rank = sum(1 for v in history if v <= current) / len(history)
        return rank

    def bollinger_width_percentile(
        self, bars: list[Bar], period: int = 20, std_mult: float = 2.0, lookback: int = 100
    ) -> float:
        """Bollinger Band width (as a fraction of the mid price) percentile
        rank against its own trailing `lookback`-bar history -- candidate
        #4/#5's "squeeze" confirmation input."""
        if len(bars) < period + lookback:
            return 0.5
        widths = []
        for end in range(len(bars) - lookback, len(bars) + 1):
            window = bars[end - period : end]
            if len(window) < period:
                continue
            closes = [b.close for b in window]
            mean = sum(closes) / period
            variance = sum((c - mean) ** 2 for c in closes) / period
            std = variance**0.5
            width = (2 * std_mult * std) / mean if mean else 0.0
            widths.append(width)
        if not widths:
            return 0.5
        current = widths[-1]
        rank = sum(1 for w in widths if w <= current) / len(widths)
        return rank

    def rsi(self, bars: list[Bar], period: int = 14) -> float:
        """Standard Wilder RSI, 0-100."""
        if len(bars) < period + 1:
            return 50.0
        closes = [b.close for b in bars[-(period + 1) :]]
        gains, losses = [], []
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i - 1]
            gains.append(max(delta, 0.0))
            losses.append(max(-delta, 0.0))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def rsi_divergence(
        self, bars: list[Bar], touch_index_a: int, touch_index_b: int, period: int = 14
    ) -> float:
        """Signed RSI difference between two named bar indices (e.g. two
        touches of an equal-highs/lows level, candidate #10's hard gate, or
        the two ends of a liquidity run, candidate #9's confidence input).
        Positive = RSI at index B is higher than at index A. Caller
        interprets sign/direction against price direction to call it a
        real divergence -- this method just computes the two RSI readings
        and their difference, it doesn't itself decide "is this bearish or
        bullish," since that depends on which one is a high-sweep vs.
        low-sweep (the caller's context, not this method's)."""
        if touch_index_a >= len(bars) or touch_index_b >= len(bars):
            return 0.0
        rsi_a = self.rsi(bars[: touch_index_a + 1], period)
        rsi_b = self.rsi(bars[: touch_index_b + 1], period)
        return rsi_b - rsi_a

    def adx(self, bars: list[Bar], period: int = 14) -> float:
        """Wilder's ADX -- trend strength, 0-100, direction-agnostic. Used
        across nearly every candidate's confidence layer as a chop/trend
        regime filter input (low ADX = chop, high ADX = trend)."""
        if len(bars) < period * 2:
            return 0.0
        plus_dm, minus_dm, trs = [], [], []
        for i in range(1, len(bars)):
            up_move = bars[i].high - bars[i - 1].high
            down_move = bars[i - 1].low - bars[i].low
            plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
            minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
            prev_close = bars[i - 1].close
            trs.append(max(bars[i].high - bars[i].low, abs(bars[i].high - prev_close), abs(bars[i].low - prev_close)))

        def _wilder_smooth(values: list[float], period: int) -> list[float]:
            smoothed = [sum(values[:period])]
            for v in values[period:]:
                smoothed.append(smoothed[-1] - smoothed[-1] / period + v)
            return smoothed

        smoothed_tr = _wilder_smooth(trs, period)
        smoothed_plus_dm = _wilder_smooth(plus_dm, period)
        smoothed_minus_dm = _wilder_smooth(minus_dm, period)

        dx_values = []
        for tr, pdm, mdm in zip(smoothed_tr, smoothed_plus_dm, smoothed_minus_dm, strict=True):
            if tr == 0:
                dx_values.append(0.0)
                continue
            plus_di = 100 * (pdm / tr)
            minus_di = 100 * (mdm / tr)
            di_sum = plus_di + minus_di
            dx_values.append(100 * abs(plus_di - minus_di) / di_sum if di_sum > 0 else 0.0)

        if len(dx_values) < period:
            return sum(dx_values) / len(dx_values) if dx_values else 0.0
        return sum(dx_values[-period:]) / period

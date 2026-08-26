"""
Tick -> Bar aggregation for live/paper mode (CP9). Before this, nothing
called MarketDataBus.publish_bar() outside a backtest replay -- every
on_bar-based strategy (most of them: RSI Threshold, Condition Strategy,
SMA Cross) correctly subscribed via StrategyRunner.start()'s
subscribe_bars(), but nothing on the publishing side ever fired, so those
strategies sat completely idle in live/paper mode, forever, with no error.

Event-driven, not timer-driven: a bar closes when the FIRST tick of the
*next* bucket arrives, not on a wall-clock schedule. This is correct and
simple for a liquid instrument (ticks arrive well within any bucket), but
means a bar can sit open indefinitely if ticks stop arriving entirely
(illiquid instrument, or a feed outage) -- a known, deliberate scope
boundary, not silently pretended away. A timer-based sweep would close
that gap; not built here.
"""

from datetime import UTC, datetime
from decimal import Decimal

from xillion.core.events import Bar, Tick
from xillion.data.bus import MarketDataBus

# Only the timeframes the platform actually offers elsewhere (Backtest.tsx's
# dropdown, strategy_class.default_timeframe) -- an unrecognised timeframe
# string is skipped rather than guessed at.
_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "1d": 86400,
}


def _bucket_start(ts: datetime, seconds: int) -> datetime:
    epoch = int(ts.timestamp())
    bucket_epoch = epoch - (epoch % seconds)
    return datetime.fromtimestamp(bucket_epoch, tz=UTC)


class _BarAccumulator:
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        bucket_start: datetime,
        price: Decimal,
        cumulative_volume: int | None,
    ) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.bucket_start = bucket_start
        self.open = price
        self.high = price
        self.low = price
        self.close = price
        # Broker ticks (verified against Zerodha's KiteTicker shape) report
        # CUMULATIVE volume for the trading day, not a per-tick trade size --
        # summing raw tick.volume across ticks would wildly overstate a
        # bar's volume. Track first/last cumulative and take the delta.
        self._first_cumulative = cumulative_volume
        self._last_cumulative = cumulative_volume

    def update(self, price: Decimal, cumulative_volume: int | None) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        if cumulative_volume is not None:
            self._last_cumulative = cumulative_volume

    def to_bar(self) -> Bar:
        volume = 0
        if self._first_cumulative is not None and self._last_cumulative is not None:
            volume = max(0, self._last_cumulative - self._first_cumulative)
        return Bar(
            symbol=self.symbol,
            timeframe=self.timeframe,
            ts=self.bucket_start,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=volume,
        )


class BarAggregator:
    """Feed every live tick through on_tick(); when a (symbol, timeframe)
    bucket closes, publishes the finished Bar on the bus. Timeframes are
    driven by whatever's actually subscribed at the moment a tick arrives
    (bus.subscribed_bar_timeframes), so this needs no knowledge of
    strategies or instances -- add a new timeframe subscription and the
    next tick starts aggregating it automatically."""

    def __init__(self, bus: MarketDataBus) -> None:
        self._bus = bus
        self._accumulators: dict[tuple[str, str], _BarAccumulator] = {}

    async def on_tick(self, tick: Tick) -> None:
        timeframes = self._bus.subscribed_bar_timeframes(tick.symbol)
        for tf in timeframes:
            seconds = _TIMEFRAME_SECONDS.get(tf)
            if seconds is None:
                continue
            bucket = _bucket_start(tick.ltt, seconds)
            key = (tick.symbol, tf)
            acc = self._accumulators.get(key)

            if acc is None:
                self._accumulators[key] = _BarAccumulator(
                    tick.symbol, tf, bucket, tick.ltp, tick.volume
                )
                continue

            if bucket > acc.bucket_start:
                finished = acc.to_bar()
                self._accumulators[key] = _BarAccumulator(
                    tick.symbol, tf, bucket, tick.ltp, tick.volume
                )
                await self._bus.publish_bar(finished)
            elif bucket == acc.bucket_start:
                acc.update(tick.ltp, tick.volume)
            # bucket < acc.bucket_start: an out-of-order/late tick -- ignored
            # rather than reopening an already-closed bar.

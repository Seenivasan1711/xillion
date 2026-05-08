"""
Tick-to-bar aggregator. Consumes ticks from the data bus and emits closed bars
at configured timeframes. Handles multiple symbols and timeframes concurrently.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import structlog

from xillion.core.events import Bar, Tick

logger = structlog.get_logger(__name__)

TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "10m": 600,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "1d": 86400,
}


def _bar_open_time(ts: datetime, tf_seconds: int) -> datetime:
    """Round ts down to the nearest bar-open time for the given timeframe."""
    epoch = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
    epoch_ts = int(epoch.timestamp())
    bar_ts = (epoch_ts // tf_seconds) * tf_seconds
    return datetime.fromtimestamp(bar_ts, tz=timezone.utc)


class _PartialBar:
    def __init__(self, symbol: str, timeframe: str, open_time: datetime, price: Decimal) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self.open_time = open_time
        self.open = price
        self.high = price
        self.low = price
        self.close = price
        self.volume: int = 0

    def update(self, price: Decimal, volume: int = 0) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume

    def to_bar(self) -> Bar:
        return Bar(
            symbol=self.symbol,
            timeframe=self.timeframe,
            ts=self.open_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


class TickAggregator:
    """
    Aggregates ticks into bars. For each (symbol, timeframe) subscription,
    maintains a partial bar and emits a closed Bar when the period ends.
    """

    def __init__(self) -> None:
        # (symbol, timeframe) -> PartialBar
        self._partials: dict[tuple[str, str], _PartialBar] = {}
        self._subscriptions: dict[str, set[str]] = {}  # symbol -> set of timeframes

    def subscribe(self, symbol: str, timeframe: str) -> None:
        if timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(f"Unknown timeframe: {timeframe}. Known: {list(TIMEFRAME_SECONDS)}")
        self._subscriptions.setdefault(symbol, set()).add(timeframe)

    async def on_tick(self, tick: Tick) -> list[Bar]:
        """Process a tick and return any bars that just closed."""
        timeframes = self._subscriptions.get(tick.symbol, set())
        closed_bars: list[Bar] = []

        for tf in timeframes:
            tf_seconds = TIMEFRAME_SECONDS[tf]
            bar_open = _bar_open_time(tick.ltt, tf_seconds)
            key = (tick.symbol, tf)
            partial = self._partials.get(key)

            if partial is None:
                # First tick for this symbol+timeframe
                self._partials[key] = _PartialBar(tick.symbol, tf, bar_open, tick.ltp)
            elif bar_open > partial.open_time:
                # Bar boundary crossed — emit the closed bar, start a new one
                closed_bars.append(partial.to_bar())
                self._partials[key] = _PartialBar(tick.symbol, tf, bar_open, tick.ltp)
            else:
                partial.update(tick.ltp, volume=tick.volume or 0)

        return closed_bars

    def get_partial_bar(self, symbol: str, timeframe: str) -> Optional[_PartialBar]:
        return self._partials.get((symbol, timeframe))

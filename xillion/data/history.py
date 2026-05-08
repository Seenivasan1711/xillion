"""
Historical data manager: fetches bars from the DB or broker and caches them.
In backtest mode, the data is loaded upfront. In live mode, it's fetched on demand.
"""
from datetime import datetime
from typing import Optional

import structlog

from xillion.core.events import Bar

logger = structlog.get_logger(__name__)


class HistoryManager:
    """
    Provides historical bar data to strategies via ctx.history().
    Wraps the DB repository with optional broker fallback.
    """

    def __init__(self, repository=None, broker=None) -> None:
        self._repo = repository
        self._broker = broker
        # In-memory cache: (symbol, timeframe) -> sorted list[Bar]
        self._cache: dict[tuple[str, str], list[Bar]] = {}

    def preload(self, symbol: str, timeframe: str, bars: list[Bar]) -> None:
        """Load bars directly (used by backtest engine)."""
        key = (symbol, timeframe)
        sorted_bars = sorted(bars, key=lambda b: b.ts)
        self._cache[key] = sorted_bars
        logger.debug("history preloaded", symbol=symbol, tf=timeframe, count=len(sorted_bars))

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        lookback: int,
        as_of: Optional[datetime] = None,
    ) -> list[Bar]:
        """
        Return up to `lookback` bars for (symbol, timeframe) ending at `as_of`.
        `as_of` is None in live mode (means now), and the simulated current time in backtest.
        """
        key = (symbol, timeframe)
        bars = self._cache.get(key, [])

        if as_of is not None:
            bars = [b for b in bars if b.ts < as_of]

        return bars[-lookback:] if lookback < len(bars) else bars

    def add_bar(self, bar: Bar) -> None:
        key = (bar.symbol, bar.timeframe)
        if key not in self._cache:
            self._cache[key] = []
        cache = self._cache[key]
        if not cache or bar.ts > cache[-1].ts:
            cache.append(bar)
        elif bar.ts == cache[-1].ts:
            cache[-1] = bar

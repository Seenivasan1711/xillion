"""
Historical data manager: fetches bars from the DB or broker and caches them.
In backtest mode, the data is loaded upfront. In live mode, it's fetched on demand.
"""

from datetime import datetime, timedelta

import structlog

from xillion.core.events import Bar

logger = structlog.get_logger(__name__)


class HistoryManager:
    """
    Provides historical bar data to strategies via ctx.history().
    Wraps the DB repository with optional broker fallback.
    """

    def __init__(self, repository=None, broker=None, exchange: str = "NSE") -> None:
        self._repo = repository
        self._broker = broker
        # NOTE: single exchange for the whole manager, defaulting to "NSE" --
        # matches the exchange hardcoding elsewhere in the live path (see
        # docs/status/task-tracker.md CP10). An options instance trading NFO
        # won't get a DB backfill until that's threaded through properly;
        # it just falls back to in-memory-only bars, same as before this.
        self._exchange = exchange
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
        as_of: datetime | None = None,
    ) -> list[Bar]:
        """
        Return up to `lookback` bars for (symbol, timeframe) ending at `as_of`.
        `as_of` is None in live mode (means now), and the simulated current time in backtest.

        If the in-memory cache doesn't have `lookback` bars yet (e.g. a
        strategy just started and wants a 200-bar SMA), and a `repository`
        was supplied, backfill from the DB warehouse so the strategy isn't
        silently starved for its first `lookback` live ticks.
        """
        key = (symbol, timeframe)
        bars = self._cache.get(key, [])

        if as_of is not None:
            bars = [b for b in bars if b.ts < as_of]

        if len(bars) >= lookback or self._repo is None:
            return bars[-lookback:] if lookback < len(bars) else bars

        earliest = bars[0].ts if bars else (as_of or datetime.utcnow())
        db_bars = await self._repo.get_bars(
            symbol,
            timeframe,
            from_ts=datetime.min,
            to_ts=earliest - timedelta(microseconds=1),
            exchange=self._exchange,
        )
        merged = db_bars + bars  # db_bars end strictly before the in-memory tail starts
        return merged[-lookback:] if lookback < len(merged) else merged

    def add_bar(self, bar: Bar) -> None:
        key = (bar.symbol, bar.timeframe)
        if key not in self._cache:
            self._cache[key] = []
        cache = self._cache[key]
        if not cache or bar.ts > cache[-1].ts:
            cache.append(bar)
        elif bar.ts == cache[-1].ts:
            cache[-1] = bar

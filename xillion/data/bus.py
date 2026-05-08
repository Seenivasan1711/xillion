"""
Market Data Bus: an in-process pub/sub layer.
Strategies subscribe to (symbol, timeframe) topics and receive Bar/Tick events.
In live/paper mode the broker plugin publishes ticks; in backtest the
backtest broker publishes historical bars in order.
"""
import asyncio
from collections import defaultdict
from typing import Callable, Coroutine

import structlog

from xillion.core.events import Bar, Tick

logger = structlog.get_logger(__name__)

TickHandler = Callable[[Tick], Coroutine]
BarHandler = Callable[[Bar], Coroutine]


class MarketDataBus:
    def __init__(self) -> None:
        # symbol -> list of async handlers
        self._tick_subscribers: dict[str, list[TickHandler]] = defaultdict(list)
        # (symbol, timeframe) -> list of async handlers
        self._bar_subscribers: dict[tuple[str, str], list[BarHandler]] = defaultdict(list)

    def subscribe_ticks(self, symbol: str, handler: TickHandler) -> None:
        self._tick_subscribers[symbol].append(handler)

    def unsubscribe_ticks(self, symbol: str, handler: TickHandler) -> None:
        subs = self._tick_subscribers.get(symbol, [])
        if handler in subs:
            subs.remove(handler)

    def subscribe_bars(self, symbol: str, timeframe: str, handler: BarHandler) -> None:
        self._bar_subscribers[(symbol, timeframe)].append(handler)

    def unsubscribe_bars(self, symbol: str, timeframe: str, handler: BarHandler) -> None:
        key = (symbol, timeframe)
        subs = self._bar_subscribers.get(key, [])
        if handler in subs:
            subs.remove(handler)

    async def publish_tick(self, tick: Tick) -> None:
        handlers = self._tick_subscribers.get(tick.symbol, [])
        if handlers:
            await asyncio.gather(*(h(tick) for h in handlers), return_exceptions=True)

    async def publish_bar(self, bar: Bar) -> None:
        handlers = self._bar_subscribers.get((bar.symbol, bar.timeframe), [])
        if handlers:
            results = await asyncio.gather(*(h(bar) for h in handlers), return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(
                        "strategy on_bar raised exception",
                        symbol=bar.symbol,
                        timeframe=bar.timeframe,
                        error=str(result),
                    )

    def subscribed_symbols(self) -> set[str]:
        tick_syms = set(self._tick_subscribers.keys())
        bar_syms = {sym for sym, _ in self._bar_subscribers.keys()}
        return tick_syms | bar_syms

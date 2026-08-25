"""
Self-healing + self-failure alerting for the long-running background tasks
started in xillion/main.py's lifespan (tick broadcaster, daily refreshes,
the market-hours scheduler, log persistence). asyncio.create_task()
silently swallows an unhandled exception unless something awaits the task
or checks .exception() -- before this, if one of those loops died
mid-session (a bug, an unexpected None, a transient network blip), the
system would just stop doing that thing with zero visible symptom until
the user happened to notice live prices had gone stale or an instance
stopped trading.

supervise() restarts a dead task automatically (bounded: a crash-looping
task gives up after max_restarts within window_seconds rather than
spinning forever) and Telegram-alerts on every restart and on giving up,
so a self-healed blip is still visible, not just silently absorbed.
"""
import asyncio
import time
import traceback
from typing import Callable, Coroutine, Optional

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_MAX_RESTARTS = 5
_DEFAULT_WINDOW_SECONDS = 600.0
_DEFAULT_BACKOFF_SECONDS = 30.0


class SupervisedTask:
    """Handle for a self-healing background task. cancel() stops it for
    good (no further restarts) -- used on process shutdown, same call
    shape as a bare asyncio.Task so main.py's existing `*_task.cancel()`
    shutdown calls didn't need to change."""

    def __init__(
        self,
        name: str,
        coro_factory: Callable[[], Coroutine],
        notifier=None,
        max_restarts: int = _DEFAULT_MAX_RESTARTS,
        window_seconds: float = _DEFAULT_WINDOW_SECONDS,
        backoff_seconds: float = _DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        self._name = name
        self._coro_factory = coro_factory
        self._notifier = notifier
        self._max_restarts = max_restarts
        self._window_seconds = window_seconds
        self._backoff_seconds = backoff_seconds
        self._restart_times: list[float] = []
        self._stopped = False
        self._task: Optional[asyncio.Task] = None
        self._start()

    def _start(self) -> None:
        self._task = asyncio.create_task(self._coro_factory())
        self._task.add_done_callback(self._on_done)

    def _on_done(self, t: asyncio.Task) -> None:
        if self._stopped or t.cancelled():
            return

        exc = t.exception()
        # Deliberately treats a clean return as a failure too, not just an
        # unhandled exception: these loops are meant to run forever (a
        # `while True` or an unbounded `async for`), and some of them (e.g.
        # _tick_broadcaster) already swallow their own exceptions and just
        # return -- exception-only detection would miss that case entirely.
        detail = str(exc) if exc is not None else "it exited without raising -- this loop is meant to run forever"
        # str(exc) alone (e.g. "cannot reuse already awaited coroutine")
        # gives no file/line to act on -- capture the full traceback so a
        # crash is diagnosable from the Dev/Logs page alone, without needing
        # to reproduce it.
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc is not None else None
        logger.error("background task stopped", task=self._name, error=detail, traceback=tb)

        now = time.monotonic()
        self._restart_times = [ts for ts in self._restart_times if now - ts < self._window_seconds]
        self._restart_times.append(now)

        if len(self._restart_times) > self._max_restarts:
            logger.error("background task exceeded restart budget -- giving up", task=self._name)
            self._notify(
                title=f"{self._name} gave up",
                body=(
                    f"Crashed {len(self._restart_times)} times in "
                    f"{int(self._window_seconds)}s ({detail}). Not retrying again -- "
                    "restart the process to recover."
                ),
            )
            return

        self._notify(
            title=f"{self._name} restarting",
            body=(
                f"Crashed: {detail}. Restarting in {int(self._backoff_seconds)}s "
                f"(attempt {len(self._restart_times)}/{self._max_restarts})."
            ),
        )
        asyncio.create_task(self._delayed_restart())

    async def _delayed_restart(self) -> None:
        await asyncio.sleep(self._backoff_seconds)
        if not self._stopped:
            self._start()

    def _notify(self, title: str, body: str) -> None:
        if self._notifier is not None:
            asyncio.create_task(self._notifier.alert(title=title, body=body, severity="critical"))

    def cancel(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()


def supervise(
    name: str,
    coro_factory: Callable[[], Coroutine],
    notifier=None,
    max_restarts: int = _DEFAULT_MAX_RESTARTS,
    window_seconds: float = _DEFAULT_WINDOW_SECONDS,
    backoff_seconds: float = _DEFAULT_BACKOFF_SECONDS,
) -> SupervisedTask:
    """`coro_factory` must be a zero-arg callable that returns a *fresh*
    coroutine each call (e.g. `lambda: _daily_token_refresh(app)`), not a
    bare coroutine -- a coroutine object can only be awaited once, so
    restarting requires being able to build a new one."""
    return SupervisedTask(name, coro_factory, notifier, max_restarts, window_seconds, backoff_seconds)

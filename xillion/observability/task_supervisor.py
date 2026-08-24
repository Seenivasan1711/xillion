"""
Self-failure alerting for the long-running background tasks started in
xillion/main.py's lifespan (tick broadcaster, daily refreshes, the
market-hours scheduler, log persistence). asyncio.create_task() silently
swallows an unhandled exception unless something awaits the task or checks
.exception() -- before this, if one of those loops died mid-session (a bug,
an unexpected None, whatever), the system would just stop doing that thing
with zero visible symptom until the user happened to notice live prices had
gone stale or an instance stopped trading. This does NOT restart the task
(that's CP10's self-healing scope) -- it only makes the failure loud.
"""
import asyncio

import structlog

logger = structlog.get_logger(__name__)


def supervise(name: str, coro, notifier=None) -> asyncio.Task:
    """Wrap a background coroutine that's meant to run forever (a `while
    True` loop or an unbounded `async for`) so any exit that isn't a clean
    cancellation on shutdown gets logged and, if a notifier is available,
    sent to Telegram immediately.

    Deliberately alerts on a clean return, not just an unhandled exception:
    _tick_broadcaster's own try/except already swallows both
    CancelledError and any other Exception internally and just returns --
    the most likely real failure (the broker's tick stream ending on a WS
    disconnect) would never surface as a Task exception at all, only as
    the loop quietly stopping. An infinite loop returning at all is itself
    the anomaly worth reporting, regardless of whether it raised."""
    task = asyncio.create_task(coro)

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            detail = str(exc)
            logger.error("background task died", task=name, error=detail)
        else:
            detail = "it exited without raising -- this loop is meant to run forever"
            logger.error("background task stopped unexpectedly", task=name)
        if notifier is not None:
            asyncio.create_task(notifier.alert(
                title=f"{name} stopped working",
                body=f"Background task stopped: {detail}. It will not restart on its own until the process is restarted.",
                severity="critical",
            ))

    task.add_done_callback(_on_done)
    return task

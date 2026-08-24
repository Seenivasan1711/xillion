"""
Self-healing + self-failure alerting for background tasks (CP9 alerting,
CP10 restart): asyncio.create_task() silently swallows an unhandled
exception unless something checks .exception() -- supervise() makes that
loud instead of silent, restarts the task automatically (bounded, so a
crash-looping task doesn't spin forever), and crucially also treats a
*clean* return from a task meant to run forever as an anomaly worth
reporting (see xillion/observability/task_supervisor.py's docstring for
why: _tick_broadcaster's own try/except already swallows its own errors
and just returns, so exception-only detection would miss the most likely
real failure).
"""
import asyncio

import pytest

from xillion.observability.task_supervisor import supervise


class _FakeNotifier:
    def __init__(self):
        self.alerts: list[dict] = []

    async def alert(self, title, body, severity="info"):
        self.alerts.append({"title": title, "body": body, "severity": severity})


async def _settle(n=5):
    # Let pending callbacks/scheduled tasks (including ones that schedule
    # further tasks, like the alert-then-restart chain) actually run.
    for _ in range(n):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_a_task_that_raises_triggers_an_alert_and_restarts():
    notifier = _FakeNotifier()
    calls = 0

    async def _factory():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("disk full")
        await asyncio.sleep(100)  # second attempt: stays "running"

    supervised = supervise("test_task", _factory, notifier=notifier, backoff_seconds=0.01)
    await _settle()
    await asyncio.sleep(0.02)
    await _settle()

    assert calls == 2  # restarted once
    assert len(notifier.alerts) == 1
    assert "test_task" in notifier.alerts[0]["title"]
    assert "restarting" in notifier.alerts[0]["title"]
    assert "disk full" in notifier.alerts[0]["body"]
    assert notifier.alerts[0]["severity"] == "critical"

    supervised.cancel()


@pytest.mark.asyncio
async def test_a_task_that_returns_cleanly_still_triggers_a_restart():
    """The loop was supposed to run forever -- returning at all, even
    without an exception, means something stopped it."""
    notifier = _FakeNotifier()
    calls = 0

    async def _factory():
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        await asyncio.sleep(100)

    supervised = supervise("quiet_task", _factory, notifier=notifier, backoff_seconds=0.01)
    await _settle()
    await asyncio.sleep(0.02)
    await _settle()

    assert calls == 2
    assert len(notifier.alerts) == 1
    assert "quiet_task" in notifier.alerts[0]["title"]

    supervised.cancel()


@pytest.mark.asyncio
async def test_a_cancelled_task_does_not_trigger_an_alert_or_restart():
    """Cancellation on shutdown is the normal, expected way these tasks
    end -- it must never page anyone or spawn a replacement."""
    notifier = _FakeNotifier()
    calls = 0

    async def _factory():
        nonlocal calls
        calls += 1
        await asyncio.sleep(100)

    supervised = supervise("forever_task", _factory, notifier=notifier, backoff_seconds=0.01)
    await asyncio.sleep(0)
    supervised.cancel()
    await _settle()
    await asyncio.sleep(0.02)
    await _settle()

    assert calls == 1  # never restarted
    assert notifier.alerts == []


@pytest.mark.asyncio
async def test_supervision_works_with_no_notifier_configured():
    """Telegram not configured (common in dev, or before the user sets it
    up) must not crash the supervisor itself -- it should still log and
    still restart."""
    async def _boom():
        raise RuntimeError("boom")

    supervised = supervise("no_notifier_task", _boom, notifier=None, backoff_seconds=0.01)
    await _settle()
    await asyncio.sleep(0.02)
    await _settle()  # must not raise

    supervised.cancel()


@pytest.mark.asyncio
async def test_a_crash_looping_task_gives_up_after_the_restart_budget():
    notifier = _FakeNotifier()
    calls = 0

    async def _always_boom():
        nonlocal calls
        calls += 1
        raise RuntimeError(f"boom {calls}")

    supervise(
        "looping_task", _always_boom, notifier=notifier,
        max_restarts=2, window_seconds=600, backoff_seconds=0.01,
    )

    # Drain enough restart cycles to exceed the budget (max_restarts=2).
    for _ in range(6):
        await _settle()
        await asyncio.sleep(0.02)

    # 1 initial run + up to max_restarts restarts, then it gives up and
    # stops calling the factory entirely.
    assert calls <= 3
    final_call_count = calls
    await _settle()
    await asyncio.sleep(0.05)
    await _settle()
    assert calls == final_call_count  # no further attempts after giving up

    titles = [a["title"] for a in notifier.alerts]
    assert any("gave up" in t for t in titles)


@pytest.mark.asyncio
async def test_giving_up_alert_explains_it_will_not_retry():
    notifier = _FakeNotifier()

    async def _always_boom():
        raise RuntimeError("boom")

    supervise(
        "looping_task_2", _always_boom, notifier=notifier,
        max_restarts=1, window_seconds=600, backoff_seconds=0.01,
    )

    for _ in range(6):
        await _settle()
        await asyncio.sleep(0.02)

    give_up_alerts = [a for a in notifier.alerts if "gave up" in a["title"]]
    assert len(give_up_alerts) == 1
    assert "restart the process" in give_up_alerts[0]["body"]

"""
Self-failure alerting for background tasks (CP9): asyncio.create_task()
silently swallows an unhandled exception unless something checks
.exception() -- supervise() makes that loud instead of silent, and
crucially also treats a *clean* return from a task meant to run forever as
an anomaly worth reporting (see xillion/observability/task_supervisor.py's
docstring for why: _tick_broadcaster's own try/except already swallows its
own errors and just returns, so exception-only detection would miss the
most likely real failure).
"""
import asyncio

import pytest

from xillion.observability.task_supervisor import supervise


class _FakeNotifier:
    def __init__(self):
        self.alerts: list[dict] = []

    async def alert(self, title, body, severity="info"):
        self.alerts.append({"title": title, "body": body, "severity": severity})


async def _settle():
    # Let the task run, finish, and its done-callback (which itself
    # schedules a task for the alert) fire and complete.
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_a_task_that_raises_triggers_an_alert():
    notifier = _FakeNotifier()

    async def _boom():
        raise RuntimeError("disk full")

    supervise("test_task", _boom(), notifier=notifier)
    await _settle()

    assert len(notifier.alerts) == 1
    assert "test_task" in notifier.alerts[0]["title"]
    assert "disk full" in notifier.alerts[0]["body"]
    assert notifier.alerts[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_a_task_that_returns_cleanly_still_triggers_an_alert():
    """The loop was supposed to run forever -- returning at all, even
    without an exception, means something stopped it."""
    notifier = _FakeNotifier()

    async def _returns_quietly():
        return None

    supervise("quiet_task", _returns_quietly(), notifier=notifier)
    await _settle()

    assert len(notifier.alerts) == 1
    assert "quiet_task" in notifier.alerts[0]["title"]


@pytest.mark.asyncio
async def test_a_cancelled_task_does_not_trigger_an_alert():
    """Cancellation on shutdown is the normal, expected way these tasks
    end -- it must never page anyone."""
    notifier = _FakeNotifier()

    async def _runs_forever():
        await asyncio.sleep(100)

    task = supervise("forever_task", _runs_forever(), notifier=notifier)
    await asyncio.sleep(0)
    task.cancel()
    await _settle()

    assert notifier.alerts == []


@pytest.mark.asyncio
async def test_supervision_works_with_no_notifier_configured():
    """Telegram not configured (common in dev, or before the user sets it
    up) must not crash the supervisor itself -- it should still log."""
    async def _boom():
        raise RuntimeError("boom")

    supervise("no_notifier_task", _boom(), notifier=None)
    await _settle()  # must not raise

"""
capture_processor (CP9): every structlog event app-wide gets funneled
through this before it's console-rendered. It must never raise or block a
log call -- see xillion/observability/log_capture.py's docstring for why
(it runs synchronously on every logger.info/.warning/etc call in the app).
"""
import asyncio

import pytest

from xillion.observability import log_capture


@pytest.fixture(autouse=True)
def _reset_queue():
    log_capture._queue = None
    yield
    log_capture._queue = None


def test_event_is_enqueued_with_expected_shape():
    result = log_capture.capture_processor(
        None, "info", {"event": "something happened", "module": "strategy_engine", "foo": "bar"}
    )
    assert result == {"event": "something happened", "module": "strategy_engine", "foo": "bar"}  # unchanged, passed through

    entry = log_capture._get_queue().get_nowait()
    assert entry["level"] == "info"
    assert entry["source"] == "strategy_engine"
    assert entry["message"] == "something happened"
    assert entry["fields"] == {"foo": "bar"}
    assert "ts" in entry


def test_missing_module_falls_back_to_system_source():
    log_capture.capture_processor(None, "warning", {"event": "no module here"})
    entry = log_capture._get_queue().get_nowait()
    assert entry["source"] == "system"


def test_a_full_queue_drops_the_entry_without_raising():
    log_capture._queue = asyncio.Queue(maxsize=1)
    log_capture.capture_processor(None, "info", {"event": "first"})
    # Queue is now full (maxsize=1) -- the second call must not raise.
    log_capture.capture_processor(None, "info", {"event": "second, dropped"})

    assert log_capture._get_queue().qsize() == 1
    assert log_capture._get_queue().get_nowait()["message"] == "first"


def test_capture_processor_never_raises_even_with_no_event_loop():
    """This is called from ordinary sync code paths across the app -- the
    first call may need to create the queue before any event loop is
    guaranteed running for this thread. asyncio.Queue() itself doesn't
    require a running loop to construct, but this test pins that
    assumption so a future asyncio change can't silently break logging
    app-wide."""
    log_capture._queue = None
    result = log_capture.capture_processor(None, "error", {"event": "boom"})
    assert result is not None  # processor chain must continue regardless

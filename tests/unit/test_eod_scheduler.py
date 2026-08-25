"""CP14 scheduler timing + connected-broker discovery."""
from datetime import datetime, time, timedelta

from xillion.engine.eod_scheduler import IST, _connected_brokers, _next_occurrence


def test_next_occurrence_same_day_when_target_is_later():
    now = datetime(2026, 8, 25, 10, 0, tzinfo=IST)
    target = time(15, 15)
    result = _next_occurrence(now, target)
    assert result == datetime(2026, 8, 25, 15, 15, tzinfo=IST)


def test_next_occurrence_rolls_to_next_day_when_target_already_passed():
    now = datetime(2026, 8, 25, 16, 0, tzinfo=IST)
    target = time(15, 15)
    result = _next_occurrence(now, target)
    assert result == datetime(2026, 8, 26, 15, 15, tzinfo=IST)


def test_next_occurrence_rolls_over_when_exactly_at_target():
    now = datetime(2026, 8, 25, 15, 15, tzinfo=IST)
    target = time(15, 15)
    result = _next_occurrence(now, target)
    assert result == datetime(2026, 8, 26, 15, 15, tzinfo=IST)


class _FakeApp:
    class State:
        pass
    def __init__(self, broker_instances):
        self.state = self.State()
        self.state.broker_instances = broker_instances


async def test_connected_brokers_skips_entries_with_no_instance():
    app = _FakeApp({
        "Zerodha Primary": {"instance": "fake-broker-1", "status": "connected"},
        "Dhan Primary": {"instance": None, "status": "failed"},
    })
    result = await _connected_brokers(app)
    assert result == [("Zerodha Primary", "fake-broker-1")]


async def test_connected_brokers_empty_when_none_connected():
    app = _FakeApp({})
    result = await _connected_brokers(app)
    assert result == []

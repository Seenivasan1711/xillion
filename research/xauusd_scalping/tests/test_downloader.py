"""download_dukascopy.py integrity fixes, 2026-09-24 (08_correction_history #19).

No network: the HTTP client and sleep are faked."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

_PATH = Path(__file__).resolve().parent.parent / "data" / "download_dukascopy.py"
_spec = importlib.util.spec_from_file_location("download_dukascopy", _PATH)
dl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dl)


class _Resp:
    def __init__(self, status, content=b"x"):
        self.status_code = status
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Client:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0

    def get(self, *a, **k):
        self.calls += 1
        return _Resp(self.statuses.pop(0))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(dl.time, "sleep", lambda s: None)


def test_503_throttling_is_retried_not_recorded_as_failed():
    """Previously a single 503 raised immediately -> hour marked failed forever."""
    client = _Client([503, 503, 200])
    assert dl._fetch_hour(client, "EURUSD", datetime(2026, 3, 10, 9, tzinfo=UTC)) == b"x"
    assert client.calls == 3


def test_persistent_503_still_fails_after_bounded_retries():
    client = _Client([503] * 10)
    with pytest.raises(RuntimeError, match="503"):
        dl._fetch_hour(client, "EURUSD", datetime(2026, 3, 10, 9, tzinfo=UTC))
    assert client.calls == 1 + len(dl._THROTTLE_RETRY_DELAYS)


def test_404_is_an_empty_hour_without_retry():
    client = _Client([404])
    assert dl._fetch_hour(client, "EURUSD", datetime(2026, 3, 7, 9, tzinfo=UTC)) == b""
    assert client.calls == 1


def test_only_saturday_is_skipped():
    assert dl._market_closed(datetime(2026, 3, 7, 12, tzinfo=UTC))  # Saturday
    assert not dl._market_closed(datetime(2026, 3, 6, 23, tzinfo=UTC))  # Friday night
    assert not dl._market_closed(datetime(2026, 3, 8, 23, tzinfo=UTC))  # Sunday open


def test_reconcile_unmarks_completed_hours_with_no_bars_on_disk(tmp_path, monkeypatch):
    """The mid-day-kill case: 10h and 11h marked completed, only 10h on disk."""
    monkeypatch.setattr(dl, "_data_dir", lambda symbol: tmp_path)
    ts = pd.date_range("2026-03-10 10:00", periods=60, freq="1min", tz="UTC")
    pd.DataFrame({"ts": ts, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0.0}).to_parquet(
        tmp_path / "EURUSD_2026-03.parquet", index=False
    )
    manifest = {
        "completed_hours": ["EURUSD_2026-03-10T10", "EURUSD_2026-03-10T11"],
        "empty_hours": [],
        "failed_hours": [],
    }
    assert dl._reconcile_manifest("EURUSD", manifest) == 1
    assert manifest["completed_hours"] == ["EURUSD_2026-03-10T10"]


def test_pacing_backs_off_on_throttle_and_eases_back():
    assert dl._next_delay(2.5, 2.5, throttled=True, streak=0) == 5.0
    assert dl._next_delay(40.0, 2.5, throttled=True, streak=0) == dl._MAX_DELAY_SECONDS
    assert dl._next_delay(5.0, 2.5, throttled=False, streak=5) == 5.0  # not yet
    assert dl._next_delay(5.0, 2.5, throttled=False, streak=20) == 4.0
    assert dl._next_delay(2.5, 2.5, throttled=False, streak=20) == 2.5  # floor at base


def test_throttle_event_is_counted_for_pacing():
    dl._throttle_events = 0
    dl._fetch_hour(_Client([503, 200]), "EURUSD", datetime(2026, 3, 10, 9, tzinfo=UTC))
    assert dl._throttle_events == 1

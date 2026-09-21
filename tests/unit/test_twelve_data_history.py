"""
TwelveDataHistoryProvider (Gold Sweep-Reversal's Stage 2 backtest data
source) -- response shape and chunking verified live against the real API
2026-09-21 (5-min XAUUSD bars fetched successfully back to 2021; a
multi-chunk 40-day range produced correctly ordered, deduplicated bars
with no gaps). No network calls here -- httpx is stubbed.
"""

from datetime import UTC, date, datetime

import httpx
import pytest

from data_providers.twelve_data_history import TwelveDataHistoryProvider


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload


def _stub_get(responses, monkeypatch, calls: list | None = None):
    """`responses` is either a single payload (reused every call) or a
    list of payloads consumed in order (for chunking tests)."""
    state = {"i": 0}

    async def _fake_get(self, url, params=None):
        if calls is not None:
            calls.append(dict(params or {}))
        if isinstance(responses, list):
            payload = responses[min(state["i"], len(responses) - 1)]
            state["i"] += 1
        else:
            payload = responses
        return _FakeResponse(payload)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)


@pytest.mark.asyncio
async def test_fetch_bars_parses_time_series_response(monkeypatch):
    _stub_get(
        {
            "status": "ok",
            "values": [
                {
                    "datetime": "2026-01-02 00:05:00",
                    "open": "2005.0",
                    "high": "2015.0",
                    "low": "2000.0",
                    "close": "2010.0",
                },
                {
                    "datetime": "2026-01-02 00:00:00",
                    "open": "2000.0",
                    "high": "2010.0",
                    "low": "1990.0",
                    "close": "2005.0",
                },
            ],
        },
        monkeypatch,
    )

    provider = TwelveDataHistoryProvider()
    bars = await provider.fetch_bars(
        "XAUUSD",
        "FX",
        "5m",
        from_date=date(2026, 1, 2),
        to_date=date(2026, 1, 2),
        credentials={"api_key": "test-key"},
    )

    assert len(bars) == 2
    # Sorted ascending regardless of the API's own (newest-first) order.
    assert bars[0].ts == datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
    assert bars[1].ts == datetime(2026, 1, 2, 0, 5, tzinfo=UTC)
    assert bars[0].open == 2000
    assert bars[0].volume == 0


@pytest.mark.asyncio
async def test_missing_api_key_raises_clear_error():
    provider = TwelveDataHistoryProvider()
    with pytest.raises(ValueError, match="API key"):
        await provider.fetch_bars(
            "XAUUSD",
            "FX",
            "5m",
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 2),
            credentials=None,
        )


@pytest.mark.asyncio
async def test_unsupported_timeframe_rejected():
    provider = TwelveDataHistoryProvider()
    with pytest.raises(ValueError, match="timeframe"):
        await provider.fetch_bars(
            "XAUUSD",
            "FX",
            "1s",
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 2),
            credentials={"api_key": "test-key"},
        )


@pytest.mark.asyncio
async def test_no_data_error_treated_as_a_gap_not_fatal(monkeypatch):
    _stub_get(
        {"status": "error", "message": "No data is available on the specified dates."},
        monkeypatch,
    )
    provider = TwelveDataHistoryProvider()
    bars = await provider.fetch_bars(
        "XAUUSD",
        "FX",
        "5m",
        from_date=date(2019, 1, 1),
        to_date=date(2019, 1, 2),
        credentials={"api_key": "test-key"},
    )
    assert bars == []


@pytest.mark.asyncio
async def test_real_api_error_raises(monkeypatch):
    _stub_get({"status": "error", "message": "Invalid API key"}, monkeypatch)
    provider = TwelveDataHistoryProvider()
    with pytest.raises(RuntimeError, match="Invalid API key"):
        await provider.fetch_bars(
            "XAUUSD",
            "FX",
            "5m",
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 2),
            credentials={"api_key": "test-key"},
        )


@pytest.mark.asyncio
async def test_multi_chunk_range_makes_multiple_paced_calls(monkeypatch):
    sleep_calls = []

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr("asyncio.sleep", _fake_sleep)

    call_params: list = []
    _stub_get(
        {
            "status": "ok",
            "values": [
                {
                    "datetime": "2026-01-01 00:00:00",
                    "open": "2000.0",
                    "high": "2000.0",
                    "low": "2000.0",
                    "close": "2000.0",
                }
            ],
        },
        monkeypatch,
        calls=call_params,
    )

    provider = TwelveDataHistoryProvider()
    # A range wide enough to force multiple 5-min chunks (~17 days/chunk).
    await provider.fetch_bars(
        "XAUUSD",
        "FX",
        "5m",
        from_date=date(2026, 1, 1),
        to_date=date(2026, 3, 1),
        credentials={"api_key": "test-key"},
    )

    assert len(call_params) > 1  # genuinely chunked, not one giant call
    assert len(sleep_calls) == len(call_params) - 1  # paced between calls, not before the first
    assert all(s == pytest.approx(8.0) for s in sleep_calls)


@pytest.mark.asyncio
async def test_duplicate_timestamps_across_chunk_seams_are_deduped(monkeypatch):
    # Both "chunks" return the same bar -- simulates the overlap at a
    # chunk boundary seen in the real API.
    payload = {
        "status": "ok",
        "values": [
            {
                "datetime": "2026-01-01 00:00:00",
                "open": "2000.0",
                "high": "2000.0",
                "low": "2000.0",
                "close": "2000.0",
            }
        ],
    }

    async def _fake_sleep(seconds):
        pass

    monkeypatch.setattr("asyncio.sleep", _fake_sleep)
    _stub_get(payload, monkeypatch)

    provider = TwelveDataHistoryProvider()
    bars = await provider.fetch_bars(
        "XAUUSD",
        "FX",
        "5m",
        from_date=date(2026, 1, 1),
        to_date=date(2026, 3, 1),
        credentials={"api_key": "test-key"},
    )
    timestamps = [b.ts for b in bars]
    assert len(timestamps) == len(set(timestamps))

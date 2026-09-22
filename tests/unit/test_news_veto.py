"""
StrategyContext.news_veto_active() (2026-09-22, Gold Sweep-Reversal's
ritual check). Confirmed live against the real Finnhub API that the free
tier returns 403 on /calendar/economic -- these tests stub httpx, they
don't hit the network, but the 403-handling behavior they check is exactly
what that live confirmation showed actually happens.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from xillion.core.execution import ExecutionRouter
from xillion.core.risk import RiskManager
from xillion.data.history import HistoryManager
from xillion.engine.strategy_engine import _StrategyContextImpl


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def _make_ctx() -> _StrategyContextImpl:
    router = ExecutionRouter(broker=None, risk_manager=RiskManager())
    history = HistoryManager()
    return _StrategyContextImpl(
        instance_id="test-instance",
        instance_name="Test Instance",
        mode="alert",
        capital_allocated=Decimal("5000"),
        params={},
        execution_router=router,
        history_manager=history,
    )


@pytest.mark.asyncio
async def test_no_api_key_returns_false_without_network_call(monkeypatch):
    monkeypatch.setattr("xillion.auth.credstore.load_finnhub_api_key", lambda: _async_return(""))
    called = {"n": 0}

    async def _fake_get(self, url, params=None, timeout=None):
        called["n"] += 1
        return _FakeResponse(200, {"economicCalendar": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    ctx = _make_ctx()
    assert await ctx.news_veto_active() is False
    assert called["n"] == 0


async def _async_return(value):
    return value


@pytest.mark.asyncio
async def test_403_fails_open_and_caches_for_the_day(monkeypatch):
    monkeypatch.setattr(
        "xillion.auth.credstore.load_finnhub_api_key", lambda: _async_return("fake-key")
    )
    calls = {"n": 0}

    async def _fake_get(self, url, params=None, timeout=None):
        calls["n"] += 1
        return _FakeResponse(403, {"error": "You don't have access to this resource."})

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    ctx = _make_ctx()
    assert await ctx.news_veto_active() is False
    assert calls["n"] == 1

    # Second call the same (simulated) day shouldn't hit the network again --
    # already confirmed unavailable, no reason to keep asking.
    assert await ctx.news_veto_active() is False
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_high_impact_us_event_within_15_minutes_vetoes(monkeypatch):
    monkeypatch.setattr(
        "xillion.auth.credstore.load_finnhub_api_key", lambda: _async_return("fake-key")
    )
    soon = (datetime.now(UTC) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")

    async def _fake_get(self, url, params=None, timeout=None):
        return _FakeResponse(
            200,
            {
                "economicCalendar": [
                    {"impact": "high", "country": "US", "time": soon},
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    ctx = _make_ctx()
    assert await ctx.news_veto_active() is True


@pytest.mark.asyncio
async def test_distant_or_low_impact_events_do_not_veto(monkeypatch):
    monkeypatch.setattr(
        "xillion.auth.credstore.load_finnhub_api_key", lambda: _async_return("fake-key")
    )
    far_away = (datetime.now(UTC) + timedelta(hours=5)).isoformat().replace("+00:00", "Z")
    soon_low_impact = (datetime.now(UTC) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")

    async def _fake_get(self, url, params=None, timeout=None):
        return _FakeResponse(
            200,
            {
                "economicCalendar": [
                    {"impact": "high", "country": "US", "time": far_away},
                    {"impact": "low", "country": "US", "time": soon_low_impact},
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    ctx = _make_ctx()
    assert await ctx.news_veto_active() is False

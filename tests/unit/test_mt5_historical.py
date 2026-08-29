"""
Gold Lane B1 backtest data source (2026-08-29): the MT5 bridge's on-demand
historical-request queue (xillion/api/mt5_bridge.py's poll()/historical_
report() extensions, MT5HistoricalRequest, migration 019). Same "no real
MT5 terminal in this environment" position as test_mt5_broker.py -- these
exercise the exact DB read/mutate logic the API handlers perform, same
direct-function-call convention as every other API test in this session
(no HTTP TestClient layer needed to prove the contract).
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI

from brokers.mt5_funding_pips import MT5FundingPipsBroker
from xillion.api.mt5_bridge import HistoricalReportBody, ReportBar, historical_report, poll
from xillion.db.models import AppUser, MT5HistoricalRequest
from xillion.db.session import get_session_factory, init_db


def _user() -> AppUser:
    return AppUser(
        id=1, username="test-user", password_hash="x", created_at=datetime.now(UTC).isoformat()
    )


class _FakeRequest:
    def __init__(self, app: FastAPI):
        self.app = app


async def _app_with_broker(connection_name: str) -> FastAPI:
    app = FastAPI()
    broker = MT5FundingPipsBroker(connection_name=connection_name)
    await broker.connect({})
    app.state.broker_instances = {
        connection_name: {"name": connection_name, "instance": broker, "status": "connected"}
    }
    return app


async def _seed_request(
    connection_name: str, symbol: str = "XAUUSD", status: str = "PENDING"
) -> int:
    factory = get_session_factory()
    now = datetime.now(UTC).isoformat()
    async with factory() as db:
        row = MT5HistoricalRequest(
            broker_connection_name=connection_name,
            symbol=symbol,
            timeframe="1d",
            from_date="2026-01-01",
            to_date="2026-01-31",
            status=status,
            requested_at=now,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


@pytest.mark.asyncio
async def test_poll_returns_a_pending_historical_request():
    await init_db()
    app = await _app_with_broker("MT5 Hist Poll Test")
    await _seed_request("MT5 Hist Poll Test")

    result = await poll("MT5 Hist Poll Test", _FakeRequest(app), _user())

    assert len(result["historical_requests"]) == 1
    assert result["historical_requests"][0]["symbol"] == "XAUUSD"
    assert result["historical_requests"][0]["from_date"] == "2026-01-01"


@pytest.mark.asyncio
async def test_poll_does_not_return_an_already_done_request():
    await init_db()
    app = await _app_with_broker("MT5 Hist Poll Done Test")
    await _seed_request("MT5 Hist Poll Done Test", status="DONE")

    result = await poll("MT5 Hist Poll Done Test", _FakeRequest(app), _user())

    assert result["historical_requests"] == []


@pytest.mark.asyncio
async def test_poll_isolates_by_connection_name():
    await init_db()
    app = await _app_with_broker("MT5 Hist Poll Isolated Test")
    await _seed_request("MT5 Hist Poll Other Connection")

    result = await poll("MT5 Hist Poll Isolated Test", _FakeRequest(app), _user())

    assert result["historical_requests"] == []


@pytest.mark.asyncio
async def test_poll_leaves_the_request_pending_not_acked():
    """Unlike orders (must never execute twice), a historical fetch is
    idempotent -- leaving it PENDING (not flipping to some intermediate
    state) means a bridge restart mid-fetch just re-fetches on its next
    poll instead of the request getting stuck forever with nothing ever
    picking it up again."""
    await init_db()
    app = await _app_with_broker("MT5 Hist Poll Idempotent Test")
    request_id = await _seed_request("MT5 Hist Poll Idempotent Test")

    await poll("MT5 Hist Poll Idempotent Test", _FakeRequest(app), _user())

    factory = get_session_factory()
    async with factory() as db:
        row = await db.get(MT5HistoricalRequest, request_id)
        assert row.status == "PENDING"


@pytest.mark.asyncio
async def test_historical_report_marks_done_with_bars():
    await init_db()
    request_id = await _seed_request("MT5 Hist Report Test")

    body = HistoricalReportBody(
        request_id=request_id,
        status="DONE",
        bars=[
            ReportBar(ts="2026-01-02T00:00:00", open="2000", high="2010", low="1990", close="2005"),
        ],
    )
    result = await historical_report(body, _user())

    assert result == {"status": "ok"}
    factory = get_session_factory()
    async with factory() as db:
        row = await db.get(MT5HistoricalRequest, request_id)
        assert row.status == "DONE"
        assert '"open": "2000"' in row.bars_json
        assert row.completed_at is not None


@pytest.mark.asyncio
async def test_historical_report_marks_failed_with_error_message():
    await init_db()
    request_id = await _seed_request("MT5 Hist Report Fail Test")

    body = HistoricalReportBody(
        request_id=request_id, status="FAILED", error_message="symbol_select failed"
    )
    await historical_report(body, _user())

    factory = get_session_factory()
    async with factory() as db:
        row = await db.get(MT5HistoricalRequest, request_id)
        assert row.status == "FAILED"
        assert row.error_message == "symbol_select failed"


@pytest.mark.asyncio
async def test_historical_report_on_unknown_request_id_does_not_raise():
    """Stale report for a request this backend no longer tracks (e.g.
    restarted since the bridge picked it up) -- same 'ignore, don't
    crash' stance /report already takes for an unknown fill."""
    await init_db()

    body = HistoricalReportBody(request_id=999999, status="DONE", bars=[])
    result = await historical_report(body, _user())

    assert result == {"status": "ok"}

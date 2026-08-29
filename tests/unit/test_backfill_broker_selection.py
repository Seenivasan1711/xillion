"""
POST /data/backfill's broker-selection logic (xillion/api/data.py's
start_backfill(), 2026-08-29 fix): a requires_broker provider used to get
"whichever connected broker happens to be first in dict iteration order",
correct only by coincidence when Kite was the only such provider and
Zerodha the only broker anyone had connected. Found while adding a SECOND
requires_broker provider (MT5 Bridge (Gold)) -- with two brokers connected
at once, the old logic could hand a provider the wrong instance entirely.
required_broker_name now pins each provider to the specific broker CLASS
it actually needs.
"""

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from xillion.api.data import BackfillRequest, start_backfill
from xillion.core.data_provider_base import DataProviderCapabilities, HistoricalDataProvider
from xillion.db.models import AppUser
from xillion.db.session import init_db


class _PinnedProvider(HistoricalDataProvider):
    name = "Pinned Provider Test"
    capabilities = DataProviderCapabilities(
        requires_credentials=False, requires_broker=True, required_broker_name="Zerodha"
    )


class _LooseProvider(HistoricalDataProvider):
    """A provider that never declared required_broker_name -- keeps the
    original looser "any connected broker" behaviour."""

    name = "Loose Provider Test"
    capabilities = DataProviderCapabilities(requires_credentials=False, requires_broker=True)


def _fake_user() -> AppUser:
    from datetime import UTC, datetime

    return AppUser(
        id=1, username="test-user", password_hash="x", created_at=datetime.now(UTC).isoformat()
    )


class _FakeRequest:
    def __init__(self, app: FastAPI):
        self.app = app


def _app_with_two_brokers():
    app = FastAPI()
    zerodha_instance = SimpleNamespace(tag="zerodha")
    mt5_instance = SimpleNamespace(tag="mt5")
    app.state.broker_instances = {
        # Insertion order deliberately puts the WRONG-for-Zerodha broker
        # first, so a fix that just takes next(connected) would fail this.
        "MT5 Funding Pips": {
            "name": "MT5 Funding Pips",
            "broker_name": "MT5 Funding Pips",
            "instance": mt5_instance,
            "status": "connected",
        },
        "Zerodha Primary": {
            "name": "Zerodha Primary",
            "broker_name": "Zerodha",
            "instance": zerodha_instance,
            "status": "connected",
        },
    }
    app.state.backfill_jobs = {}
    app.state.plugin_loader = SimpleNamespace(
        registry=SimpleNamespace(
            data_providers={
                _PinnedProvider.name: _PinnedProvider,
                _LooseProvider.name: _LooseProvider,
            }
        )
    )
    return app, zerodha_instance, mt5_instance


@pytest.mark.asyncio
async def test_a_pinned_provider_gets_its_own_broker_not_whichever_is_first(monkeypatch):
    await init_db()
    app, zerodha_instance, mt5_instance = _app_with_two_brokers()

    captured = {}

    async def _fake_run(app_state, job_id, body, credentials, broker):
        captured["broker"] = broker
        app_state.backfill_jobs[job_id]["status"] = "done"

    monkeypatch.setattr("xillion.api.data._run_backfill_job", _fake_run)

    body = BackfillRequest(
        provider_name=_PinnedProvider.name,
        symbol="XAUUSD",
        exchange="MT5",
        timeframe="1d",
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
    )
    request = _FakeRequest(app)
    from xillion.db.session import get_session_factory

    async with get_session_factory()() as db:
        await start_backfill(body, request, db, _fake_user())

    assert captured["broker"] is zerodha_instance
    assert captured["broker"] is not mt5_instance


@pytest.mark.asyncio
async def test_a_provider_with_no_required_broker_name_keeps_the_old_loose_behaviour(monkeypatch):
    await init_db()
    app, zerodha_instance, mt5_instance = _app_with_two_brokers()

    captured = {}

    async def _fake_run(app_state, job_id, body, credentials, broker):
        captured["broker"] = broker
        app_state.backfill_jobs[job_id]["status"] = "done"

    monkeypatch.setattr("xillion.api.data._run_backfill_job", _fake_run)

    body = BackfillRequest(
        provider_name=_LooseProvider.name,
        symbol="XAUUSD",
        exchange="MT5",
        timeframe="1d",
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
    )
    request = _FakeRequest(app)
    from xillion.db.session import get_session_factory

    async with get_session_factory()() as db:
        await start_backfill(body, request, db, _fake_user())

    assert captured["broker"] in (zerodha_instance, mt5_instance)


@pytest.mark.asyncio
async def test_pinned_provider_errors_clearly_when_only_the_wrong_broker_is_connected():
    await init_db()
    app = FastAPI()
    app.state.broker_instances = {
        "MT5 Funding Pips": {
            "name": "MT5 Funding Pips",
            "broker_name": "MT5 Funding Pips",
            "instance": SimpleNamespace(),
            "status": "connected",
        }
    }
    app.state.backfill_jobs = {}
    app.state.plugin_loader = SimpleNamespace(
        registry=SimpleNamespace(data_providers={_PinnedProvider.name: _PinnedProvider})
    )
    body = BackfillRequest(
        provider_name=_PinnedProvider.name,
        symbol="XAUUSD",
        exchange="MT5",
        timeframe="1d",
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
    )
    request = _FakeRequest(app)
    from xillion.db.session import get_session_factory

    async with get_session_factory()() as db:
        with pytest.raises(HTTPException) as exc_info:
            await start_backfill(body, request, db, _fake_user())

    assert exc_info.value.status_code == 422
    assert "Zerodha" in exc_info.value.detail

"""
Backfill job orchestration (CP3): _run_backfill_job drives BarWarehouse in
the background and records status on the shared job dict -- this is what
POST /api/data/backfill kicks off via asyncio.create_task.
"""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from xillion.api.data import BackfillRequest, _run_backfill_job
from xillion.core.data_provider_base import DataProviderCapabilities, HistoricalDataProvider
from xillion.core.events import Bar
from xillion.db.session import init_db, init_warehouse_db


class _FakeProvider(HistoricalDataProvider):
    name = "Fake Backfill Provider"
    capabilities = DataProviderCapabilities(requires_credentials=False)

    async def fetch_bars(self, symbol, exchange, timeframe, from_date, to_date, **kw):
        return [
            Bar(
                symbol=symbol,
                timeframe=timeframe,
                ts=datetime.combine(from_date, datetime.min.time()),
                open=Decimal(1),
                high=Decimal(1),
                low=Decimal(1),
                close=Decimal(1),
                volume=1,
            )
        ]


class _FailingProvider(HistoricalDataProvider):
    name = "Failing Backfill Provider"
    capabilities = DataProviderCapabilities(requires_credentials=False)

    async def fetch_bars(self, symbol, exchange, timeframe, from_date, to_date, **kw):
        raise RuntimeError("provider is down")


def _app_state(provider_cls):
    return SimpleNamespace(
        backfill_jobs={"job-1": {"status": "queued"}},
        plugin_loader=SimpleNamespace(
            registry=SimpleNamespace(data_providers={provider_cls.name: provider_cls})
        ),
    )


@pytest.mark.asyncio
async def test_successful_backfill_job_reports_done_with_bar_count():
    await init_db()
    await init_warehouse_db()
    body = BackfillRequest(
        provider_name=_FakeProvider.name,
        symbol="BACKFILL_JOB_SYM",
        exchange="NFO",
        timeframe="1d",
        from_date=date(2026, 8, 3),
        to_date=date(2026, 8, 3),
    )
    state = _app_state(_FakeProvider)

    await _run_backfill_job(state, "job-1", body, credentials=None, broker=None)

    job = state.backfill_jobs["job-1"]
    assert job["status"] == "done"
    assert job["bars_fetched"] == 1
    assert job["finished_at"] is not None


@pytest.mark.asyncio
async def test_failing_provider_reports_failed_status_not_an_unhandled_exception():
    await init_db()
    await init_warehouse_db()
    body = BackfillRequest(
        provider_name=_FailingProvider.name,
        symbol="BACKFILL_JOB_SYM_2",
        exchange="NFO",
        timeframe="1d",
        from_date=date(2026, 8, 3),
        to_date=date(2026, 8, 3),
    )
    state = _app_state(_FailingProvider)

    await _run_backfill_job(state, "job-1", body, credentials=None, broker=None)  # must not raise

    job = state.backfill_jobs["job-1"]
    assert job["status"] == "failed"
    assert "provider is down" in job["error"]

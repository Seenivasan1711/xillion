"""
MT5BridgeHistoryProvider.fetch_bars() (Gold Lane B1 backtest data source,
2026-08-29): enqueues an MT5HistoricalRequest row and polls it until the
bridge (a separate process, not present in this test environment) marks it
DONE/FAILED. Tests here simulate "the bridge" as a concurrent asyncio task
that updates the row directly -- the same DB the real bridge's report
handler would write to -- rather than running a real MT5 terminal. Poll
timing constants are monkeypatched down so these run in milliseconds, not
the real 60s timeout.
"""

import asyncio
import json
from datetime import UTC, datetime

import pytest

from data_providers import mt5_bridge_history
from data_providers.mt5_bridge_history import MT5BridgeHistoryProvider
from xillion.db.models import MT5HistoricalRequest
from xillion.db.session import get_session_factory, init_db


class _FakeBroker:
    _connection_name = "MT5 Provider Test"


async def _simulate_bridge_fulfils_the_request(delay: float = 0.02) -> None:
    """Waits for the request row to appear, then reports it DONE with one
    bar -- standing in for the real bridge's historical-report call."""
    factory = get_session_factory()
    await asyncio.sleep(delay)
    async with factory() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(MT5HistoricalRequest).where(
                MT5HistoricalRequest.broker_connection_name == "MT5 Provider Test"
            )
        )
        row = result.scalars().first()
        assert row is not None, "provider never enqueued a request"
        row.status = "DONE"
        row.bars_json = json.dumps(
            [
                {
                    "ts": "2026-01-02T00:00:00",
                    "open": "2000",
                    "high": "2010",
                    "low": "1990",
                    "close": "2005",
                    "volume": 100,
                }
            ]
        )
        row.completed_at = datetime.now(UTC).isoformat()
        await db.commit()


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch):
    monkeypatch.setattr(mt5_bridge_history, "_POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(mt5_bridge_history, "_POLL_TIMEOUT_SECONDS", 0.5)


def test_capabilities_require_the_mt5_broker_specifically():
    caps = MT5BridgeHistoryProvider.capabilities
    assert caps.requires_broker is True
    assert caps.required_broker_name == "MT5 Funding Pips"


@pytest.mark.asyncio
async def test_fetch_bars_raises_without_a_connected_broker():
    provider = MT5BridgeHistoryProvider()
    with pytest.raises(ValueError, match="needs a connected MT5"):
        await provider.fetch_bars(
            "XAUUSD", "MT5", "1d", datetime(2026, 1, 1).date(), datetime(2026, 1, 31).date()
        )


@pytest.mark.asyncio
async def test_fetch_bars_enqueues_and_returns_bars_once_the_bridge_reports():
    await init_db()
    provider = MT5BridgeHistoryProvider()
    from datetime import date

    fulfil = asyncio.create_task(_simulate_bridge_fulfils_the_request())
    try:
        bars = await provider.fetch_bars(
            "XAUUSD", "MT5", "1d", date(2026, 1, 1), date(2026, 1, 31), broker=_FakeBroker()
        )
    finally:
        await fulfil

    assert len(bars) == 1
    assert bars[0].symbol == "XAUUSD"
    assert str(bars[0].close) == "2005"
    assert bars[0].volume == 100


@pytest.mark.asyncio
async def test_fetch_bars_raises_with_the_bridges_own_error_message():
    await init_db()
    provider = MT5BridgeHistoryProvider()
    from datetime import date

    async def _simulate_bridge_fails(delay: float = 0.02) -> None:
        factory = get_session_factory()
        await asyncio.sleep(delay)
        async with factory() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(MT5HistoricalRequest).where(
                    MT5HistoricalRequest.broker_connection_name == "MT5 Provider Fail Test"
                )
            )
            row = result.scalars().first()
            row.status = "FAILED"
            row.error_message = "symbol_select(XAUUSD) failed: market closed"
            await db.commit()

    class _FailBroker:
        _connection_name = "MT5 Provider Fail Test"

    fulfil = asyncio.create_task(_simulate_bridge_fails())
    try:
        with pytest.raises(RuntimeError, match="market closed"):
            await provider.fetch_bars(
                "XAUUSD", "MT5", "1d", date(2026, 1, 1), date(2026, 1, 31), broker=_FailBroker()
            )
    finally:
        await fulfil


@pytest.mark.asyncio
async def test_fetch_bars_times_out_clearly_when_the_bridge_never_responds():
    await init_db()
    provider = MT5BridgeHistoryProvider()
    from datetime import date

    class _OfflineBridgeBroker:
        _connection_name = "MT5 Provider Offline Test"

    with pytest.raises(RuntimeError, match="did not respond"):
        await provider.fetch_bars(
            "XAUUSD",
            "MT5",
            "1d",
            date(2026, 1, 1),
            date(2026, 1, 31),
            broker=_OfflineBridgeBroker(),
        )

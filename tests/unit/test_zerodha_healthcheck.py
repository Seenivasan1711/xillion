"""
Tests for ZerodhaBroker.healthcheck() reflecting real ticker-socket state,
not just the REST session flag. Does not touch the network -- no real
KiteTicker/KiteConnect calls are made.
"""
import pytest

from brokers.zerodha import ZerodhaBroker


class _StubKite:
    """Stands in for the kiteconnect.KiteConnect client's .profile() call."""

    def profile(self):
        return {"user_id": "TEST"}


@pytest.mark.asyncio
async def test_healthcheck_false_when_never_connected():
    broker = ZerodhaBroker()
    assert await broker.healthcheck() is False


@pytest.mark.asyncio
async def test_healthcheck_true_when_session_valid_and_no_ticker_yet():
    broker = ZerodhaBroker()
    broker._connected = True
    broker._kite = _StubKite()
    # No ticker started yet -- healthcheck should only depend on the REST session.
    assert await broker.healthcheck() is True


@pytest.mark.asyncio
async def test_healthcheck_false_when_ticker_exists_but_socket_disconnected():
    broker = ZerodhaBroker()
    broker._connected = True
    broker._kite = _StubKite()
    broker._ticker = object()  # a ticker exists...
    broker._ticker_connected = False  # ...but its socket is down
    assert await broker.healthcheck() is False


@pytest.mark.asyncio
async def test_healthcheck_true_when_ticker_connected():
    broker = ZerodhaBroker()
    broker._connected = True
    broker._kite = _StubKite()
    broker._ticker = object()
    broker._ticker_connected = True
    assert await broker.healthcheck() is True


@pytest.mark.asyncio
async def test_disconnect_resets_ticker_connected_flag():
    broker = ZerodhaBroker()
    broker._connected = True
    broker._ticker_connected = True
    broker._ticker = None  # avoid touching the real .close() executor path
    await broker.disconnect()
    assert broker._connected is False
    assert broker._ticker_connected is False

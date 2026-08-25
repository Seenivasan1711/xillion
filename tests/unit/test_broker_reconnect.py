"""
POST /brokers/connections/{name}/reconnect used to be hardcoded to
"Zerodha Primary" -- Dhan's own Reconnect button in Settings > Active
connections would 400 even though app.state.broker_instances already
tracks Dhan connections identically to Zerodha's. Found while working on
CP11's GTT follow-up in the same broker-capability area of the codebase.
"""
import pytest
from fastapi import FastAPI, HTTPException

from xillion.api.brokers import reconnect_broker


@pytest.mark.asyncio
async def test_dhan_reconnect_dispatches_to_try_connect_dhan(monkeypatch):
    calls = []

    async def _fake_try_connect_dhan(app):
        calls.append(app)
        app.state.broker_instances["Dhan Primary"]["status"] = "connected"

    monkeypatch.setattr("xillion.main._try_connect_dhan", _fake_try_connect_dhan)

    app = FastAPI()
    app.state.broker_instances = {"Dhan Primary": {"name": "Dhan Primary", "status": "error"}}
    request = type("R", (), {"app": app})()

    result = await reconnect_broker("Dhan Primary", request)

    assert calls == [app]
    assert result == {"name": "Dhan Primary", "status": "connected"}


@pytest.mark.asyncio
async def test_zerodha_reconnect_still_works(monkeypatch):
    calls = []

    async def _fake_try_connect_zerodha(app):
        calls.append(app)

    monkeypatch.setattr("xillion.main._try_connect_zerodha", _fake_try_connect_zerodha)

    app = FastAPI()
    app.state.broker_instances = {"Zerodha Primary": {"name": "Zerodha Primary", "status": "connected"}}
    request = type("R", (), {"app": app})()

    result = await reconnect_broker("Zerodha Primary", request)

    assert calls == [app]
    assert result["name"] == "Zerodha Primary"


@pytest.mark.asyncio
async def test_unknown_connection_name_is_404():
    app = FastAPI()
    app.state.broker_instances = {}
    request = type("R", (), {"app": app})()

    with pytest.raises(HTTPException) as exc_info:
        await reconnect_broker("Nonexistent", request)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_a_connected_but_unsupported_broker_name_is_400_not_a_silent_noop():
    """A connection can exist in broker_instances without a reconnect
    handler yet (e.g. a future broker) -- must fail loudly, not pretend."""
    app = FastAPI()
    app.state.broker_instances = {"Some Future Broker": {"name": "Some Future Broker", "status": "error"}}
    request = type("R", (), {"app": app})()

    with pytest.raises(HTTPException) as exc_info:
        await reconnect_broker("Some Future Broker", request)
    assert exc_info.value.status_code == 400

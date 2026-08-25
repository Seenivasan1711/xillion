"""
Dhan credentials Settings API -- mirrors the pre-existing Zerodha pattern
(xillion/api/settings.py) so multi-broker credentials are stored encrypted
in the DB (xillion.auth.credstore / BrokerCredential table) rather than
only ever being settable via .env, which doesn't work for a system meant
to hold several providers' secrets and let them be added/rotated from the
running app.

_try_connect_dhan is monkeypatched out here -- it makes a real network call
to Dhan's user_profile endpoint to validate the token, which has nothing to
do with what these tests are proving (that credentials round-trip through
encrypted DB storage correctly).
"""
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI

from xillion.api.settings import (
    DhanCredentialsRequest,
    delete_dhan_credentials,
    get_dhan_status,
    put_dhan_credentials,
)
from xillion.auth.credstore import load_credentials
from xillion.db.models import AppUser
from xillion.db.session import get_session_factory, init_db


class _FakeRequest:
    def __init__(self, app: FastAPI):
        self.app = app


def _user() -> AppUser:
    return AppUser(id=1, username="test-user", password_hash="x", created_at=datetime.now(timezone.utc).isoformat())


@pytest.mark.asyncio
async def test_dhan_credentials_round_trip_through_encrypted_db_storage(monkeypatch):
    async def _noop_connect(app):
        pass

    monkeypatch.setattr("xillion.main._try_connect_dhan", _noop_connect)

    await init_db()
    app = FastAPI()
    app.state.broker_instances = {}
    request = _FakeRequest(app)
    user = _user()
    factory = get_session_factory()

    async with factory() as db:
        before = await get_dhan_status(db=db, user=user)
        assert before.configured is False

    async with factory() as db:
        body = DhanCredentialsRequest(client_id="1000000003", access_token="tok-abc", pin="1234", totp_secret="")
        result = await put_dhan_credentials(body, request, db, user)
        assert result["saved"] is True

    async with factory() as db:
        status = await get_dhan_status(db=db, user=user)
        assert status.configured is True
        assert status.client_id == "1000000003"

        creds = await load_credentials(db, "Dhan Primary")
        assert creds["access_token"] == "tok-abc"
        assert creds["pin"] == "1234"

    async with factory() as db:
        deleted = await delete_dhan_credentials(request, db, user)
        assert deleted["deleted"] is True

    async with factory() as db:
        status_after = await get_dhan_status(db=db, user=user)
        assert status_after.configured is False


@pytest.mark.asyncio
async def test_saving_dhan_credentials_does_not_touch_zerodha_credentials(monkeypatch):
    """Regression guard: both credential rows are keyed by connection name
    in the same BrokerCredential table -- a bug here could let one broker's
    save/delete clobber the other's."""
    from xillion.auth.credstore import save_credentials

    async def _noop_connect(app):
        pass

    monkeypatch.setattr("xillion.main._try_connect_dhan", _noop_connect)

    await init_db()
    app = FastAPI()
    app.state.broker_instances = {}
    request = _FakeRequest(app)
    user = _user()
    factory = get_session_factory()

    async with factory() as db:
        await save_credentials(db, "Zerodha Primary", "Zerodha", {"api_key": "zk"})

    async with factory() as db:
        body = DhanCredentialsRequest(client_id="1000000099", access_token="tok-xyz")
        await put_dhan_credentials(body, request, db, user)

    async with factory() as db:
        zerodha_creds = await load_credentials(db, "Zerodha Primary")
        assert zerodha_creds["api_key"] == "zk"

    async with factory() as db:
        await delete_dhan_credentials(request, db, user)

    async with factory() as db:
        zerodha_creds_after = await load_credentials(db, "Zerodha Primary")
        assert zerodha_creds_after["api_key"] == "zk"  # untouched by Dhan delete


@pytest.mark.asyncio
async def test_saving_dhan_broker_credentials_also_configures_the_dhanhq_data_provider(monkeypatch):
    """The Dhan broker (order placement) and the DhanHQ data provider
    (historical bars) both authenticate with the exact same real Dhan API
    token -- before this, saving it under Configuration -> Brokers left
    the Data Providers tab's DhanHQ card asking for the identical client
    ID + access token a second time."""
    from xillion.auth.data_provider_credstore import load_provider_credentials

    async def _noop_connect(app):
        pass

    monkeypatch.setattr("xillion.main._try_connect_dhan", _noop_connect)

    await init_db()
    app = FastAPI()
    app.state.broker_instances = {}
    request = _FakeRequest(app)
    user = _user()
    factory = get_session_factory()

    async with factory() as db:
        body = DhanCredentialsRequest(client_id="1000000003", access_token="tok-abc")
        result = await put_dhan_credentials(body, request, db, user)
        assert result["saved"] is True

    async with factory() as db:
        provider_creds = await load_provider_credentials(db, "DhanHQ")
        assert provider_creds is not None
        assert provider_creds["api_key"] == "tok-abc"        # access token
        assert provider_creds["api_secret"] == "1000000003"  # client ID

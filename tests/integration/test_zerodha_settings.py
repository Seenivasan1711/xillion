"""
Zerodha credentials Settings API -- product_type coverage specifically.

2026-08-29: product type moved from a hardcoded MIS constant in
brokers/zerodha.py to a per-connection, UI-configurable field (Rakesh's own
request, mirroring the same change made to Dhan the same day). No existing
test file covered xillion/api/settings.py's Zerodha endpoints at all before
this -- this file is scoped to proving the new field round-trips correctly
through the same encrypted-DB storage every other credential field already
uses (xillion.auth.credstore / BrokerCredential table), not full CRUD parity
with test_dhan_settings.py.

_try_connect_zerodha is monkeypatched out -- it makes a real network call to
validate the token/attempt login, which has nothing to do with what this is
proving.
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI

from xillion.api.settings import (
    ZerodhaCredentialsRequest,
    get_zerodha_status,
    put_zerodha_credentials,
)
from xillion.auth.credstore import load_credentials
from xillion.db.models import AppUser
from xillion.db.session import get_session_factory, init_db


class _FakeRequest:
    def __init__(self, app: FastAPI):
        self.app = app


def _user() -> AppUser:
    return AppUser(
        id=1, username="test-user", password_hash="x", created_at=datetime.now(UTC).isoformat()
    )


@pytest.mark.asyncio
async def test_product_type_round_trips_and_defaults_to_mis(monkeypatch):
    async def _noop_connect(app):
        pass

    monkeypatch.setattr("xillion.main._try_connect_zerodha", _noop_connect)

    await init_db()
    app = FastAPI()
    app.state.broker_instances = {}
    request = _FakeRequest(app)
    user = _user()
    factory = get_session_factory()

    async with factory() as db:
        body = ZerodhaCredentialsRequest(
            api_key="k", api_secret="s", user_id="AB1234", password="p", totp_secret="t"
        )
        await put_zerodha_credentials(body, request, db, user)

    async with factory() as db:
        status = await get_zerodha_status(db=db, user=user)
        assert status.product_type == "MIS"  # default, not specified above

        creds = await load_credentials(db, "Zerodha Primary")
        assert creds["product_type"] == "MIS"

    async with factory() as db:
        body = ZerodhaCredentialsRequest(
            api_key="k",
            api_secret="s",
            user_id="AB1234",
            password="p",
            totp_secret="t",
            product_type="NRML",
        )
        await put_zerodha_credentials(body, request, db, user)

    async with factory() as db:
        status = await get_zerodha_status(db=db, user=user)
        assert status.product_type == "NRML"

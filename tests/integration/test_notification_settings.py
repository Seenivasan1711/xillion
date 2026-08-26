"""
Telegram notification settings, moved off .env onto the same encrypted DB
storage as Zerodha/Dhan (reusing BrokerCredential -- see the note on
NOTIFICATIONS_NAME in xillion/api/settings.py). Also proves the save path
applies immediately to the running TelegramNotifier without a restart.
"""

from datetime import UTC

import pytest
from fastapi import FastAPI

from xillion.api.settings import NotificationSettings, get_notifications, put_notifications
from xillion.auth.credstore import load_credentials
from xillion.db.session import get_session_factory, init_db
from xillion.notifications.telegram import TelegramNotifier


class _FakeRequest:
    def __init__(self, app: FastAPI):
        self.app = app


def _user():
    from datetime import datetime

    from xillion.db.models import AppUser

    return AppUser(
        id=1, username="test-user", password_hash="x", created_at=datetime.now(UTC).isoformat()
    )


@pytest.mark.asyncio
async def test_notification_settings_round_trip_and_apply_to_live_notifier():
    await init_db()
    app = FastAPI()
    app.state.telegram = TelegramNotifier()  # unconfigured at startup
    request = _FakeRequest(app)
    user = _user()
    factory = get_session_factory()

    async with factory() as db:
        before = await get_notifications(db=db, user=user)
        assert before.telegram_bot_token == ""

    async with factory() as db:
        body = NotificationSettings(
            telegram_bot_token="123:ABC", telegram_chat_id="-100999", on_kill_switch=False
        )
        result = await put_notifications(body, request, db, user)
        assert result["saved"] is True

    # Applied to the live notifier immediately -- no restart needed.
    assert app.state.telegram._token == "123:ABC"
    assert app.state.telegram._chat_id == "-100999"
    assert app.state.telegram._enabled is True

    async with factory() as db:
        status = await get_notifications(db=db, user=user)
        assert status.telegram_bot_token == "123:ABC"
        assert status.on_kill_switch is False
        assert status.on_order_filled is True  # untouched toggles keep their default

        creds = await load_credentials(db, "Telegram")
        assert creds["telegram_chat_id"] == "-100999"

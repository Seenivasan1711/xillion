"""
TelegramNotifier.send_test() -- unlike send()/alert() (which deliberately
swallow every failure so a broken Telegram config never crashes real
alerting/trading code), the "Send test message" button needs to actually
tell the user whether it worked.
"""
import httpx
import pytest

from xillion.notifications.telegram import TelegramNotifier


@pytest.mark.asyncio
async def test_send_test_reports_not_configured_without_token():
    notifier = TelegramNotifier("", "")
    ok, detail = await notifier.send_test()
    assert ok is False
    assert "token" in detail.lower() or "chat" in detail.lower()


@pytest.mark.asyncio
async def test_send_test_reports_success(monkeypatch):
    notifier = TelegramNotifier("fake-token", "12345")

    class _FakeResponse:
        is_success = True
        status_code = 200
        def json(self): return {}

    async def _fake_post(self, url, json, timeout):
        return _FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    ok, detail = await notifier.send_test()
    assert ok is True
    assert detail == "Sent"


@pytest.mark.asyncio
async def test_send_test_reports_telegram_api_error(monkeypatch):
    notifier = TelegramNotifier("bad-token", "12345")

    class _FakeResponse:
        is_success = False
        status_code = 401
        def json(self): return {"description": "Unauthorized"}

    async def _fake_post(self, url, json, timeout):
        return _FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    ok, detail = await notifier.send_test()
    assert ok is False
    assert detail == "Unauthorized"


@pytest.mark.asyncio
async def test_send_test_reports_network_exception(monkeypatch):
    notifier = TelegramNotifier("fake-token", "12345")

    async def _fake_post(self, url, json, timeout):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    ok, detail = await notifier.send_test()
    assert ok is False
    assert "timed out" in detail

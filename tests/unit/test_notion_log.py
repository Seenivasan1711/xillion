"""
notion_log (2026-09-22, SESSION SPRINT item 16): unconfigured is a real
no-op, configured writes look up the database's real title property (not
assumed to be "Name") and post a page, and every failure mode (missing
title property, bad response, exception) is swallowed, never raised -- same
best-effort contract as TelegramNotifier.send() and mongo_context_store.py.
No real Notion API here; httpx is stubbed.
"""

import httpx
import pytest

from xillion.notifications import notion_log


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _reset_title_cache():
    notion_log._title_prop_cache.clear()
    yield
    notion_log._title_prop_cache.clear()


@pytest.fixture(autouse=True)
def _configure(monkeypatch):
    class _FakeSettings:
        notion_api_token = "fake-token"
        notion_database_id = "fake-db-id"

    monkeypatch.setattr(notion_log, "get_settings", lambda: _FakeSettings())


@pytest.mark.asyncio
async def test_no_op_when_unconfigured(monkeypatch):
    class _EmptySettings:
        notion_api_token = ""
        notion_database_id = ""

    monkeypatch.setattr(notion_log, "get_settings", lambda: _EmptySettings())

    calls = {"n": 0}

    async def _fake_get(self, url, headers=None, timeout=None):
        calls["n"] += 1
        return _FakeResponse(200, {})

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    await notion_log.log_action("Test", {"a": 1})
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_finds_real_title_property_and_posts_page(monkeypatch):
    posted = {}

    async def _fake_get(self, url, headers=None, timeout=None):
        return _FakeResponse(
            200, {"properties": {"Entry": {"type": "title"}, "Tags": {"type": "select"}}}
        )

    async def _fake_post(self, url, headers=None, json=None, timeout=None):
        posted["url"] = url
        posted["json"] = json
        return _FakeResponse(200, {"id": "page-1"})

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    await notion_log.log_action("Instance updated: Gold Sweep-Reversal", {"tp_pts": 10.0})

    assert posted["url"].endswith("/pages")
    assert (
        "Entry" in posted["json"]["properties"]
    )  # used the real title prop, not a hardcoded "Name"
    title_text = posted["json"]["properties"]["Entry"]["title"][0]["text"]["content"]
    assert "Instance updated: Gold Sweep-Reversal" in title_text


@pytest.mark.asyncio
async def test_no_title_property_skips_without_raising(monkeypatch):
    async def _fake_get(self, url, headers=None, timeout=None):
        return _FakeResponse(200, {"properties": {"Tags": {"type": "select"}}})

    post_called = {"n": 0}

    async def _fake_post(self, *args, **kwargs):
        post_called["n"] += 1
        return _FakeResponse(200, {})

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    await notion_log.log_action("Test", {"a": 1})
    assert post_called["n"] == 0


@pytest.mark.asyncio
async def test_exception_is_swallowed(monkeypatch):
    async def _fake_get(self, url, headers=None, timeout=None):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    # Must not raise.
    await notion_log.log_action("Test", {"a": 1})

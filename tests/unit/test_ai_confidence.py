"""
Pre-trade AI confidence hook (CP8): disabled by default (no network call at
all), and any failure when configured returns None rather than raising --
a review service being down must never break a real alert.
"""

import httpx
import pytest

from xillion.config import settings
from xillion.notifications.ai_confidence import get_confidence

_ORIGINAL_ASYNC_CLIENT_INIT = httpx.AsyncClient.__init__


def _patch_client_transport(monkeypatch, handler) -> None:
    """Route httpx.AsyncClient(...) to a MockTransport instead of the
    network, using the ORIGINAL __init__ captured at import time -- patching
    via a lambda that calls httpx.AsyncClient.__init__ directly recurses
    forever once that name itself is the patched attribute."""

    def _patched_init(self, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        _ORIGINAL_ASYNC_CLIENT_INIT(self, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)


@pytest.mark.asyncio
async def test_disabled_by_default_makes_no_network_call(monkeypatch):
    monkeypatch.setattr(settings, "ai_confidence_url", "")

    async def _boom(*a, **kw):
        raise AssertionError("should never be called when disabled")

    monkeypatch.setattr(httpx.AsyncClient, "post", _boom)
    result = await get_confidence("NIFTY", "BUY", 100.0, 110.0, 95.0, "tag")
    assert result is None


@pytest.mark.asyncio
async def test_returns_clamped_confidence_on_success(monkeypatch):
    monkeypatch.setattr(settings, "ai_confidence_url", "http://fake/confidence")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"confidence": 150, "reasoning": "overconfident"})

    _patch_client_transport(monkeypatch, handler)
    result = await get_confidence("NIFTY", "BUY", 100.0, 110.0, 95.0, "tag")
    assert result == 100.0  # clamped


@pytest.mark.asyncio
async def test_backend_failure_returns_none_not_raise(monkeypatch):
    monkeypatch.setattr(settings, "ai_confidence_url", "http://fake/confidence")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "server error"})

    _patch_client_transport(monkeypatch, handler)
    result = await get_confidence("NIFTY", "BUY", 100.0, 110.0, 95.0, "tag")
    assert result is None


@pytest.mark.asyncio
async def test_missing_confidence_field_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "ai_confidence_url", "http://fake/confidence")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reasoning": "no score given"})

    _patch_client_transport(monkeypatch, handler)
    result = await get_confidence("NIFTY", "BUY", 100.0, 110.0, 95.0, "tag")
    assert result is None

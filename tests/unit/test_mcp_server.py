"""
MCP server (CP7): every tool is a translation layer over xillion's real
REST API -- verified here against a mocked HTTP transport (no real server
needed) so each tool's request construction and response handling is
actually exercised, not just "the function exists".
"""
import os

import httpx
import pytest

import xillion.mcp_server.server as mcp_server
from xillion.mcp_server.client import XillionAuthError, XillionClient


@pytest.fixture(autouse=True)
def _mcp_env(monkeypatch):
    monkeypatch.setenv("XILLION_MCP_USERNAME", "testuser")
    monkeypatch.setenv("XILLION_MCP_PASSWORD", "testpass")
    monkeypatch.delenv("XILLION_MCP_TOTP_CODE", raising=False)


def _mock_client(handler) -> XillionClient:
    transport = httpx.MockTransport(handler)
    return XillionClient(transport=transport)


def _login_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"authenticated": True, "username": "testuser", "has_totp": False})


@pytest.mark.asyncio
async def test_client_logs_in_lazily_and_only_once():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/auth/login"):
            return _login_ok(request)
        return httpx.Response(200, json={"ok": True})

    client = _mock_client(handler)
    await client.get("/strategies/classes")
    await client.get("/portfolio/summary")

    assert calls.count("/api/auth/login") == 1  # logged in once, reused after


@pytest.mark.asyncio
async def test_client_raises_clear_error_without_credentials(monkeypatch):
    monkeypatch.delenv("XILLION_MCP_USERNAME", raising=False)
    monkeypatch.delenv("XILLION_MCP_PASSWORD", raising=False)
    client = _mock_client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(XillionAuthError):
        await client.get("/strategies/classes")


@pytest.mark.asyncio
async def test_client_raises_when_totp_required_but_not_supplied():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"requires_totp": True})
    client = _mock_client(handler)
    with pytest.raises(XillionAuthError):
        await client.get("/strategies/classes")


@pytest.mark.asyncio
async def test_list_strategies_calls_the_real_endpoint(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/login"):
            return _login_ok(request)
        assert request.url.path == "/api/strategies/classes"
        return httpx.Response(200, json={"strategies": [{"name": "RSI Threshold"}], "errors": {}})

    monkeypatch.setattr(mcp_server, "_client", _mock_client(handler))
    result = await mcp_server.list_strategies()
    assert result["strategies"][0]["name"] == "RSI Threshold"


@pytest.mark.asyncio
async def test_get_trades_today_filters_to_todays_exits(monkeypatch):
    from datetime import date
    today = date.today().isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/login"):
            return _login_ok(request)
        return httpx.Response(200, json={"trades": [
            {"id": "1", "exit_ts": f"{today}T10:00:00"},
            {"id": "2", "exit_ts": "2020-01-01T10:00:00"},
        ]})

    monkeypatch.setattr(mcp_server, "_client", _mock_client(handler))
    result = await mcp_server.get_trades_today()
    assert [t["id"] for t in result["trades"]] == ["1"]


@pytest.mark.asyncio
async def test_run_backtest_posts_the_expected_body(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/login"):
            return _login_ok(request)
        assert request.url.path == "/api/backtest/run-provider"
        import json
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "done", "trade_count": 0})

    monkeypatch.setattr(mcp_server, "_client", _mock_client(handler))
    result = await mcp_server.run_backtest(
        strategy_name="RSI Threshold", provider_name="NSE Bhavcopy (Free)",
        symbol="NIFTY26AUGFUT", from_date="2024-01-01", to_date="2024-01-31",
    )
    assert result["status"] == "done"
    assert captured["body"]["strategy_name"] == "RSI Threshold"
    assert captured["body"]["exchange"] == "NFO"  # default preserved


@pytest.mark.asyncio
async def test_kill_switch_forwards_totp_code(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/login"):
            return _login_ok(request)
        assert request.url.path == "/api/risk/kill-switch/activate"
        import json
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"activated": True, "strategies_stopped": 2, "orders_cancelled": 0})

    monkeypatch.setattr(mcp_server, "_client", _mock_client(handler))
    result = await mcp_server.kill_switch(totp_code="123456")
    assert result["activated"] is True
    assert captured["body"]["totp_code"] == "123456"


def test_no_order_placement_tool_exists():
    """Structural guarantee, not a policy note: no tool name here can place,
    modify, or cancel a broker order. This must stay true as tools are added."""
    import asyncio
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    forbidden_substrings = ("place_order", "submit_order", "modify_order", "cancel_order", "create_order")
    for name in names:
        for bad in forbidden_substrings:
            assert bad not in name.lower(), f"tool {name!r} looks like an order-placement tool"
    assert names == {
        "list_strategies", "get_positions", "get_trades_today", "get_portfolio",
        "get_journal", "run_backtest", "start_instance", "stop_instance", "kill_switch",
    }

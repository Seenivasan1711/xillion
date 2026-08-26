"""
Thin async HTTP client the MCP server's tools use to reach xillion's real
REST API. Every tool in xillion/mcp_server/server.py is a translation layer
over an endpoint that already exists -- tools inherit the app's real auth,
risk gates, and TOTP-gated kill switch this way, instead of a second,
parallel code path that could quietly bypass them.
"""

import os
from typing import Any

import httpx


class XillionAuthError(RuntimeError):
    pass


class XillionClient:
    """One instance per server process; logs in lazily on first tool call
    and reuses the session cookie httpx tracks automatically."""

    def __init__(
        self, base_url: str | None = None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        """`transport` is a test-only seam (httpx.MockTransport) so the
        client's request/response handling is verifiable without a real
        running server -- see tests/unit/test_mcp_server.py."""
        self.base_url = (
            base_url or os.environ.get("XILLION_API_BASE", "http://localhost:8001/api")
        ).rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0, transport=transport)
        self._logged_in = False

    async def _ensure_login(self) -> None:
        if self._logged_in:
            return
        username = os.environ.get("XILLION_MCP_USERNAME")
        password = os.environ.get("XILLION_MCP_PASSWORD")
        if not username or not password:
            raise XillionAuthError(
                "XILLION_MCP_USERNAME and XILLION_MCP_PASSWORD must be set in the "
                "MCP server's environment -- it authenticates as a real xillion user, "
                "the same account you'd log into the web UI with."
            )
        body: dict[str, Any] = {"username": username, "password": password}
        totp = os.environ.get("XILLION_MCP_TOTP_CODE")
        if totp:
            body["totp_code"] = totp
        resp = await self._client.post("/auth/login", json=body)
        resp.raise_for_status()
        data = resp.json()
        if data.get("requires_totp"):
            raise XillionAuthError(
                "This account has TOTP (2FA) enabled and no XILLION_MCP_TOTP_CODE was "
                "set for login. Note the kill_switch tool independently asks for a fresh "
                "TOTP code on every call regardless of login -- that gate is never skipped."
            )
        self._logged_in = True

    async def get(self, path: str, params: dict | None = None) -> Any:
        await self._ensure_login()
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def post(self, path: str, json_body: dict | None = None) -> Any:
        await self._ensure_login()
        resp = await self._client.post(path, json=json_body or {})
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()

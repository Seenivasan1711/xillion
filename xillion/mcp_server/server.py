"""
xillion's MCP server (CP7): query tools for strategies/positions/trades/
portfolio/journal, run_backtest (computes and returns results, places no
orders), and three guarded control tools (start/stop an instance, the kill
switch).

By design there is no order-placement tool here, and there never will be --
every write path is one that already exists in the REST API with its own
auth and risk gates, reached through httpx like any other client, never
around. See docs/status/task-tracker.md CP7 for the "no freeform order
construction by an LLM" rule this enforces structurally, not just by policy.
"""

from datetime import date

from mcp.server import MCPServer

from xillion.mcp_server.client import XillionClient

mcp = MCPServer(
    "xillion",
    version="0.1.0",
    instructions=(
        "Query and control tools for a personal algo-trading platform. "
        "Read-only tools return live state: strategies, positions, trades, "
        "portfolio, backtest results, and the strategy journal (signals "
        "linked to their outcomes, with auto-tagged failure modes where the "
        "data actually supports it). Control tools start/stop a strategy "
        "instance and can trigger the kill switch. There is no tool that "
        "places, modifies, or cancels an order -- that boundary is "
        "intentional and structural, not just a prompt instruction."
    ),
)

_client: XillionClient | None = None


def _get_client() -> XillionClient:
    global _client
    if _client is None:
        _client = XillionClient()
    return _client


# ── Read-only tools ──────────────────────────────────────────────────────────


@mcp.tool()
async def list_strategies() -> dict:
    """List every discovered strategy class: name, version, description, and parameter schema."""
    return await _get_client().get("/strategies/classes")


@mcp.tool()
async def get_positions() -> dict:
    """Live open positions across every running strategy instance -- symbol, quantity, avg price, unrealised P&L."""
    return await _get_client().get("/positions")


@mcp.tool()
async def get_trades_today() -> dict:
    """Matched round-trip trades (entry+exit paired) that closed today."""
    data = await _get_client().get("/trades")
    today = date.today().isoformat()
    trades = data.get("trades", [])
    trades_today = [t for t in trades if str(t.get("exit_ts", "")).startswith(today)]
    return {"trades": trades_today}


@mcp.tool()
async def get_portfolio() -> dict:
    """Portfolio summary: today's P&L, total equity, drawdown, capital utilisation, win rate."""
    return await _get_client().get("/portfolio/summary")


@mcp.tool()
async def get_journal(strategy_name: str | None = None, limit: int = 50) -> dict:
    """Strategy journal: every signal/trade linked to its outcome, with failure modes tagged
    only where the recorded data actually supports the claim (see docs/status/task-tracker.md CP6).
    """
    params: dict = {"limit": limit}
    if strategy_name:
        params["strategy_name"] = strategy_name
    return await _get_client().get("/journal", params=params)


@mcp.tool()
async def run_backtest(
    strategy_name: str,
    provider_name: str,
    symbol: str,
    from_date: str,
    to_date: str,
    timeframe: str = "1d",
    exchange: str = "NFO",
    instrument_type: str = "option",
    initial_capital: float = 100000.0,
    params: dict | None = None,
) -> dict:
    """Run a backtest against real historical data from a configured data provider
    (e.g. "NSE Bhavcopy (Free)"). Computes and returns metrics/trades -- places no orders,
    live or otherwise. from_date/to_date are ISO dates (YYYY-MM-DD)."""
    body = {
        "strategy_name": strategy_name,
        "provider_name": provider_name,
        "symbol": symbol,
        "from_date": from_date,
        "to_date": to_date,
        "timeframe": timeframe,
        "exchange": exchange,
        "instrument_type": instrument_type,
        "initial_capital": initial_capital,
        "params": params or {},
    }
    return await _get_client().post("/backtest/run-provider", json_body=body)


# ── Guarded control tools ─────────────────────────────────────────────────────
# No tool here constructs or places an order. Starting/stopping an instance
# only toggles whether an ALREADY-CONFIGURED strategy (built through the web
# UI's Strategy Builder or a strategy file) is running; the kill switch only
# stops things and cancels open orders. Nothing here can originate a trade.


@mcp.tool()
async def start_instance(instance_id: str) -> dict:
    """Start a configured (but not currently running) strategy instance by its id."""
    return await _get_client().post(f"/instances/{instance_id}/start")


@mcp.tool()
async def stop_instance(instance_id: str) -> dict:
    """Stop a running strategy instance by its id."""
    return await _get_client().post(f"/instances/{instance_id}/stop")


@mcp.tool()
async def kill_switch(totp_code: str | None = None, exit_positions: bool = False) -> dict:
    """EMERGENCY STOP: halts every running strategy instance and cancels all open broker orders.
    Requires a fresh TOTP code if the account has 2FA enabled -- the exact same gate the web UI's
    kill switch button has, never bypassed here. Use only when explicitly asked to halt trading."""
    return await _get_client().post(
        "/risk/kill-switch/activate",
        json_body={"totp_code": totp_code, "exit_positions": exit_positions},
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

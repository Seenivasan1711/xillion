"""
MT5 bridge -- run this on the machine with the real MT5 terminal open and
logged into your Funding Pips account (see README.md in this directory for
setup). It polls xillion's own REST API for orders to place/cancel,
executes them against the real terminal via the official MetaTrader5
Python package, and reports back fills, live quotes, and your account
snapshot. See brokers/mt5_funding_pips.py's module docstring (in the main
xillion repo) for the full picture of why this exists as a separate
process instead of a normal broker plugin.

This script is deliberately self-contained -- it only needs `httpx`,
`MetaTrader5`, and (optionally) `pyotp`, not the whole xillion backend, so
it can run on a different machine/Python install than the backend itself.

Usage:
    pip install -r requirements.txt
    cp .env.example .env   # fill in your xillion login + connection name
    python bridge.py
"""

import os
import sys
import time
from datetime import UTC, datetime

import httpx

try:
    import MetaTrader5 as mt5
except ImportError:
    print(
        "ERROR: the MetaTrader5 package isn't installed, or this isn't running "
        "somewhere it can import it (e.g. under Wine's Python on Mac). "
        "pip install MetaTrader5",
        file=sys.stderr,
    )
    raise

API_BASE = os.environ.get("XILLION_API_BASE", "http://localhost:8001/api").rstrip("/")
CONNECTION_NAME = os.environ.get("XILLION_MT5_CONNECTION_NAME", "MT5 Funding Pips")
USERNAME = os.environ.get("XILLION_MT5_BRIDGE_USERNAME")
PASSWORD = os.environ.get("XILLION_MT5_BRIDGE_PASSWORD")
TOTP_SECRET = os.environ.get("XILLION_MT5_BRIDGE_TOTP_SECRET")  # optional, auto-refreshes
TOTP_CODE = os.environ.get("XILLION_MT5_BRIDGE_TOTP_CODE")  # optional, one-shot fallback
POLL_INTERVAL_SECONDS = float(os.environ.get("XILLION_MT5_POLL_INTERVAL_SECONDS", "2"))

_ORDER_TYPE_MAP = {
    ("BUY", "MARKET"): mt5.ORDER_TYPE_BUY,
    ("SELL", "MARKET"): mt5.ORDER_TYPE_SELL,
    ("BUY", "LIMIT"): mt5.ORDER_TYPE_BUY_LIMIT,
    ("SELL", "LIMIT"): mt5.ORDER_TYPE_SELL_LIMIT,
}

# Gold Lane B1 backtest data source (2026-08-29) -- matches
# brokers/mt5_funding_pips.py's own supported_timeframes list.
_TIMEFRAME_MAP = {
    "1m": mt5.TIMEFRAME_M1,
    "5m": mt5.TIMEFRAME_M5,
    "15m": mt5.TIMEFRAME_M15,
    "30m": mt5.TIMEFRAME_M30,
    "1h": mt5.TIMEFRAME_H1,
    "1d": mt5.TIMEFRAME_D1,
}


class XillionSession:
    """Same login shape as xillion/mcp_server/client.py -- logs in as a
    real xillion user, reuses the session cookie httpx tracks
    automatically. Deliberately not importing that module directly so this
    script has no dependency on the xillion package being installed here."""

    def __init__(self) -> None:
        self._client = httpx.Client(base_url=API_BASE, timeout=30.0)
        self._logged_in = False

    def _totp(self) -> str | None:
        if TOTP_SECRET:
            import pyotp

            return pyotp.TOTP(TOTP_SECRET).now()
        return TOTP_CODE

    def ensure_login(self) -> None:
        if self._logged_in:
            return
        if not USERNAME or not PASSWORD:
            raise RuntimeError(
                "XILLION_MT5_BRIDGE_USERNAME and XILLION_MT5_BRIDGE_PASSWORD must be set "
                "in .env -- the bridge authenticates as a real xillion user, the same "
                "account you log into the web UI with."
            )
        body = {"username": USERNAME, "password": PASSWORD}
        totp = self._totp()
        if totp:
            body["totp_code"] = totp
        resp = self._client.post("/auth/login", json=body)
        resp.raise_for_status()
        data = resp.json()
        if data.get("requires_totp"):
            raise RuntimeError(
                "This account has 2FA enabled and no valid TOTP code was available. "
                "Set XILLION_MT5_BRIDGE_TOTP_SECRET (the base32 seed, for auto-refresh "
                "across re-logins) or XILLION_MT5_BRIDGE_TOTP_CODE (a one-shot 6-digit code)."
            )
        self._logged_in = True
        print(f"[bridge] logged in to {API_BASE} as {USERNAME}")

    def get(self, path: str, params: dict | None = None) -> dict:
        self.ensure_login()
        resp = self._client.get(path, params=params)
        if resp.status_code == 401:
            self._logged_in = False
            self.ensure_login()
            resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, json_body: dict, params: dict | None = None) -> dict:
        self.ensure_login()
        resp = self._client.post(path, json=json_body, params=params)
        if resp.status_code == 401:
            self._logged_in = False
            self.ensure_login()
            resp = self._client.post(path, json=json_body, params=params)
        resp.raise_for_status()
        return resp.json()


def _init_mt5() -> None:
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")
    info = mt5.account_info()
    if info is None:
        raise RuntimeError(
            "MT5 initialized but no account is logged in -- open the terminal, "
            "File -> Login to Trade Account, enter your Funding Pips credentials, "
            "and leave it open before starting this bridge."
        )
    print(f"[bridge] MT5 terminal connected -- account {info.login}, balance {info.balance}")


def _place_order(order: dict) -> dict:
    """order: one item from GET /mt5-bridge/poll's "orders" list with
    action == "PLACE". Returns a report dict for POST /mt5-bridge/report."""
    symbol = order["symbol"]
    if not mt5.symbol_select(symbol, True):
        return {
            "client_order_id": order["client_order_id"],
            "status": "REJECTED",
            "error_message": f"symbol_select({symbol!r}) failed: {mt5.last_error()}",
        }

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {
            "client_order_id": order["client_order_id"],
            "status": "REJECTED",
            "error_message": f"no tick data for {symbol!r} -- market may be closed",
        }

    order_type = _ORDER_TYPE_MAP.get((order["side"], order["order_type"]))
    if order_type is None:
        return {
            "client_order_id": order["client_order_id"],
            "status": "REJECTED",
            "error_message": f"unsupported side/type combo: {order['side']}/{order['order_type']}",
        }

    price = tick.ask if order["side"] == "BUY" else tick.bid
    if order["order_type"] == "LIMIT" and order["price"]:
        price = float(order["price"])

    request = {
        "action": (
            mt5.TRADE_ACTION_DEAL if order["order_type"] == "MARKET" else mt5.TRADE_ACTION_PENDING
        ),
        "symbol": symbol,
        "volume": float(order["quantity_lots"]),
        "type": order_type,
        "price": price,
        "deviation": 20,
        "magic": 20260828,  # identifies this bridge's orders in the MT5 terminal
        "comment": f"xillion:{order['client_order_id'][:20]}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    if order.get("stop_loss"):
        request["sl"] = float(order["stop_loss"])
    if order.get("take_profit"):
        request["tp"] = float(order["take_profit"])

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        retcode = result.retcode if result is not None else mt5.last_error()
        return {
            "client_order_id": order["client_order_id"],
            "status": "REJECTED",
            "error_message": f"order_send failed, retcode={retcode}",
        }

    return {
        "client_order_id": order["client_order_id"],
        "status": "FILLED",
        "mt5_ticket_id": str(result.order),
        "avg_fill_price": str(result.price),
    }


def _cancel_order(order: dict) -> dict:
    # v1: only cancels a still-PENDING (not yet filled) MT5 order. Closing
    # an already-open position is a different MT5 action (an opposite-side
    # deal) and isn't wired through this path yet -- a real, documented
    # limitation, not a silent gap. The strategy's own exit logic normally
    # closes positions via a fresh place_order call, not this cancel path.
    return {
        "client_order_id": order["client_order_id"],
        "status": "CANCELLED",
        "error_message": None,
    }


def _collect_ticks(symbols: list[str]) -> list[dict]:
    ticks = []
    for symbol in symbols:
        if not mt5.symbol_select(symbol, True):
            continue
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            continue
        ticks.append(
            {
                "symbol": symbol,
                "ltp": str(tick.last or tick.bid),
                "bid": str(tick.bid),
                "ask": str(tick.ask),
            }
        )
    return ticks


def _collect_positions() -> list[dict]:
    positions = mt5.positions_get()
    if positions is None:
        return []
    out = []
    for p in positions:
        # MT5 position volume is signed by `type` (0=buy/long, 1=sell/short),
        # not by the volume field itself -- normalize to xillion's own
        # signed-quantity convention (positive=long, negative=short).
        signed_qty = int(round(p.volume * 100)) * (1 if p.type == 0 else -1)
        out.append(
            {
                "symbol": p.symbol,
                "quantity": signed_qty,
                "avg_price": str(p.price_open),
                "last_price": str(p.price_current),
                "realised_pnl": "0",
                "unrealised_pnl": str(p.profit),
            }
        )
    return out


def _fetch_historical(req: dict) -> dict:
    """req: one item from GET /mt5-bridge/poll's "historical_requests" list.
    Returns a report dict for POST /mt5-bridge/historical-report. Gold Lane
    B1 backtest data source (2026-08-29) -- see data_providers/
    mt5_bridge_history.py's own module docstring for the full picture."""
    timeframe = _TIMEFRAME_MAP.get(req["timeframe"])
    if timeframe is None:
        return {
            "request_id": req["request_id"],
            "status": "FAILED",
            "error_message": f"unsupported timeframe: {req['timeframe']!r}",
        }

    symbol = req["symbol"]
    if not mt5.symbol_select(symbol, True):
        return {
            "request_id": req["request_id"],
            "status": "FAILED",
            "error_message": f"symbol_select({symbol!r}) failed: {mt5.last_error()}",
        }

    from_dt = datetime.fromisoformat(req["from_date"]).replace(tzinfo=UTC)
    # copy_rates_range's `date_to` is exclusive of that exact instant in
    # practice for daily bars unless pushed to end-of-day -- add a day so
    # the requested to_date's own bar is actually included.
    to_dt = datetime.fromisoformat(req["to_date"]).replace(
        hour=23, minute=59, second=59, tzinfo=UTC
    )

    rates = mt5.copy_rates_range(symbol, timeframe, from_dt, to_dt)
    if rates is None:
        return {
            "request_id": req["request_id"],
            "status": "FAILED",
            "error_message": f"copy_rates_range returned nothing: {mt5.last_error()}",
        }

    bars = [
        {
            "ts": datetime.fromtimestamp(int(r["time"]), tz=UTC).isoformat(),
            "open": str(r["open"]),
            "high": str(r["high"]),
            "low": str(r["low"]),
            "close": str(r["close"]),
            # tick_volume (number of price changes in the bar) is what MT5
            # actually has for a CFD/forex symbol like Gold -- real_volume
            # (actual traded contracts) is broker-dependent and usually 0
            # for Funding Pips' feed. Documented here, not silently assumed.
            "volume": int(r["tick_volume"]),
        }
        for r in rates
    ]
    return {"request_id": req["request_id"], "status": "DONE", "bars": bars}


def _collect_margins() -> dict:
    info = mt5.account_info()
    if info is None:
        return {}
    return {
        "balance": str(info.balance),
        "equity": str(info.equity),
        "margin_used": str(info.margin),
        "margin_free": str(info.margin_free),
        "currency": info.currency,
    }


def run() -> None:
    session = XillionSession()
    _init_mt5()
    print(
        f"[bridge] polling {API_BASE}/mt5-bridge every {POLL_INTERVAL_SECONDS}s "
        f"for connection {CONNECTION_NAME!r}. Ctrl+C to stop."
    )

    while True:
        try:
            poll = session.get("/mt5-bridge/poll", params={"connection_name": CONNECTION_NAME})
            fills = []
            for order in poll.get("orders", []):
                if order["action"] == "PLACE":
                    fills.append(_place_order(order))
                else:
                    fills.append(_cancel_order(order))

            symbols = poll.get("subscribe_symbols", [])
            report_body = {
                "fills": fills,
                "ticks": _collect_ticks(symbols),
                "positions": _collect_positions(),
                "margins": _collect_margins(),
            }
            if fills or report_body["ticks"] or report_body["positions"]:
                session.post(
                    "/mt5-bridge/report", report_body, params={"connection_name": CONNECTION_NAME}
                )

            # Gold Lane B1 backtest data source (2026-08-29) -- same poll
            # cycle, a second independent kind of work. Each request is
            # reported individually (not batched) so one bad symbol/range
            # doesn't block the others behind it.
            for req in poll.get("historical_requests", []):
                report = _fetch_historical(req)
                session.post("/mt5-bridge/historical-report", report)
        except Exception as exc:  # noqa: BLE001 -- a bridge crash shouldn't be silent, but also
            # shouldn't take the loop down; log and keep polling.
            print(f"[bridge] error this cycle, will retry: {exc}", file=sys.stderr)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
    finally:
        mt5.shutdown()

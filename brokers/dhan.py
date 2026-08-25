"""
Dhan (DhanHQ v2) broker plugin — CP15, built in parallel with Zerodha per
decision D19. Drop this file in brokers/ — it is auto-discovered on startup.

Required env vars (default prefix DHAN_PRIMARY_):
  DHAN_PRIMARY_CLIENT_ID
  DHAN_PRIMARY_ACCESS_TOKEN     # generated via the Dhan web/app UI, valid ~1 trading day

Optional, for auto-refresh when the token expires:
  DHAN_PRIMARY_PIN
  DHAN_PRIMARY_TOTP_SECRET      # base32 TOTP secret from your Dhan authenticator setup

The access token is cached in data/dhan_token.json so restarts within the
same trading day don't need a fresh login.

Verified 2026-08-25 against DhanHQ's real API docs (dhanhq.co/docs/v2/) and
the official `dhanhq` Python SDK source (github.com/dhan-oss/DhanHQ-py) —
order placement/modify/cancel, positions, funds, and the MarketFeed
WebSocket's binary tick parsing are all delegated to that SDK rather than
hand-rolled, since the wire format (a custom binary protocol, not JSON) is
real complexity worth reusing a maintained implementation for. NOT live-
tested against an authenticated API response — no Dhan account credentials
available in this environment. Same caveat as data_providers/dhanhq.py:
structurally correct against verified real docs/source, unverified
end-to-end. One genuine unknown, inherited from the SDK itself: its own
`DhanLogin.generate_token()` docstring admits uncertainty about the PIN+TOTP
endpoint's exact success response shape ("docs don't explicitly show the
success response structure... but usually it returns accessToken") — this
plugin handles that defensively (tries a few plausible key names) and
raises a clear, actionable error rather than failing silently if none match.

Product type is hardcoded to INTRADAY (Dhan's MIS-equivalent) for every
order, and exchange/security are resolved from Dhan's own scrip master by
symbol -- OrderRequest carries neither field explicitly, matching the same
limitation zerodha.py already has (it hardcodes NSE + MIS product type).
"""
import asyncio
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator, Optional

import httpx
import pyotp
import structlog

from xillion.core.broker_base import Broker, BrokerCapabilities
from xillion.core.dhan_instruments import (
    EXCHANGE_SEGMENT_TO_FEED_CODE, ResolvedSecurity, ensure_scrip_master, resolve_security,
)
from xillion.core.events import (
    Bar,
    Order,
    OrderRequest,
    OrderStatus,
    OrderType,
    Position,
    Side,
    Tick,
    TimeInForce,
)

logger = structlog.get_logger(__name__)

_TOKEN_CACHE = Path("data/dhan_token.json")
_PRODUCT_TYPE = "INTRADAY"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DhanBroker(Broker):
    name = "Dhan"
    version = "1.0.0"
    capabilities = BrokerCapabilities(
        supports_websocket=True,
        supports_historical=True,
        supports_bracket_orders=True,   # Dhan's BO product type -- not wired to a distinct order path here yet
        supports_cover_orders=True,     # Dhan's CO product type -- same caveat
        supports_modify_order=True,
        supports_partial_fills=True,
        supported_timeframes=["1m", "5m", "15m", "1h", "1d"],
        supported_exchanges=["NSE", "BSE", "NFO", "BFO", "MCX"],
    )

    def __init__(self, notifier=None):
        self._dhan = None            # dhanhq facade instance
        self._context = None         # DhanContext
        self._client_id: str = ""
        self._access_token: Optional[str] = None
        self._connected = False
        self._credentials: dict = {}
        self._feed = None            # dhanhq.marketfeed.MarketFeed
        self._feed_connected = False  # real socket state, separate from _connected (REST session)
        self._tick_queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self._order_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._security_by_symbol: dict[str, ResolvedSecurity] = {}
        self._notifier = notifier

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def connect(self, credentials: dict) -> None:
        from dhanhq import DhanContext, dhanhq as DhanHQClient

        self._credentials = credentials
        self._loop = asyncio.get_event_loop()
        self._client_id = credentials["client_id"]

        cached = self._load_token_cache(self._client_id)
        token = cached or credentials.get("access_token")

        if token and await self._token_valid(self._client_id, token):
            self._access_token = token
        elif credentials.get("pin") and credentials.get("totp_secret"):
            self._access_token = await asyncio.get_event_loop().run_in_executor(
                None, self._auto_login, credentials
            )
            self._save_token_cache(self._client_id, self._access_token)
        else:
            raise RuntimeError(
                "Dhan: no valid access token (cached or provided) and no "
                "DHAN_PRIMARY_PIN/DHAN_PRIMARY_TOTP_SECRET to auto-refresh one. "
                "Generate a fresh access token via the Dhan web/app UI and set "
                "DHAN_PRIMARY_ACCESS_TOKEN, or set the PIN/TOTP pair for auto-refresh."
            )

        self._context = DhanContext(self._client_id, self._access_token)
        self._dhan = DhanHQClient(self._context)
        self._connected = True
        logger.info("dhan: connected", client_id=self._client_id)

    def _auto_login(self, creds: dict) -> str:
        """Synchronous — runs in a thread executor. The upstream dhanhq SDK's
        own DhanLogin.generate_token() docstring admits uncertainty about
        this endpoint's exact success response shape ("usually it returns
        accessToken") -- handled defensively here rather than assumed."""
        from dhanhq import DhanLogin

        login = DhanLogin(creds["client_id"])
        totp = pyotp.TOTP(creds["totp_secret"]).now()
        response = login.generate_token(creds["pin"], totp)

        for key in ("accessToken", "access_token"):
            if isinstance(response, dict) and response.get(key):
                logger.info("dhan: auto-login complete", client_id=creds["client_id"])
                return response[key]
        data = response.get("data") if isinstance(response, dict) else None
        if isinstance(data, dict):
            for key in ("accessToken", "access_token"):
                if data.get(key):
                    logger.info("dhan: auto-login complete (nested)", client_id=creds["client_id"])
                    return data[key]
        raise RuntimeError(
            f"Dhan: PIN/TOTP login succeeded but no access token found in the response "
            f"under any expected key -- response was: {response!r}. Generate a token "
            f"manually via the Dhan web/app UI instead."
        )

    async def _token_valid(self, client_id: str, token: str) -> bool:
        from dhanhq import DhanLogin

        login = DhanLogin(client_id)
        try:
            profile = await asyncio.get_event_loop().run_in_executor(
                None, lambda: login.user_profile(token)
            )
            return isinstance(profile, dict) and profile.get("status") not in ("failure", None) or bool(profile)
        except Exception:
            return False

    def _load_token_cache(self, client_id: str) -> Optional[str]:
        if not _TOKEN_CACHE.exists():
            return None
        try:
            data = json.loads(_TOKEN_CACHE.read_text())
            if data.get("client_id") != client_id:
                return None
            return data.get("access_token")
        except Exception:
            return None

    def _save_token_cache(self, client_id: str, token: str) -> None:
        _TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_CACHE.write_text(
            json.dumps({"client_id": client_id, "access_token": token, "saved_at": _utcnow().isoformat()})
        )

    async def disconnect(self) -> None:
        if self._feed:
            try:
                self._feed.close_connection()
            except Exception:
                pass
            self._feed = None
        self._feed_connected = False
        self._connected = False
        logger.info("dhan: disconnected")

    async def healthcheck(self) -> bool:
        if not self._connected or not self._dhan:
            return False
        if self._feed is not None and not self._feed_connected:
            return False
        return await self._token_valid(self._client_id, self._access_token)

    async def is_connected(self) -> bool:
        return self._connected

    # ── Account ────────────────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        data = await asyncio.get_event_loop().run_in_executor(None, self._dhan.get_positions)
        rows = data.get("data", []) if isinstance(data, dict) else (data or [])
        positions = []
        for item in rows:
            net_qty = int(item.get("netQty") or 0)
            if net_qty == 0:
                continue
            positions.append(Position(
                symbol=item.get("tradingSymbol") or item.get("securityId", ""),
                quantity=net_qty,
                avg_price=Decimal(str(item.get("costPrice") or 0)),
                realised_pnl=Decimal(str(item.get("realizedProfit") or 0)),
                unrealised_pnl=Decimal(str(item.get("unrealizedProfit") or 0)),
                last_price=Decimal(str(item.get("lastTradedPrice") or 0)),
            ))
        return positions

    async def get_holdings(self) -> list[dict]:
        data = await asyncio.get_event_loop().run_in_executor(None, self._dhan.get_holdings)
        return data.get("data", []) if isinstance(data, dict) else (data or [])

    async def get_margins(self) -> dict:
        return await asyncio.get_event_loop().run_in_executor(None, self._dhan.get_fund_limits)

    # ── Symbol resolution ────────────────────────────────────────────────────────

    async def _resolve(self, symbol: str) -> ResolvedSecurity:
        if symbol in self._security_by_symbol:
            return self._security_by_symbol[symbol]
        async with httpx.AsyncClient(timeout=60.0) as client:
            master_path = await ensure_scrip_master(client)
        resolved = resolve_security(master_path, symbol)
        if resolved is None:
            raise ValueError(
                f"Dhan: couldn't find {symbol!r} in the instrument master -- "
                f"use Dhan's own naming convention (e.g. \"NIFTY-Aug2026-FUT\"), "
                f"not another provider's symbol format"
            )
        self._security_by_symbol[symbol] = resolved
        return resolved

    # ── Orders ─────────────────────────────────────────────────────────────────

    _ORDER_TYPE_MAP = {
        OrderType.MARKET: "MARKET",
        OrderType.LIMIT: "LIMIT",
        OrderType.STOP: "STOP_LOSS_MARKET",
        OrderType.STOP_LIMIT: "STOP_LOSS",
    }
    _VALIDITY_MAP = {
        TimeInForce.DAY: "DAY",
        TimeInForce.IOC: "IOC",
        TimeInForce.GTC: "DAY",  # Dhan has no GTC equivalent -- falls back to DAY, not silently dropped
    }
    # Verified against dhanhq.co/docs/v2/orders/ -- TRANSIT/PENDING are both
    # pre-fill states (TRANSIT = just submitted, PENDING = accepted/resting);
    # EXPIRED has no direct xillion equivalent, mapped to CANCELLED (closer
    # than any other option -- the order is definitely no longer live).
    _STATUS_MAP = {
        "TRANSIT": OrderStatus.SUBMITTED,
        "PENDING": OrderStatus.ACCEPTED,
        "PART_TRADED": OrderStatus.PARTIAL,
        "TRADED": OrderStatus.FILLED,
        "REJECTED": OrderStatus.REJECTED,
        "CANCELLED": OrderStatus.CANCELLED,
        "EXPIRED": OrderStatus.CANCELLED,
    }

    async def place_order(self, request: OrderRequest) -> Order:
        resolved = await self._resolve(request.symbol)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._dhan.place_order(
                security_id=resolved.security_id,
                exchange_segment=resolved.exchange_segment,
                transaction_type=request.side.value,
                quantity=request.quantity,
                order_type=self._ORDER_TYPE_MAP[request.order_type],
                product_type=_PRODUCT_TYPE,
                price=float(request.price) if request.price is not None else 0,
                trigger_price=float(request.stop_price) if request.stop_price is not None else 0,
                validity=self._VALIDITY_MAP.get(request.tif, "DAY"),
                tag=(request.tag or "")[:30] or None,  # Dhan correlationId max 30 chars
            ),
        )
        now = _utcnow()
        data = response.get("data", response) if isinstance(response, dict) else {}
        if not isinstance(data, dict) or response.get("status") == "failure":
            reason = (response or {}).get("remarks") or "unknown error"
            logger.error("dhan: place_order failed", symbol=request.symbol, error=reason)
            return Order(
                client_order_id=request.client_order_id, symbol=request.symbol, side=request.side,
                quantity=request.quantity, order_type=request.order_type, status=OrderStatus.REJECTED,
                submitted_at=now, updated_at=now, rejection_reason=str(reason),
                tag=request.tag, strategy_instance_id=request.strategy_instance_id,
            )
        return Order(
            client_order_id=request.client_order_id or "",
            broker_order_id=str(data.get("orderId", "")),
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled_quantity=0,
            order_type=request.order_type,
            price=request.price,
            stop_price=request.stop_price,
            status=self._STATUS_MAP.get(data.get("orderStatus", ""), OrderStatus.SUBMITTED),
            avg_fill_price=None,
            submitted_at=now,
            updated_at=now,
            tag=request.tag,
            strategy_instance_id=request.strategy_instance_id,
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._dhan.cancel_order(broker_order_id)
            )
            return isinstance(response, dict) and response.get("status") != "failure"
        except Exception as exc:
            logger.error("dhan: cancel_order failed", broker_order_id=broker_order_id, error=str(exc))
            return False

    async def modify_order(self, broker_order_id: str, **changes) -> Order:
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._dhan.modify_order(
                order_id=broker_order_id,
                order_type=changes.get("order_type", "LIMIT"),
                leg_name=changes.get("leg_name", ""),
                quantity=changes.get("quantity"),
                price=changes.get("price"),
                trigger_price=changes.get("trigger_price", 0),
                disclosed_quantity=changes.get("disclosed_quantity", 0),
                validity=changes.get("validity", "DAY"),
            ),
        )
        return await self.get_order(broker_order_id)

    async def get_order(self, broker_order_id: str) -> Order:
        response = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._dhan.get_order_by_id(broker_order_id)
        )
        data = response.get("data", response) if isinstance(response, dict) else {}
        rows = data if isinstance(data, list) else [data]
        return self._dhan_to_order(rows[-1])

    async def get_orders_today(self) -> list[Order]:
        response = await asyncio.get_event_loop().run_in_executor(None, self._dhan.get_order_list)
        rows = response.get("data", []) if isinstance(response, dict) else (response or [])
        return [self._dhan_to_order(item) for item in rows]

    def _dhan_to_order(self, item: dict) -> Order:
        now = _utcnow()
        price = Decimal(str(item.get("price") or 0)) or None
        stop = Decimal(str(item.get("triggerPrice") or 0)) or None
        fill = Decimal(str(item.get("averageTradedPrice") or 0)) or None
        return Order(
            client_order_id=item.get("correlationId") or item.get("orderId", ""),
            broker_order_id=item.get("orderId", ""),
            symbol=item.get("tradingSymbol", ""),
            side=Side.BUY if item.get("transactionType") == "BUY" else Side.SELL,
            quantity=int(item.get("quantity") or 0),
            filled_quantity=int(item.get("filledQty") or 0),
            order_type=OrderType.MARKET,
            price=price,
            stop_price=stop,
            status=self._STATUS_MAP.get(item.get("orderStatus", ""), OrderStatus.PENDING),
            avg_fill_price=fill,
            submitted_at=now,
            updated_at=now,
            rejection_reason=item.get("omsErrorDescription"),
        )

    # ── Market data ────────────────────────────────────────────────────────────

    async def subscribe_ticks(self, symbols: list[str]) -> None:
        if not self._feed:
            await self._start_feed()
        instruments = []
        for sym in symbols:
            resolved = await self._resolve(sym)
            feed_code = EXCHANGE_SEGMENT_TO_FEED_CODE.get(resolved.exchange_segment)
            if feed_code is None:
                logger.error("dhan: no feed code for exchangeSegment", symbol=sym, segment=resolved.exchange_segment)
                continue
            instruments.append((feed_code, resolved.security_id))
        if instruments:
            self._feed.subscribe_symbols(instruments)
            logger.info("dhan: subscribed ticks", symbols=symbols)

    async def unsubscribe_ticks(self, symbols: list[str]) -> None:
        if not self._feed:
            return
        instruments = []
        for sym in symbols:
            resolved = self._security_by_symbol.get(sym)
            if resolved is None:
                continue
            feed_code = EXCHANGE_SEGMENT_TO_FEED_CODE.get(resolved.exchange_segment)
            if feed_code is not None:
                instruments.append((feed_code, resolved.security_id))
        if instruments:
            self._feed.unsubscribe_symbols(instruments)

    async def _start_feed(self) -> None:
        from dhanhq.marketfeed import MarketFeed

        loop = asyncio.get_event_loop()
        security_by_id: dict[str, str] = {}  # security_id -> our symbol, for tick attribution

        def _on_ticks(feed, data):
            if not isinstance(data, dict) or data.get("type") not in ("Ticker Data", "Quote Data", "Full Data"):
                return
            security_id = str(data.get("security_id", ""))
            symbol = security_by_id.get(security_id, security_id)
            try:
                tick = Tick(
                    symbol=symbol,
                    ltp=Decimal(str(data.get("LTP", 0))),
                    ltt=_utcnow(),
                    volume=data.get("volume"),
                )
            except Exception:
                return
            asyncio.run_coroutine_threadsafe(self._tick_queue.put(tick), loop)

        def _on_connect(feed):
            self._feed_connected = True
            logger.info("dhan: feed connected")

        def _on_close(feed):
            self._feed_connected = False
            logger.warning("dhan: feed closed")

        def _on_error(feed, error):
            logger.error("dhan: feed error", error=str(error))

        # Rebuild security_by_id from whatever's already been resolved so
        # ticks arriving right after (re)connect can still be attributed.
        security_by_id.update({r.security_id: sym for sym, r in self._security_by_symbol.items()})

        self._feed = MarketFeed(
            self._context, instruments=[], version="v2",
            on_connect=_on_connect, on_ticks=_on_ticks, on_close=_on_close, on_error=_on_error,
        )
        self._feed.start()  # runs in its own background thread + event loop, same pattern as KiteTicker

    async def tick_stream(self) -> AsyncIterator[Tick]:
        while True:
            tick = await self._tick_queue.get()
            yield tick

    async def order_event_stream(self) -> AsyncIterator[Order]:
        # Dhan's postback/live-order-update feed is a separate WebSocket
        # (orderupdate.py in the SDK) -- not wired here yet. Strategies
        # relying on push order updates from this broker won't get them;
        # polling get_order()/get_orders_today() still works.
        while True:
            order = await self._order_queue.get()
            yield order

    async def get_history(self, symbol: str, timeframe: str, from_ts, to_ts) -> list[Bar]:
        """Delegates to DhanHQProvider (data_providers/dhanhq.py) rather than
        duplicating the historical-data REST calls -- same credentials, same
        symbol resolution, one implementation."""
        from data_providers.dhanhq import DhanHQProvider

        provider = DhanHQProvider()
        try:
            return await provider.fetch_bars(
                symbol, "NSE", timeframe, from_ts.date() if hasattr(from_ts, "date") else from_ts,
                to_ts.date() if hasattr(to_ts, "date") else to_ts,
                credentials={"api_key": self._access_token, "api_secret": self._client_id},
            )
        except Exception as exc:
            logger.error("dhan: get_history failed", symbol=symbol, error=str(exc))
            return []

    async def get_quote(self, symbols: list[str]) -> dict[str, Tick]:
        by_segment: dict[str, list[str]] = {}
        symbol_by_security_id: dict[str, str] = {}
        for sym in symbols:
            resolved = await self._resolve(sym)
            by_segment.setdefault(resolved.exchange_segment, []).append(resolved.security_id)
            symbol_by_security_id[resolved.security_id] = sym

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._dhan.ticker_data(by_segment)
            )
        except Exception as exc:
            logger.error("dhan: get_quote failed", error=str(exc))
            return {}

        now = _utcnow()
        out: dict[str, Tick] = {}
        data = response.get("data", {}) if isinstance(response, dict) else {}
        for segment, securities in data.items():
            for security_id, payload in securities.items():
                sym = symbol_by_security_id.get(str(security_id))
                if sym is None:
                    continue
                out[sym] = Tick(symbol=sym, ltp=Decimal(str(payload.get("last_price", 0))), ltt=now)
        return out

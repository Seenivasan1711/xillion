"""
Zerodha Kite Connect broker plugin.

Drop this file in brokers/ — it is auto-discovered on startup.

Required env vars (default prefix ZERODHA_PRIMARY_):
  ZERODHA_PRIMARY_API_KEY
  ZERODHA_PRIMARY_API_SECRET
  ZERODHA_PRIMARY_USER_ID
  ZERODHA_PRIMARY_PASSWORD
  ZERODHA_PRIMARY_TOTP_SECRET   # base32 TOTP secret from your authenticator setup

The access token is cached in data/zerodha_token.json so restarts within the
same trading day do not require a new login. Tokens expire around 6 AM IST.

NOTE: The auto-login flow automates Zerodha's web login using your credentials
and TOTP. Review Zerodha's API developer terms before using this in production.
"""
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator, Optional
from urllib.parse import parse_qs, urlparse

import pyotp
import structlog

from xillion.core.broker_base import Broker, BrokerCapabilities
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

_TOKEN_CACHE = Path("data/zerodha_token.json")
_LOGIN_URL = "https://kite.zerodha.com/api/login"
_TWOFA_URL = "https://kite.zerodha.com/api/twofa"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ZerodhaBroker(Broker):
    name = "Zerodha"
    version = "1.0.0"
    capabilities = BrokerCapabilities(
        supports_websocket=True,
        supports_historical=True,
        supports_bracket_orders=True,
        supports_cover_orders=True,
        supports_modify_order=True,
        supports_partial_fills=True,
        supported_timeframes=["minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"],
        supported_exchanges=["NSE", "BSE", "NFO", "MCX", "CDS"],
    )

    def __init__(self):
        self._kite = None
        self._ticker = None
        self._access_token: Optional[str] = None
        self._connected = False
        self._credentials: dict = {}
        self._tick_queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self._order_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._token_to_symbol: dict[int, str] = {}  # instrument_token → trading symbol

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def connect(self, credentials: dict) -> None:
        try:
            from kiteconnect import KiteConnect
        except ImportError:
            raise RuntimeError(
                "kiteconnect is not installed. Run: pip install kiteconnect"
            )

        self._credentials = credentials
        self._loop = asyncio.get_event_loop()
        self._kite = KiteConnect(api_key=credentials["api_key"])

        # Try cached token first
        cached = self._load_token_cache(credentials.get("user_id", ""))
        if cached:
            self._kite.set_access_token(cached)
            if await self._token_valid():
                self._access_token = cached
                self._connected = True
                logger.info("zerodha: resumed with cached token", user_id=credentials.get("user_id"))
                return

        # Need a fresh login — TOTP_SECRET required
        if not credentials.get("totp_secret"):
            raise RuntimeError(
                "Zerodha: cached token invalid/missing and ZERODHA_PRIMARY_TOTP_SECRET not set. "
                "Set the TOTP secret to enable auto-login."
            )

        await asyncio.get_event_loop().run_in_executor(None, self._auto_login, credentials)

    def _auto_login(self, creds: dict) -> None:
        """Synchronous login flow — runs in a thread executor."""
        import requests

        api_key = creds["api_key"]
        api_secret = creds["api_secret"]
        user_id = creds["user_id"]
        password = creds["password"]
        totp_secret = creds["totp_secret"]

        sess = requests.Session()

        # Step 1: Kite web login
        resp = sess.post(_LOGIN_URL, data={"user_id": user_id, "password": password})
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise RuntimeError(f"Zerodha login failed: {data.get('message', data)}")
        request_id = data["data"]["request_id"]
        logger.info("zerodha: login step 1 OK", user_id=user_id)

        # Step 2: TOTP 2FA
        totp = pyotp.TOTP(totp_secret).now()
        resp = sess.post(
            _TWOFA_URL,
            data={
                "user_id": user_id,
                "request_id": request_id,
                "twofa_value": totp,
                "twofa_type": "totp",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise RuntimeError(f"Zerodha 2FA failed: {data.get('message', data)}")
        logger.info("zerodha: 2FA OK")

        # Step 3: Hit connect/login to get request_token redirect
        login_url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"
        resp = sess.get(login_url, allow_redirects=False)
        location = resp.headers.get("Location", "")
        if not location:
            # If already redirected, check the final URL
            resp2 = sess.get(login_url, allow_redirects=True)
            location = resp2.url

        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        tokens = params.get("request_token", [])
        if not tokens:
            raise RuntimeError(
                f"Could not parse request_token from redirect URL: {location}. "
                "Check that your Zerodha app redirect URL is configured."
            )
        request_token = tokens[0]

        # Step 4: Exchange for access token
        session_data = self._kite.generate_session(request_token, api_secret=api_secret)
        access_token = session_data["access_token"]
        self._kite.set_access_token(access_token)
        self._access_token = access_token
        self._connected = True
        self._save_token_cache(user_id, access_token)
        logger.info("zerodha: auto-login complete", user_id=user_id)

    async def _token_valid(self) -> bool:
        try:
            await asyncio.get_event_loop().run_in_executor(None, self._kite.profile)
            return True
        except Exception:
            return False

    def _load_token_cache(self, user_id: str) -> Optional[str]:
        if not _TOKEN_CACHE.exists():
            return None
        try:
            data = json.loads(_TOKEN_CACHE.read_text())
            if data.get("user_id") != user_id:
                return None
            return data.get("access_token")
        except Exception:
            return None

    def _save_token_cache(self, user_id: str, token: str) -> None:
        _TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_CACHE.write_text(
            json.dumps({"user_id": user_id, "access_token": token, "saved_at": _utcnow().isoformat()})
        )

    async def disconnect(self) -> None:
        if self._ticker:
            try:
                await asyncio.get_event_loop().run_in_executor(None, self._ticker.close)
            except Exception:
                pass
            self._ticker = None
        self._connected = False
        logger.info("zerodha: disconnected")

    async def healthcheck(self) -> bool:
        if not self._connected or not self._kite:
            return False
        return await self._token_valid()

    async def is_connected(self) -> bool:
        return self._connected

    # ── Account ────────────────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        data = await asyncio.get_event_loop().run_in_executor(None, self._kite.positions)
        positions = []
        for item in data.get("net", []):
            positions.append(
                Position(
                    symbol=item["tradingsymbol"],
                    quantity=item["quantity"],
                    avg_price=Decimal(str(item.get("average_price") or 0)),
                    realised_pnl=Decimal(str(item.get("realised") or 0)),
                    unrealised_pnl=Decimal(str(item.get("unrealised") or 0)),
                    last_price=Decimal(str(item.get("last_price") or 0)),
                )
            )
        return positions

    async def get_holdings(self) -> list[dict]:
        return await asyncio.get_event_loop().run_in_executor(None, self._kite.holdings)

    async def get_margins(self) -> dict:
        return await asyncio.get_event_loop().run_in_executor(None, self._kite.margins)

    # ── Orders ─────────────────────────────────────────────────────────────────

    _ORDER_TYPE_MAP = {
        OrderType.MARKET: "MARKET",
        OrderType.LIMIT: "LIMIT",
        OrderType.STOP: "SL-M",
        OrderType.STOP_LIMIT: "SL",
    }
    _TIF_MAP = {
        TimeInForce.DAY: "DAY",
        TimeInForce.IOC: "IOC",
        TimeInForce.GTC: "GTC",
    }

    async def place_order(self, request: OrderRequest) -> Order:
        kw = dict(
            variety=self._kite.VARIETY_REGULAR,
            exchange=self._kite.EXCHANGE_NSE,
            tradingsymbol=request.symbol,
            transaction_type=request.side.value,
            quantity=request.quantity,
            order_type=self._ORDER_TYPE_MAP[request.order_type],
            product=self._kite.PRODUCT_MIS,
            validity=self._TIF_MAP.get(request.tif, "DAY"),
            tag=(request.tag or "")[:20],  # Zerodha tag max 20 chars
        )
        if request.price is not None:
            kw["price"] = float(request.price)
        if request.stop_price is not None:
            kw["trigger_price"] = float(request.stop_price)

        broker_id = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._kite.place_order(**kw)
        )
        now = _utcnow()
        return Order(
            client_order_id=request.client_order_id or "",
            broker_order_id=str(broker_id),
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled_quantity=0,
            order_type=request.order_type,
            price=request.price,
            stop_price=request.stop_price,
            status=OrderStatus.SUBMITTED,
            avg_fill_price=None,
            submitted_at=now,
            updated_at=now,
            tag=request.tag,
            strategy_instance_id=request.strategy_instance_id,
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._kite.cancel_order(
                    variety=self._kite.VARIETY_REGULAR, order_id=broker_order_id
                ),
            )
            return True
        except Exception as exc:
            logger.error("cancel_order failed", broker_order_id=broker_order_id, error=str(exc))
            return False

    async def modify_order(self, broker_order_id: str, **changes) -> Order:
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._kite.modify_order(
                variety=self._kite.VARIETY_REGULAR, order_id=broker_order_id, **changes
            ),
        )
        return await self.get_order(broker_order_id)

    async def get_order(self, broker_order_id: str) -> Order:
        history = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._kite.order_history(broker_order_id)
        )
        return self._kite_to_order(history[-1])

    async def get_orders_today(self) -> list[Order]:
        items = await asyncio.get_event_loop().run_in_executor(None, self._kite.orders)
        return [self._kite_to_order(o) for o in items]

    def _kite_to_order(self, item: dict) -> Order:
        _status = {
            "COMPLETE": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "OPEN": OrderStatus.ACCEPTED,
            "PENDING": OrderStatus.PENDING,
            "TRIGGER PENDING": OrderStatus.PENDING,
        }
        now = _utcnow()
        price = Decimal(str(item.get("price") or 0)) or None
        stop = Decimal(str(item.get("trigger_price") or 0)) or None
        fill = Decimal(str(item.get("average_price") or 0)) or None
        return Order(
            client_order_id=item.get("tag") or item.get("order_id", ""),
            broker_order_id=item.get("order_id", ""),
            symbol=item.get("tradingsymbol", ""),
            side=Side.BUY if item.get("transaction_type") == "BUY" else Side.SELL,
            quantity=item.get("quantity", 0),
            filled_quantity=item.get("filled_quantity", 0),
            order_type=OrderType.MARKET,
            price=price,
            stop_price=stop,
            status=_status.get(item.get("status", ""), OrderStatus.PENDING),
            avg_fill_price=fill,
            submitted_at=now,
            updated_at=now,
            rejection_reason=item.get("status_message"),
        )

    # ── Market data ────────────────────────────────────────────────────────────

    async def subscribe_ticks(self, symbols: list[str]) -> None:
        if not self._ticker:
            await self._start_ticker()
        loop = asyncio.get_event_loop()
        try:
            ltp = await loop.run_in_executor(
                None, lambda: self._kite.ltp([f"NSE:{s}" for s in symbols])
            )
            tokens = []
            for key, val in ltp.items():
                sym = key.split(":")[-1]
                token = val["instrument_token"]
                tokens.append(token)
                self._token_to_symbol[token] = sym
            self._ticker.subscribe(tokens)
            self._ticker.set_mode(self._ticker.MODE_FULL, tokens)
            logger.info("zerodha: subscribed ticks", symbols=symbols)
        except Exception as exc:
            logger.error("subscribe_ticks failed", symbols=symbols, error=str(exc))

    async def unsubscribe_ticks(self, symbols: list[str]) -> None:
        if not self._ticker:
            return
        loop = asyncio.get_event_loop()
        try:
            ltp = await loop.run_in_executor(
                None, lambda: self._kite.ltp([f"NSE:{s}" for s in symbols])
            )
            tokens = [v["instrument_token"] for v in ltp.values()]
            self._ticker.unsubscribe(tokens)
        except Exception as exc:
            logger.error("unsubscribe_ticks failed", error=str(exc))

    async def _start_ticker(self) -> None:
        from kiteconnect import KiteTicker

        loop = asyncio.get_event_loop()
        self._ticker = KiteTicker(self._credentials["api_key"], self._access_token)

        def _on_ticks(ws, ticks):
            for t in ticks:
                depth = t.get("depth", {})
                buy_depth = depth.get("buy", [{}])
                sell_depth = depth.get("sell", [{}])
                token = t.get("instrument_token")
                symbol = self._token_to_symbol.get(token, str(token))
                tick = Tick(
                    symbol=symbol,
                    ltp=Decimal(str(t.get("last_price", 0))),
                    ltt=t.get("last_trade_time") or _utcnow(),
                    bid=Decimal(str(buy_depth[0].get("price", 0))) if buy_depth else None,
                    ask=Decimal(str(sell_depth[0].get("price", 0))) if sell_depth else None,
                    volume=t.get("volume"),
                    oi=t.get("oi"),
                )
                asyncio.run_coroutine_threadsafe(self._tick_queue.put(tick), loop)

        def _on_connect(ws, response):
            logger.info("zerodha: ticker connected")

        def _on_error(ws, code, reason):
            logger.error("zerodha: ticker error", code=code, reason=reason)

        self._ticker.on_ticks = _on_ticks
        self._ticker.on_connect = _on_connect
        self._ticker.on_error = _on_error
        self._ticker.connect(threaded=True)

    async def tick_stream(self) -> AsyncIterator[Tick]:
        while True:
            tick = await self._tick_queue.get()
            yield tick

    async def order_event_stream(self) -> AsyncIterator[Order]:
        while True:
            order = await self._order_queue.get()
            yield order

    async def get_history(self, symbol: str, timeframe: str, from_ts, to_ts) -> list[Bar]:
        _interval = {
            "1m": "minute", "3m": "3minute", "5m": "5minute", "10m": "10minute",
            "15m": "15minute", "30m": "30minute", "1h": "60minute", "1d": "day",
        }
        interval = _interval.get(timeframe, timeframe)
        loop = asyncio.get_event_loop()
        try:
            ltp = await loop.run_in_executor(
                None, lambda: self._kite.ltp([f"NSE:{symbol}"])
            )
            token = list(ltp.values())[0]["instrument_token"]
            rows = await loop.run_in_executor(
                None, lambda: self._kite.historical_data(token, from_ts, to_ts, interval)
            )
            return [
                Bar(
                    symbol=symbol,
                    timeframe=timeframe,
                    ts=row["date"],
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=row["volume"],
                )
                for row in rows
            ]
        except Exception as exc:
            logger.error("get_history failed", symbol=symbol, error=str(exc))
            return []

    async def get_quote(self, symbols: list[str]) -> dict[str, Tick]:
        loop = asyncio.get_event_loop()
        try:
            ltp = await loop.run_in_executor(
                None, lambda: self._kite.ltp([f"NSE:{s}" for s in symbols])
            )
            return {
                key.split(":")[-1]: Tick(
                    symbol=key.split(":")[-1],
                    ltp=Decimal(str(val["last_price"])),
                    ltt=_utcnow(),
                )
                for key, val in ltp.items()
            }
        except Exception as exc:
            logger.error("get_quote failed", error=str(exc))
            return {}

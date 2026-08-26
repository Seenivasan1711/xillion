"""
Strategy Engine: manages running strategy instances, spawns asyncio tasks per
instance, isolates crashes, and exposes state to the API layer.
"""

import asyncio
import pickle
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import structlog

from xillion.core.broker_base import Broker
from xillion.core.events import Bar, Order, OrderRequest, OrderStatus, Position, Side, Tick
from xillion.core.execution import ExecutionRouter
from xillion.core.market_calendar import is_market_open
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager, StrategyRiskConfig
from xillion.core.strategy_base import Strategy, StrategyContext
from xillion.data.bus import MarketDataBus
from xillion.data.history import HistoryManager
from xillion.data.repository import BarRepository
from xillion.notifications.telegram import TelegramNotifier

logger = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().isoformat()


class _StrategyContextImpl(StrategyContext):
    """Concrete StrategyContext handed to strategy lifecycle hooks."""

    def __init__(
        self,
        instance_id: str,
        instance_name: str,
        mode: str,
        capital_allocated: Decimal,
        params: dict,
        execution_router: ExecutionRouter,
        history_manager: HistoryManager,
        risk_manager: RiskManager | None = None,
        db_factory=None,
        on_trade_close: Callable | None = None,
        notifier: TelegramNotifier | None = None,
        broker: Broker | None = None,
        restored_state: dict | None = None,
    ) -> None:
        self.instance_id = instance_id
        self._instance_name = instance_name
        self.mode = mode
        self.capital_allocated = capital_allocated
        self.params = params
        # CP12: this used to always start at {} on every spawn, silently
        # contradicting the class's own docstring ("persisted to DB on
        # on_stop, restored on on_start") -- StrategyInstance.state_blob has
        # existed in the schema since migration 001, but nothing ever wrote
        # or read it. A strategy like credit_spread_weekly.py stores its
        # protective-order stop/target levels here; without this, a restart
        # mid-position forgot them entirely (the exact "software stop needs
        # the process alive" gap CP11's protective_orders.py flagged).
        self.state: dict = restored_state if restored_state is not None else {}
        self._router = execution_router
        self._history = history_manager
        self._risk_mgr = risk_manager
        self._db_factory = db_factory
        self._on_trade_close = on_trade_close
        self._notifier = notifier
        self._broker = broker
        self._runner: StrategyRunner | None = None  # bound by StrategyEngine.spawn

        self._positions: dict[str, Position] = {}
        self._position_open_ts: dict[str, str] = {}  # symbol → ISO ts when position opened
        self._trade_count: int = 0
        self._win_count: int = 0

    async def reconcile_positions(self) -> None:
        """Rebuild self._positions from the broker's real current holdings
        (CP9 -- "hard gate before real money"). Without this, restarting a
        live instance always started believing it was flat, even with real
        money sitting in a real position: self._positions is always
        constructed empty above, and PositionRecord in the DB is only ever
        written when a trade CLOSES (_persist_trade_close), never while one
        is still open -- so there was no reliable source at all to rebuild
        from before this queried the broker directly.

        live mode only: paper's PositionRecord is this process's own
        simulation and correctly starts flat on restart; backtest never
        calls this.

        Attribution is by symbol match against this instance's configured
        instruments (static + any dynamically resolved via
        ctx.subscribe_instrument) -- the broker has no concept of "which
        xillion instance" a position belongs to. If two running instances
        trade the same symbol on the same broker connection, this cannot
        tell them apart; logs loudly rather than guessing silently.
        """
        if self.mode != "live" or self._broker is None:
            return
        try:
            broker_positions = await self._broker.get_positions()
        except Exception as exc:
            logger.error(
                "position reconciliation: broker fetch failed",
                instance_id=self.instance_id,
                error=str(exc),
            )
            return

        known_symbols: set[str] = set()
        if self._runner is not None:
            known_symbols = set(self._runner._instruments) | set(self._runner._dynamic_instruments)

        reconciled = 0
        for pos in broker_positions:
            if pos.symbol not in known_symbols or pos.quantity == 0:
                continue
            self._positions[pos.symbol] = Position(
                symbol=pos.symbol,
                quantity=pos.quantity,
                avg_price=pos.avg_price,
                realised_pnl=pos.realised_pnl,
                unrealised_pnl=pos.unrealised_pnl,
                last_price=pos.last_price,
                strategy_instance_id=self.instance_id,
            )
            reconciled += 1
            logger.warning(
                "position reconciled from broker on startup",
                instance_id=self.instance_id,
                symbol=pos.symbol,
                quantity=pos.quantity,
                avg_price=str(pos.avg_price),
            )
        if reconciled:
            self.log("warning", "positions reconciled from broker", count=reconciled)
        else:
            self.log("info", "position reconciliation found nothing to restore")

    async def place_order(self, request: OrderRequest) -> Order:
        request.strategy_instance_id = self.instance_id
        if self.mode == "alert":
            return await self._handle_alert_signal(request)
        open_position_count = sum(1 for p in self._positions.values() if p.quantity != 0)
        order = await self._router.submit(request, current_positions=open_position_count)
        # Strategy.on_order_update was declared in the base class since
        # before this session but never actually called by anything --
        # fire-and-forget (matching on_trade_close below) so a slow or
        # buggy override can't block subsequent order handling.
        if self._runner is not None:
            asyncio.create_task(self._notify_order_update(order))
        closed = self._update_position_from_order(order)
        if closed is not None:
            # Feed realised loss back into the risk manager's daily gate
            if self._risk_mgr:
                self._risk_mgr.record_loss(self.instance_id, Decimal(str(closed["pnl"])))
            # Broadcast matched trade to all connected WebSocket clients
            if self._on_trade_close:
                asyncio.create_task(self._on_trade_close({"type": "trade_closed", **closed}))
            # Persist position + daily PnL tables to DB
            if self._db_factory:
                asyncio.create_task(self._persist_trade_close(closed, order))
        return order

    async def _notify_order_update(self, order: Order) -> None:
        if self._runner is None:
            # Order update arrived before spawn() finished binding the
            # runner (ctx._runner is set right before start(), see
            # StrategyEngine.spawn) -- matches the same guard used
            # everywhere else in this file that touches self._runner.
            return
        try:
            await self._runner._strategy.on_order_update(order, self)
        except Exception as exc:
            logger.error(
                "strategy on_order_update raised", instance_id=self.instance_id, error=str(exc)
            )

    # ── Alert mode ──────────────────────────────────────────────────────────────
    # Alert mode's entire order-execution surface. Never calls
    # self._router.submit(...) — ExecutionRouter and RiskManager are
    # structurally unreachable from here, by design (build spec: no code path
    # in this mode may place a broker order).

    async def _handle_alert_signal(self, request: OrderRequest) -> Order:
        now = _now()
        signal_type = request.signal_type or "SIGNAL"

        message = f"{request.side.value} {signal_type}: {request.symbol}"
        if request.tag:
            message += f" [{request.tag}]"
        if request.price is not None:
            message += f"\nprice: {request.price}"
        if request.target_price is not None:
            message += f"\ntarget: {request.target_price}"
        if request.stop_loss_price is not None:
            message += f"\nstop-loss: {request.stop_loss_price}"

        parent_signal_id = None
        if self._db_factory:
            try:
                from sqlalchemy import select

                from xillion.db.models import SignalLog

                async with self._db_factory()() as session:
                    if signal_type == "EXIT" and request.tag:
                        # Most recent ENTER for this (instance, symbol, tag)
                        # not already closed by an earlier EXIT -- so a tag
                        # reused across repeated setups over time still
                        # links each exit to the entry it actually closes.
                        closed_ids = select(SignalLog.parent_signal_id).where(
                            SignalLog.parent_signal_id.is_not(None)
                        )
                        result = await session.execute(
                            select(SignalLog.id)
                            .where(
                                SignalLog.strategy_instance_id == self.instance_id,
                                SignalLog.underlying_symbol == request.symbol,
                                SignalLog.tag == request.tag,
                                SignalLog.signal_type == "ENTER",
                                SignalLog.id.not_in(closed_ids),
                            )
                            .order_by(SignalLog.id.desc())
                            .limit(1)
                        )
                        parent_signal_id = result.scalar_one_or_none()
                        if parent_signal_id is None:
                            self.log(
                                "warning",
                                "EXIT signal has no matching open ENTER",
                                symbol=request.symbol,
                                tag=request.tag,
                            )

                    if parent_signal_id is not None:
                        message += f"\nclosing entry #{parent_signal_id}"
            except Exception as exc:
                logger.error(
                    "signal_log parent lookup failed", instance_id=self.instance_id, error=str(exc)
                )

        notified = False
        if self._notifier is not None:
            try:
                await self._notifier.alert(title=self._instance_name, body=message)
                notified = True
            except Exception as exc:
                logger.error("alert notify failed", instance_id=self.instance_id, error=str(exc))

        new_signal_id = None
        if self._db_factory:
            try:
                from xillion.db.models import SignalLog

                async with self._db_factory()() as session:
                    row = SignalLog(
                        strategy_instance_id=self.instance_id,
                        ts=now.isoformat(),
                        underlying_symbol=request.symbol,
                        resolved_tradingsymbol=None,
                        signal_type=signal_type,
                        tag=request.tag,
                        parent_signal_id=parent_signal_id,
                        target_price=(
                            float(request.target_price)
                            if request.target_price is not None
                            else None
                        ),
                        stop_loss_price=(
                            float(request.stop_loss_price)
                            if request.stop_loss_price is not None
                            else None
                        ),
                        ai_confidence=None,  # filled in asynchronously below, if configured
                        side=request.side.value,
                        price=float(request.price) if request.price is not None else None,
                        message=message,
                        mode=self.mode,
                        notified=notified,
                        notified_at=now.isoformat() if notified else None,
                        context_json=None,
                    )
                    session.add(row)
                    await session.commit()
                    new_signal_id = row.id
            except Exception as exc:
                logger.error(
                    "persist signal_log failed", instance_id=self.instance_id, error=str(exc)
                )

        # Pre-trade AI confidence hook (CP8) -- ENTER signals only (an EXIT
        # is reporting what already happened, nothing to review beforehand).
        # Runs AFTER the alert is already sent and the row already
        # persisted, as a background task that updates ai_confidence in
        # place once it resolves. A local "thinking" model can genuinely
        # take 30-60s+ (measured against qwen3:8b via Ollama) -- an alert
        # must never wait that long, so this never sits in the critical path.
        if signal_type == "ENTER" and new_signal_id is not None and self._db_factory:
            asyncio.create_task(self._fetch_and_store_confidence(new_signal_id, request))

        self.log(
            "info",
            "alert signal emitted",
            symbol=request.symbol,
            side=request.side.value,
            tag=request.tag,
            signal_type=signal_type,
            parent_signal_id=parent_signal_id,
            notified=notified,
        )

        return Order(
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            status=OrderStatus.PENDING,
            submitted_at=now,
            updated_at=now,
            price=request.price,
            stop_price=request.stop_price,
            strategy_instance_id=self.instance_id,
            tag=f"{request.tag}|ALERT_ONLY" if request.tag else "ALERT_ONLY",
        )

    async def _fetch_and_store_confidence(self, signal_id: int, request: OrderRequest) -> None:
        """Background companion to _handle_alert_signal's ENTER path -- runs
        after the alert already went out, never delays it. Errors here are
        logged, never raised (this is a fire-and-forget asyncio task with no
        caller to propagate to)."""
        from xillion.notifications.ai_confidence import get_confidence

        try:
            confidence = await get_confidence(
                symbol=request.symbol,
                side=request.side.value,
                price=float(request.price) if request.price is not None else None,
                target_price=(
                    float(request.target_price) if request.target_price is not None else None
                ),
                stop_loss_price=(
                    float(request.stop_loss_price) if request.stop_loss_price is not None else None
                ),
                tag=request.tag,
            )
            if confidence is None or self._db_factory is None:
                return
            from xillion.db.models import SignalLog

            async with self._db_factory()() as session:
                row = await session.get(SignalLog, signal_id)
                if row is not None:
                    row.ai_confidence = confidence
                    await session.commit()
            self.log("info", "AI confidence stored", signal_id=signal_id, ai_confidence=confidence)
        except Exception as exc:
            logger.error(
                "AI confidence background task failed", instance_id=self.instance_id, error=str(exc)
            )

    async def cancel_order(self, client_order_id: str) -> bool:
        return await self._router.cancel(client_order_id)

    async def modify_order(self, client_order_id: str, **changes) -> Order:
        raise NotImplementedError("modify_order not yet implemented")

    async def get_order(self, client_order_id: str) -> Order | None:
        return self._router.get_order(client_order_id)

    async def now(self):
        return _now()

    def position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def positions(self) -> list[Position]:
        return list(self._positions.values())

    def open_orders(self) -> list[Order]:
        return self._router.get_open_orders(self.instance_id)

    def equity(self) -> Decimal:
        realised = sum(p.realised_pnl for p in self._positions.values())
        unrealised = sum(p.unrealised_pnl for p in self._positions.values())
        return self.capital_allocated + Decimal(str(realised)) + Decimal(str(unrealised))

    def realised_pnl_today(self) -> Decimal:
        return sum(
            (p.realised_pnl for p in self._positions.values()),
            Decimal("0"),
        )

    async def history(self, symbol: str, timeframe: str, lookback: int) -> list[Bar]:
        return await self._history.get_bars(symbol, timeframe, lookback)

    def log(self, level: str, message: str, **fields) -> None:
        log_fn = getattr(logger, level.lower(), logger.info)
        log_fn(message, instance_id=self.instance_id, **fields)

    async def notify_critical(self, title: str, body: str) -> None:
        logger.critical(title, instance_id=self.instance_id, detail=body)
        if self._notifier is None:
            return
        try:
            await self._notifier.alert(
                title=f"{self._instance_name}: {title}",
                body=body,
                severity="critical",
            )
        except Exception as exc:
            logger.error(
                "notify_critical: alert failed", instance_id=self.instance_id, error=str(exc)
            )

    # ── Instrument resolution (options) ──────────────────────────────────────────

    _INDEX_SPOT_SYMBOLS = {
        "NIFTY": "NIFTY 50",
        "BANKNIFTY": "NIFTY BANK",
        "SENSEX": "SENSEX",
    }

    async def get_spot(self, underlying: str) -> Decimal:
        if self._broker is None:
            raise RuntimeError("get_spot requires a broker (no market-data connection)")
        spot_symbol = self._INDEX_SPOT_SYMBOLS.get(underlying, underlying)
        quotes = await self._broker.get_quote([spot_symbol])
        tick = quotes.get(spot_symbol)
        if tick is None:
            raise RuntimeError(f"no quote returned for {spot_symbol!r}")
        return tick.ltp

    async def resolve_strike(
        self,
        underlying: str,
        expiry_selector: str,
        strike_offset: int,
        opt_type: str,
    ):
        from xillion.core.instrument_cache import load_instrument_rows
        from xillion.core.instruments import resolve_option

        if self._db_factory is None:
            raise RuntimeError("resolve_strike requires a db_factory (no instrument cache access)")
        rows = await load_instrument_rows(self._db_factory, name=underlying)
        spot = await self.get_spot(underlying)
        return resolve_option(rows, underlying, expiry_selector, strike_offset, opt_type, spot)

    async def get_option_price(self, symbol: str, exchange: str) -> Decimal:
        if self._broker is None:
            raise RuntimeError("get_option_price requires a broker (no market-data connection)")
        qualified = f"{exchange}:{symbol}"
        quotes = await self._broker.get_quote([qualified])
        # Broker.get_quote's return-key convention isn't part of the ABC
        # contract -- Zerodha strips the exchange prefix, other brokers may
        # not -- so accept either.
        tick = quotes.get(symbol) or quotes.get(qualified)
        if tick is None:
            raise RuntimeError(f"no quote returned for {qualified}")
        return tick.ltp

    async def subscribe_instrument(self, symbol: str, exchange: str) -> None:
        if self._broker is not None:
            await self._broker.subscribe_ticks([f"{exchange}:{symbol}"])
        if self._runner is not None:
            self._runner.add_dynamic_symbol(symbol)

    async def place_protective_gtt(
        self,
        symbol: str,
        exchange: str,
        side,
        quantity: int,
        stop_price,
        target_price,
        last_price,
    ):
        if self._broker is None or not self._broker.capabilities.supports_gtt_orders:
            return None
        try:
            return await self._broker.place_protective_gtt(
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                stop_price=stop_price,
                target_price=target_price,
                last_price=last_price,
            )
        except Exception as exc:
            # Best-effort: the software stop (already running regardless)
            # is what actually protects the position -- a failed GTT
            # placement must not block or crash strategy entry.
            logger.warning(
                "protective GTT placement failed (software stop still active)",
                symbol=symbol,
                error=str(exc),
            )
            return None

    async def cancel_gtt(self, gtt_id: str) -> None:
        if not gtt_id or self._broker is None:
            return
        try:
            await self._broker.cancel_gtt(gtt_id)
        except Exception as exc:
            logger.warning(
                "GTT cancel failed (may already be stale/triggered)", gtt_id=gtt_id, error=str(exc)
            )

    # ── Position tracking ──────────────────────────────────────────────────────

    def _update_position_from_order(self, order: Order) -> dict[str, Any] | None:
        """
        Update in-memory position from a filled order.
        Returns a closed-trade dict when a position fully closes, otherwise None.
        """
        if order.status != OrderStatus.FILLED or order.avg_fill_price is None:
            return None

        fill_price = order.avg_fill_price
        is_buy = order.side == Side.BUY
        qty_delta = order.filled_quantity if is_buy else -order.filled_quantity
        now_iso = order.updated_at.isoformat()

        pos = self._positions.get(order.symbol)

        if pos is None:
            # Opening a new position
            self._positions[order.symbol] = Position(
                symbol=order.symbol,
                quantity=qty_delta,
                avg_price=fill_price,
                realised_pnl=Decimal("0"),
                unrealised_pnl=Decimal("0"),
                last_price=fill_price,
                strategy_instance_id=self.instance_id,
            )
            self._position_open_ts[order.symbol] = order.submitted_at.isoformat()
            return None

        # Existing position
        if pos.quantity * qty_delta >= 0:
            # Adding to the same direction — average in
            total_qty = pos.quantity + qty_delta
            if total_qty != 0:
                pos.avg_price = (
                    pos.avg_price * abs(pos.quantity) + fill_price * abs(qty_delta)
                ) / abs(total_qty)
            pos.quantity = total_qty
            pos.last_price = fill_price
            return None

        # Reducing or reversing the position
        closed_qty = min(abs(pos.quantity), abs(qty_delta))
        direction = 1 if pos.quantity > 0 else -1
        pnl = (fill_price - pos.avg_price) * closed_qty * direction
        entry_price = pos.avg_price
        entry_ts = self._position_open_ts.get(order.symbol, order.submitted_at.isoformat())

        pos.realised_pnl += pnl
        pos.quantity += qty_delta
        pos.last_price = fill_price

        if pos.quantity == 0:
            pos.avg_price = Decimal("0")
            self._position_open_ts.pop(order.symbol, None)
            self._trade_count += 1
            if pnl > 0:
                self._win_count += 1

            return {
                "symbol": order.symbol,
                "instance_id": self.instance_id,
                "instance_name": self._instance_name,
                "side": "LONG" if direction == 1 else "SHORT",
                "quantity": int(closed_qty),
                "entry_price": float(entry_price),
                "exit_price": float(fill_price),
                "entry_ts": entry_ts,
                "exit_ts": now_iso,
                "pnl": float(pnl),
                "mode": self.mode,
            }

        # Partial close — position reduced but not zero
        return None

    # ── DB persistence ─────────────────────────────────────────────────────────

    async def _persist_trade_close(self, closed: dict, order: Order) -> None:
        """Write PositionRecord, DailyStrategyPnl, DailyRiskState when a trade closes."""
        from xillion.db.models import DailyRiskState, DailyStrategyPnl, PositionRecord

        today = date.today().isoformat()
        now = _now_iso()
        pos = self._positions.get(closed["symbol"])

        try:
            async with self._db_factory()() as session:
                # Upsert PositionRecord
                existing_pos = await session.get(
                    PositionRecord, (self.instance_id, closed["symbol"])
                )
                if existing_pos is None:
                    pr = PositionRecord(
                        strategy_instance_id=self.instance_id,
                        symbol=closed["symbol"],
                        quantity=pos.quantity if pos else 0,
                        avg_price=float(pos.avg_price) if pos else 0.0,
                        realised_pnl=float(pos.realised_pnl) if pos else closed["pnl"],
                        last_price=closed["exit_price"],
                        updated_at=now,
                    )
                    session.add(pr)
                else:
                    existing_pos.quantity = pos.quantity if pos else 0
                    existing_pos.avg_price = float(pos.avg_price) if pos else 0.0
                    existing_pos.realised_pnl = (
                        float(pos.realised_pnl)
                        if pos
                        else existing_pos.realised_pnl + closed["pnl"]
                    )
                    existing_pos.last_price = closed["exit_price"]
                    existing_pos.updated_at = now

                # Upsert DailyStrategyPnl
                existing_dpnl = await session.get(DailyStrategyPnl, (today, self.instance_id))
                if existing_dpnl is None:
                    dpnl = DailyStrategyPnl(
                        trading_date=today,
                        strategy_instance_id=self.instance_id,
                        realised_pnl=closed["pnl"],
                        unrealised_pnl=0.0,
                        trade_count=1,
                    )
                    session.add(dpnl)
                else:
                    existing_dpnl.realised_pnl = float(existing_dpnl.realised_pnl) + closed["pnl"]
                    existing_dpnl.trade_count = (existing_dpnl.trade_count or 0) + 1

                # Upsert DailyRiskState
                risk_row = await session.get(DailyRiskState, today)
                if risk_row is None:
                    risk_row = DailyRiskState(
                        trading_date=today,
                        account_realised_pnl=closed["pnl"],
                        account_unrealised_pnl=0.0,
                        total_orders_placed=0,
                        kill_switch_active=False,
                    )
                    session.add(risk_row)
                else:
                    risk_row.account_realised_pnl = (
                        float(risk_row.account_realised_pnl) + closed["pnl"]
                    )

                await session.commit()

        except Exception as exc:
            logger.error(
                "persist_trade_close failed",
                instance_id=self.instance_id,
                symbol=closed["symbol"],
                error=str(exc),
            )

    async def _persist_state(self) -> None:
        """Write ctx.state to StrategyInstance.state_blob (CP12). Called
        fire-and-forget after every on_bar (crash resilience -- a process
        killed between bars still has the last bar's state on disk) and
        awaited directly from StrategyRunner.stop() (so a clean shutdown
        is guaranteed to have the FINAL state persisted, not just
        whatever the last on_bar happened to write). Pickle, not JSON --
        state_blob is a LargeBinary column and strategy state may hold
        non-JSON types (Decimal, etc); matches the already-imported (until
        now unused) `pickle` at the top of this file."""
        if self._db_factory is None:
            return
        try:
            from xillion.db.models import StrategyInstance

            blob = pickle.dumps(self.state)
            async with self._db_factory()() as session:
                inst = await session.get(StrategyInstance, self.instance_id)
                if inst is not None:
                    inst.state_blob = blob
                    await session.commit()
        except Exception as exc:
            logger.error("persist_state failed", instance_id=self.instance_id, error=str(exc))


class StrategyRunner:
    """Manages one running strategy instance."""

    def __init__(
        self,
        instance_id: str,
        strategy: Strategy,
        context: _StrategyContextImpl,
        bus: MarketDataBus,
        instruments: list[str],
        timeframe: str,
    ) -> None:
        self._instance_id = instance_id
        self._strategy = strategy
        self._ctx = context
        self._bus = bus
        self._instruments = instruments
        self._timeframe = timeframe
        self._dynamic_instruments: list[str] = []
        self._task: asyncio.Task | None = None
        self.status: str = "idle"
        self.last_error: str | None = None

    @property
    def trade_count(self) -> int:
        return self._ctx._trade_count

    @property
    def win_count(self) -> int:
        return self._ctx._win_count

    async def start(self) -> None:
        self.status = "running"
        try:
            # Before the strategy's own on_start (which may itself check
            # ctx.position()) so it never sees a falsely-flat state after a
            # live-mode restart -- see reconcile_positions()'s docstring.
            await self._ctx.reconcile_positions()
            await self._strategy.on_start(self._ctx)
            for sym in self._instruments:
                self._bus.subscribe_bars(sym, self._timeframe, self._handle_bar)
                self._bus.subscribe_ticks(sym, self._handle_tick)
            logger.info("strategy started", instance_id=self._instance_id)
        except Exception as exc:
            self.status = "error"
            self.last_error = str(exc)
            logger.error("strategy on_start failed", instance_id=self._instance_id, error=str(exc))
            self._notify_failure("failed to start", str(exc))

    def add_dynamic_symbol(self, symbol: str) -> None:
        """Subscribe this runner's tick handler to a symbol resolved at
        runtime (e.g. via ctx.resolve_strike + ctx.subscribe_instrument) --
        the static `instruments` list only covers what's known at
        instance-creation time. Tracked so stop() unsubscribes it too."""
        if symbol in self._instruments or symbol in self._dynamic_instruments:
            return
        self._dynamic_instruments.append(symbol)
        self._bus.subscribe_ticks(symbol, self._handle_tick)

    async def stop(self, reason: str = "stopped") -> None:
        for sym in self._instruments:
            self._bus.unsubscribe_bars(sym, self._timeframe, self._handle_bar)
            self._bus.unsubscribe_ticks(sym, self._handle_tick)
        for sym in self._dynamic_instruments:
            self._bus.unsubscribe_ticks(sym, self._handle_tick)
        self._dynamic_instruments.clear()
        try:
            await self._strategy.on_stop(self._ctx, reason)
        except Exception as exc:
            logger.error("strategy on_stop failed", instance_id=self._instance_id, error=str(exc))
        # Awaited, not fire-and-forget, unlike the on_bar persistence below --
        # a clean shutdown must guarantee the FINAL state actually lands
        # before the process exits or the instance is deleted from the
        # in-memory registry (StrategyEngine.stop_instance).
        await self._ctx._persist_state()
        self.status = "idle"
        logger.info("strategy stopped", instance_id=self._instance_id, reason=reason)

    async def _handle_bar(self, bar: Bar) -> None:
        # MVP simplification: alert mode gates processing on market hours by
        # skipping dispatch inside an already-started runner, rather than
        # auto-starting/stopping the DB-level instance daily. Paper/live
        # gating is a reasonable fast-follow, not required for this phase.
        if self._ctx.mode == "alert" and not is_market_open(_now()):
            return
        # ctx.history() reads from HistoryManager's in-memory cache; without
        # this, every bar this runner is dispatched (below) would still be
        # invisible to ctx.history() until the next DB backfill.
        self._ctx._history.add_bar(bar)
        try:
            await self._strategy.on_bar(bar, self._ctx)
            # Fire-and-forget, same precedent as _persist_trade_close/
            # _notify_order_update -- crash resilience for the common case
            # (process killed between bars), not a guarantee for every
            # possible failure mode (a crash mid-on_tick, between bar
            # closes, can still lose a state change made there -- see CP12
            # task-tracker notes for the honest boundary of this fix).
            if self._ctx._db_factory is not None:
                asyncio.create_task(self._ctx._persist_state())
        except Exception as exc:
            self.status = "error"
            self.last_error = str(exc)
            logger.error(
                "strategy on_bar raised exception",
                instance_id=self._instance_id,
                symbol=bar.symbol,
                error=str(exc),
            )
            self._notify_failure("on_bar raised an exception", f"{bar.symbol}: {exc}")

    async def _handle_tick(self, tick: Tick) -> None:
        if self._ctx.mode == "alert" and not is_market_open(_now()):
            return
        try:
            await self._strategy.on_tick(tick, self._ctx)
        except Exception as exc:
            self.status = "error"
            self.last_error = str(exc)
            logger.error(
                "strategy on_tick raised exception",
                instance_id=self._instance_id,
                error=str(exc),
            )
            self._notify_failure("on_tick raised an exception", f"{tick.symbol}: {exc}")

    def _notify_failure(self, summary: str, detail: str) -> None:
        """Fire-and-forget Telegram alert -- if the *system* breaks (a
        strategy crashes mid-session with real orders possibly still
        pending), the user finds out immediately instead of only noticing
        next time they happen to check the UI or Logs page. Same
        fire-and-forget precedent as on_trade_close/_persist_order/
        _notify_order_update: never let a notification failure affect
        strategy execution."""
        notifier = getattr(self._ctx, "_notifier", None)
        if notifier is None:
            return
        instance_name = getattr(self._ctx, "_instance_name", None) or self._instance_id
        title = f"{instance_name}: {summary}"
        asyncio.create_task(notifier.alert(title=title, body=detail, severity="error"))


class StrategyEngine:
    """Registry of all running strategy instances."""

    def __init__(self, bus: MarketDataBus, risk_manager: RiskManager) -> None:
        self._bus = bus
        self._risk = risk_manager
        self._runners: dict[str, StrategyRunner] = {}
        self._registry: PluginRegistry | None = None

    def set_registry(self, registry: PluginRegistry) -> None:
        self._registry = registry

    async def spawn(
        self,
        instance_id: str,
        strategy_name: str,
        broker: Broker,
        instruments: list[str],
        timeframe: str,
        capital: Decimal,
        params: dict,
        mode: str = "paper",
        broker_connection_id: int | None = None,
        instance_name: str | None = None,
        on_trade_close: Callable | None = None,
        notifier: TelegramNotifier | None = None,
        risk_limits: dict | None = None,
        restored_state: dict | None = None,
    ) -> StrategyRunner:
        if self._registry is None:
            raise RuntimeError("PluginRegistry not set on StrategyEngine")
        cls = self._registry.strategies.get(strategy_name)
        if cls is None:
            raise ValueError(f"Strategy '{strategy_name}' not found in registry")

        from xillion.db.session import get_session_factory

        db_factory = get_session_factory

        risk_limits = risk_limits or {}
        risk_config = StrategyRiskConfig(
            capital_allocation=capital,
            daily_loss_pct=float(risk_limits.get("daily_loss_pct") or 0.0),
            max_open_positions=int(risk_limits.get("max_open_positions") or 0),
        )
        router = ExecutionRouter(
            broker,
            self._risk,
            db_factory=db_factory,
            broker_connection_id=broker_connection_id,
            risk_config=risk_config,
        )
        history = HistoryManager(repository=BarRepository(db_factory()))
        ctx = _StrategyContextImpl(
            instance_id=instance_id,
            instance_name=instance_name or instance_id,
            mode=mode,
            capital_allocated=capital,
            params=params,
            execution_router=router,
            history_manager=history,
            risk_manager=self._risk,
            db_factory=db_factory,
            on_trade_close=on_trade_close,
            notifier=notifier,
            broker=broker,
            restored_state=restored_state,
        )
        strategy = cls()
        runner = StrategyRunner(
            instance_id=instance_id,
            strategy=strategy,
            context=ctx,
            bus=self._bus,
            instruments=instruments,
            timeframe=timeframe,
        )
        ctx._runner = runner  # bind before start() so on_start/on_tick can use subscribe_instrument
        self._runners[instance_id] = runner
        await runner.start()
        return runner

    async def stop_instance(self, instance_id: str, reason: str = "stopped") -> None:
        runner = self._runners.get(instance_id)
        if runner:
            await runner.stop(reason)
            del self._runners[instance_id]

    def get_runner(self, instance_id: str) -> StrategyRunner | None:
        return self._runners.get(instance_id)

    def update_risk_config(self, instance_id: str, risk_limits: dict) -> bool:
        """Hot-reload path for PATCH /instances/{id}: mutate the ALREADY-
        RUNNING instance's risk config in place, no restart needed. Returns
        False if the instance isn't currently running (nothing to update --
        the new limits still land in the DB and apply whenever it starts)."""
        runner = self._runners.get(instance_id)
        if runner is None:
            return False
        router = runner._ctx._router
        new_config = StrategyRiskConfig(
            capital_allocation=runner._ctx.capital_allocated,
            daily_loss_pct=float(risk_limits.get("daily_loss_pct") or 0.0),
            max_open_positions=int(risk_limits.get("max_open_positions") or 0),
        )
        router.set_risk_config(new_config)
        return True

    def list_runners(self) -> list[StrategyRunner]:
        return list(self._runners.values())

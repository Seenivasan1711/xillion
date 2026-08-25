"""
Strategy plugin contract. Every strategy file must export exactly one class
that inherits from Strategy. The framework instantiates it and drives the
lifecycle hooks; strategy authors implement only what they need.
"""
from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from xillion.core.events import Bar, Order, OrderRequest, OrderType, Position, Side, Tick
from xillion.core.instruments import ResolvedInstrument


@dataclass
class ParamSpec:
    """Schema entry for one configurable parameter. Drives the UI form."""
    name: str
    type: str                       # "int" | "float" | "str" | "bool" | "choice"
    default: Any
    description: str = ""
    min: Optional[float] = None     # for numeric types
    max: Optional[float] = None
    choices: Optional[list] = None  # for "choice"


class StrategyContext(ABC):
    """
    Framework-injected interface. The strategy's only window into the world:
    order placement, position queries, history access, logging, state storage.

    Strategies use ONLY this context — never import brokers directly.
    """
    instance_id: str
    mode: str          # "backtest" | "paper" | "live"
    capital_allocated: Decimal
    params: dict
    state: dict        # persisted to DB on on_stop, restored on on_start

    # ── Order management ──────────────────────────────────────────────────────

    async def place_order(self, request: OrderRequest) -> Order:
        raise NotImplementedError

    async def cancel_order(self, client_order_id: str) -> bool:
        raise NotImplementedError

    async def modify_order(self, client_order_id: str, **changes) -> Order:
        raise NotImplementedError

    async def now(self) -> datetime:
        """"What time is it right now" -- environment-aware, not a bare
        datetime.now() call. Live/paper mode returns real wall-clock time;
        backtest mode returns the timestamp of the bar currently being
        processed. A strategy that needs a time-of-day or days-to-expiry
        gate (e.g. CP11's credit-spread strategy) must call this rather than
        datetime.now() directly -- calling datetime.now() in a strategy
        would make every backtest run only ever check against today's real
        date, regardless of which historical period it's replaying, so the
        gate would only pass by coincidence. Timezone-aware UTC; convert to
        the exchange's local zone at the call site."""
        raise NotImplementedError

    async def get_order(self, client_order_id: str) -> Optional[Order]:
        """Look up the current state of a previously-placed order by its
        client_order_id. Used by the multi-leg executor (CP11) to poll a
        leg that came back non-terminal (SUBMITTED/ACCEPTED) from a real
        broker connection -- paper/backtest brokers fill synchronously so
        this is only ever consulted for a live broker."""
        raise NotImplementedError

    # ── Convenience helpers ───────────────────────────────────────────────────

    async def buy(
        self,
        symbol: str,
        qty: int,
        *,
        price: Optional[Decimal] = None,
        tag: Optional[str] = None,
    ) -> Order:
        return await self.place_order(
            OrderRequest(
                symbol=symbol,
                side=Side.BUY,
                quantity=qty,
                order_type=OrderType.LIMIT if price else OrderType.MARKET,
                price=price,
                tag=tag,
            )
        )

    async def sell(
        self,
        symbol: str,
        qty: int,
        *,
        price: Optional[Decimal] = None,
        tag: Optional[str] = None,
    ) -> Order:
        return await self.place_order(
            OrderRequest(
                symbol=symbol,
                side=Side.SELL,
                quantity=qty,
                order_type=OrderType.LIMIT if price else OrderType.MARKET,
                price=price,
                tag=tag,
            )
        )

    # ── Alert-mode lifecycle helpers ──────────────────────────────────────────
    # Alert mode's signals form entry/exit pairs (target + stop-loss on entry,
    # then a later exit), unlike backtest/paper/live's single fire-and-forget
    # buy()/sell(). `tag` is the pairing key: pass the SAME tag to
    # alert_entry() and the later alert_exit() for the same setup instance
    # (e.g. f"{symbol}_{entry_ts}" if more than one concurrent setup on the
    # same symbol is possible) and the framework links them in signal_log
    # automatically -- no signal id to track in ctx.state yourself.

    async def alert_entry(
        self,
        symbol: str,
        side: Side,
        *,
        price: Optional[Decimal] = None,
        target: Optional[Decimal] = None,
        stop_loss: Optional[Decimal] = None,
        tag: Optional[str] = None,
    ) -> Order:
        return await self.place_order(
            OrderRequest(
                symbol=symbol,
                side=side,
                quantity=1,
                order_type=OrderType.LIMIT if price else OrderType.MARKET,
                price=price,
                tag=tag,
                signal_type="ENTER",
                target_price=target,
                stop_loss_price=stop_loss,
            )
        )

    async def alert_exit(
        self,
        symbol: str,
        side: Side,
        *,
        price: Optional[Decimal] = None,
        tag: Optional[str] = None,
    ) -> Order:
        return await self.place_order(
            OrderRequest(
                symbol=symbol,
                side=side,
                quantity=1,
                order_type=OrderType.LIMIT if price else OrderType.MARKET,
                price=price,
                tag=tag,
                signal_type="EXIT",
            )
        )

    # ── State queries ──────────────────────────────────────────────────────────

    def position(self, symbol: str) -> Optional[Position]:
        raise NotImplementedError

    def positions(self) -> list[Position]:
        raise NotImplementedError

    def open_orders(self) -> list[Order]:
        raise NotImplementedError

    def equity(self) -> Decimal:
        raise NotImplementedError

    def realised_pnl_today(self) -> Decimal:
        raise NotImplementedError

    # ── Historical data ────────────────────────────────────────────────────────

    async def history(self, symbol: str, timeframe: str, lookback: int) -> list[Bar]:
        """Returns up to `lookback` bars ending at the current moment.
        In backtest, returns up to the current simulated moment (no lookahead)."""
        raise NotImplementedError

    # ── Instrument resolution (options) ─────────────────────────────────────────
    # Options-specific extensions -- not generic "trading" concepts. A future
    # asset class (e.g. forex) should add its own equivalents (pip value, lot
    # sizing, session calendar) rather than overload these.

    async def get_spot(self, underlying: str) -> Decimal:
        """Current spot/index price for an underlying (e.g. "NIFTY")."""
        raise NotImplementedError

    async def resolve_strike(
        self, underlying: str, expiry_selector: str, strike_offset: int, opt_type: str,
    ) -> ResolvedInstrument:
        """Resolve an ATM/OTM/ITM strike request into a concrete, currently
        listed instrument. expiry_selector: "this_week" | "next_week" |
        "this_month" | "next_month". strike_offset: 0 = ATM, positive =
        further from ATM in the OTM direction for a call / ITM for a put."""
        raise NotImplementedError

    async def get_option_price(self, symbol: str, exchange: str) -> Decimal:
        """Current LTP for an already-resolved option tradingsymbol."""
        raise NotImplementedError

    async def subscribe_instrument(self, symbol: str, exchange: str) -> None:
        """Subscribe to live ticks for an instrument resolved at runtime (e.g.
        via resolve_strike) -- the static `instruments` list on the Strategy
        class only covers what's known at instance-creation time."""
        raise NotImplementedError

    # ── Logging ───────────────────────────────────────────────────────────────

    def log(self, level: str, message: str, **fields) -> None:
        raise NotImplementedError

    async def notify_critical(self, title: str, body: str) -> None:
        """Best-effort Telegram alert for events that need a human now (e.g.
        the multi-leg leg-failure protocol's FORCE_UNWOUND/HALTED_FOR_HUMAN
        outcomes, CP11). Falls back to a structured log line if no notifier
        is configured -- never raises, since a failed alert must not break
        the leg-failure protocol itself."""
        raise NotImplementedError


class Strategy(ABC):
    """
    Plugin contract. Every strategy file must export a class inheriting from this.
    Override only the hooks you need; the rest are no-ops by default.
    """

    # ── Class-level metadata (set as class attributes) ─────────────────────────
    name: str = ""
    version: str = "0.0.1"
    description: str = ""
    author: str = ""
    timeframe: str = "5m"
    instruments: list[str] = []

    # Parameter schema — auto-renders the config form in the dashboard
    params_schema: list[ParamSpec] = []

    # ── Lifecycle hooks ────────────────────────────────────────────────────────

    async def on_start(self, ctx: StrategyContext) -> None:
        """Called once when the strategy instance starts."""

    async def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        """Called when a new bar closes for a subscribed (symbol, timeframe)."""

    async def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        """Called on every tick. Override only for sub-bar reactivity."""

    async def on_order_update(self, order: Order, ctx: StrategyContext) -> None:
        """Called when one of this strategy's orders changes status."""

    async def on_stop(self, ctx: StrategyContext, reason: str) -> None:
        """Called on graceful shutdown, kill switch, or error pause."""

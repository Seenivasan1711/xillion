"""
Strategy plugin contract. Every strategy file must export exactly one class
that inherits from Strategy. The framework instantiates it and drives the
lifecycle hooks; strategy authors implement only what they need.
"""
from abc import ABC
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from xillion.core.events import Bar, Order, OrderRequest, OrderType, Position, Side, Tick


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

    # ── Logging ───────────────────────────────────────────────────────────────

    def log(self, level: str, message: str, **fields) -> None:
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

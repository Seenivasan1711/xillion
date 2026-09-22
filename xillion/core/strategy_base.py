"""
Strategy plugin contract. Every strategy file must export exactly one class
that inherits from Strategy. The framework instantiates it and drives the
lifecycle hooks; strategy authors implement only what they need.
"""

from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from xillion.core.events import Bar, Order, OrderRequest, OrderType, Position, Side, Tick
from xillion.core.instruments import ResolvedInstrument


@dataclass
class ParamSpec:
    """Schema entry for one configurable parameter. Drives the UI form."""

    name: str
    type: str  # "int" | "float" | "str" | "bool" | "choice"
    default: Any
    description: str = ""
    min: float | None = None  # for numeric types
    max: float | None = None
    choices: list | None = None  # for "choice"


def fill_param_defaults(strategy_cls: "type[Strategy]", params: dict) -> dict:
    """Merge `params_schema` defaults under whatever's explicitly given in
    `params` -- explicit values always win, missing keys get the schema
    default. The dashboard's instance-creation form always sends every
    param already (it seeds its own state from params_schema), so this
    gap was invisible there; it only bites a caller that goes around the
    UI (a direct API call, a script, the MCP server later) with a partial
    or empty params dict -- found for real 2026-09-21 when a `{}` params
    payload crashed on the strategy's very first `ctx.params["x"]` access,
    both for a live instance and for a provider-backed backtest run. Both
    call this before the params ever reach a strategy."""
    return {spec.name: params.get(spec.name, spec.default) for spec in strategy_cls.params_schema}


class StrategyContext(ABC):
    """
    Framework-injected interface. The strategy's only window into the world:
    order placement, position queries, history access, logging, state storage.

    Strategies use ONLY this context — never import brokers directly.
    """

    instance_id: str
    mode: str  # "backtest" | "paper" | "live"
    capital_allocated: Decimal
    params: dict
    state: dict  # persisted to DB on on_stop, restored on on_start

    # ── Order management ──────────────────────────────────────────────────────

    async def place_order(self, request: OrderRequest) -> Order:
        raise NotImplementedError

    async def cancel_order(self, client_order_id: str) -> bool:
        raise NotImplementedError

    async def modify_order(self, client_order_id: str, **changes) -> Order:
        raise NotImplementedError

    async def now(self) -> datetime:
        """ "What time is it right now" -- environment-aware, not a bare
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

    async def get_order(self, client_order_id: str) -> Order | None:
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
        price: Decimal | None = None,
        tag: str | None = None,
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
        price: Decimal | None = None,
        tag: str | None = None,
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
        price: Decimal | None = None,
        target: Decimal | None = None,
        stop_loss: Decimal | None = None,
        tag: str | None = None,
        reason: str | None = None,
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
                reason=reason,
            )
        )

    async def alert_exit(
        self,
        symbol: str,
        side: Side,
        *,
        price: Decimal | None = None,
        tag: str | None = None,
        reason: str | None = None,
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
                reason=reason,
            )
        )

    # ── State queries ──────────────────────────────────────────────────────────

    def position(self, symbol: str) -> Position | None:
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
        self,
        underlying: str,
        expiry_selector: str,
        strike_offset: int,
        opt_type: str,
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

    # ── Protective GTT / Forever Orders (CP11 follow-up) ────────────────────

    async def place_protective_gtt(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        stop_price: Decimal,
        target_price: Decimal | None,
        last_price: Decimal,
    ) -> str | None:
        """Best-effort broker-native protective trigger, alongside (not
        instead of) the software stop this codebase already runs -- see
        xillion/core/protective_orders.py's module docstring for why both
        exist. Returns the broker's trigger id if one was placed, or None
        if the connected broker doesn't support this
        (capabilities.supports_gtt_orders is False, e.g. paper/backtest
        mode) -- callers must treat None as "no broker-native protection
        exists," not as an error, since the software stop is still active
        either way."""
        raise NotImplementedError

    async def cancel_gtt(self, gtt_id: str) -> None:
        """Cancel a GTT placed via place_protective_gtt -- call this when
        the software path closes the position through any other route, so
        the broker-side trigger doesn't fire later against a position that
        no longer exists. A no-op if gtt_id is falsy."""
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

    async def notify(self, title: str, body: str, severity: str = "info") -> None:
        """Best-effort Telegram notification for routine events a human
        wants to see but that aren't urgent (e.g. a paper/live trade's
        real entry/exit fill and outcome) -- `notify_critical` above is
        reserved for events that need attention *now*. Same falls-back-to-
        a-log-line, never-raises contract."""
        raise NotImplementedError

    async def news_veto_active(self) -> bool:
        """True if a high-impact economic release is imminent and a
        strategy's own "don't enter near red-folder news" rule should skip
        firing (added 2026-09-22 for Gold Sweep-Reversal's ritual check,
        generic to any strategy that wants it). Routes through the same
        DB-configured credential (Settings -> Finnhub) a strategy plugin
        must never reach directly -- see xillion/core's "no DB/auth
        imports in strategies/*.py" convention. Best-effort: returns False
        (no veto) rather than raising if the check can't actually run
        (unconfigured, or the provider's plan doesn't support it)."""
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

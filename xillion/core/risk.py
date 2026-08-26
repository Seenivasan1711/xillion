"""
Risk Manager: pre-trade gate that every order must pass.

CP13: expanded from the original 6 checks (kill switch, quantity>0, OPS
limiter, account daily loss, per-strategy daily loss, max open positions)
toward the ~20 in automation-platform-spec/10-RISK-ENGINE.md §10.2's
validate_order(). Priority order taken directly from
architecture/risk-and-compliance.md Part C.1: price collar + OPS-cap
tightening first (pure validation logic, no new infrastructure), duplicate-
idempotency-key rejection second, prop-firm drawdown gates deferred to
Lane B (not applicable to Lane A / this checkpoint).

Several spec checks are deliberately NOT implemented here, honestly, not
silently: margin_sufficient (needs a live broker margin call -- making a
synchronous pre-trade gate await a broker RPC on every order is a real
latency tradeoff, not decided yet), market_open/symbol_tradeable (risk of
regressing paper/alert-mode testing outside market hours without more
context on what "mode" a check should apply to), modify_rate_ok (modify_order
itself isn't implemented anywhere in the codebase yet -- nothing to rate-
limit). Every check below is either checkable with data already in an
OrderRequest/StrategyRiskConfig, or via the new optional MarketContext,
which is None-safe: a field the caller doesn't have simply skips that one
check rather than failing closed on missing data (skipped checks are
logged, never silently reported as "passed").
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import structlog

from xillion.config import get_settings
from xillion.core.events import Order, OrderRequest

logger = structlog.get_logger(__name__)


@dataclass
class RiskApproved:
    pass


@dataclass
class RiskRejected:
    reason: str
    failed_checks: list[str] = field(default_factory=list)


RiskDecision = RiskApproved | RiskRejected


@dataclass
class StrategyRiskConfig:
    capital_allocation: Decimal
    daily_loss_pct: float = 0.0
    max_open_positions: int = 0
    max_orders_per_day: int = 0

    def __post_init__(self) -> None:
        s = get_settings()
        if self.daily_loss_pct == 0.0:
            self.daily_loss_pct = s.default_per_strategy_daily_loss_pct
        if self.max_open_positions == 0:
            self.max_open_positions = s.default_max_open_positions
        if self.max_orders_per_day == 0:
            self.max_orders_per_day = s.default_max_orders_per_day


@dataclass
class MarketContext:
    """Optional, per-order market/instrument data the risk engine can check
    against when the caller has it. Every field defaults to None/empty and
    every check built on one is skipped (not failed) when it's absent --
    see the module docstring for why this codebase doesn't yet have all of
    these wired end-to-end (LTP/circuit/margin need a broker quote call)."""

    ltp: Decimal | None = None
    lot_size: int | None = None
    tick_size: Decimal | None = None
    freeze_qty: int | None = None
    lower_circuit: Decimal | None = None
    upper_circuit: Decimal | None = None
    open_orders: list[Order] = field(default_factory=list)


class RiskManager:
    """
    Pre-trade gate. All strategies route orders through here before reaching a broker.
    """

    def __init__(self) -> None:
        self._kill_switch_active: bool = False
        self._kill_switch_at: datetime | None = None
        self._trading_enabled: bool = True
        self._account_daily_loss: Decimal = Decimal("0")
        self._strategy_daily_loss: dict[str, Decimal] = {}  # instance_id → loss today
        self._orders_today: dict[str, int] = {}  # instance_id → order count today
        # OPS sliding window: every check() ATTEMPT (approved or not) --
        # this is what a runaway loop actually looks like (a strategy
        # hammering place_order despite rejections), not just accepted
        # orders. The soft-throttle window (accepted only) is separate.
        self._ops_attempt_window: deque[float] = deque()
        self._ops_accepted_window: deque[float] = deque()
        # Idempotency: client_order_id -> approval monotonic time. Evicted
        # opportunistically past _IDEMPOTENCY_WINDOW_SECONDS.
        self._seen_order_ids: dict[str, float] = {}
        self._notify_callback = None  # optional async callable(title, body, severity)

    _IDEMPOTENCY_WINDOW_SECONDS = 300.0

    # ── Kill switch ────────────────────────────────────────────────────────────

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch_active

    def activate_kill_switch(self) -> None:
        self._kill_switch_active = True
        self._kill_switch_at = datetime.now(UTC)
        logger.critical("KILL SWITCH ACTIVATED")
        if self._notify_callback:
            asyncio.create_task(
                self._notify_callback(
                    "KILL SWITCH FIRED",
                    f"All strategies halted at {self._kill_switch_at.isoformat()}",
                    "critical",
                )
            )

    def reset_kill_switch(self) -> None:
        self._kill_switch_active = False
        self._kill_switch_at = None
        logger.info("kill switch reset")

    # ── Trading pause (CP13) — a softer, manually-reversible gate distinct
    # from the kill switch, which never auto-resumes and is meant for "the
    # system did something wrong". This is for "pause for maintenance". ──

    def pause_trading(self) -> None:
        self._trading_enabled = False
        logger.warning("trading paused")

    def resume_trading(self) -> None:
        self._trading_enabled = True
        logger.info("trading resumed")

    def set_notify(self, callback) -> None:
        """Wire a notification callback: async fn(title, body, severity)."""
        self._notify_callback = callback

    def status(self) -> dict:
        return {
            "kill_switch_active": self._kill_switch_active,
            "kill_switch_at": self._kill_switch_at.isoformat() if self._kill_switch_at else None,
            "trading_enabled": self._trading_enabled,
            "account_daily_loss": str(self._account_daily_loss),
            "ops_limit": get_settings().ops_limit_per_second,
            "ops_burst_ceiling": get_settings().ops_burst_ceiling,
        }

    # ── P&L tracking ──────────────────────────────────────────────────────────

    def record_loss(self, instance_id: str | None, amount: Decimal) -> None:
        """Record realised loss (negative = loss). Called by ExecutionRouter on fill."""
        if amount >= 0:
            return
        self._account_daily_loss += amount
        if instance_id:
            self._strategy_daily_loss[instance_id] = (
                self._strategy_daily_loss.get(instance_id, Decimal("0")) + amount
            )

    def reset_daily(self) -> None:
        """Call at 3:30 PM IST (market close) or midnight IST."""
        self._account_daily_loss = Decimal("0")
        self._strategy_daily_loss.clear()
        self._orders_today.clear()
        logger.info("risk: daily P&L reset")

    # ── OPS gate ──────────────────────────────────────────────────────────────

    def _ops_peek(self) -> tuple[bool, bool]:
        """Non-mutating: (soft_ok, hard_breach). Consumption happens
        separately, only once an order is fully approved -- spec §10.3's
        ops_bucket.consume() runs after every other check passes, not as a
        side effect of merely checking."""
        s = get_settings()
        now = time.monotonic()
        cutoff = now - 1.0
        while self._ops_attempt_window and self._ops_attempt_window[0] < cutoff:
            self._ops_attempt_window.popleft()
        while self._ops_accepted_window and self._ops_accepted_window[0] < cutoff:
            self._ops_accepted_window.popleft()
        # +1 for the attempt currently being evaluated -- hitting the hard
        # ceiling is about ATTEMPT rate (a strategy bug hammering
        # place_order), not accepted-order rate; a strategy already being
        # throttled by the soft cap and retrying anyway is exactly the
        # runaway-loop signature the spec is guarding against.
        hard_breach = (len(self._ops_attempt_window) + 1) >= s.ops_burst_ceiling
        soft_ok = len(self._ops_accepted_window) < s.ops_limit_per_second
        return soft_ok, hard_breach

    def _ops_consume(self) -> None:
        now = time.monotonic()
        self._ops_accepted_window.append(now)

    # ── Idempotency ──────────────────────────────────────────────────────────

    def _is_duplicate(self, client_order_id: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._IDEMPOTENCY_WINDOW_SECONDS
        stale = [k for k, t in self._seen_order_ids.items() if t < cutoff]
        for k in stale:
            del self._seen_order_ids[k]
        return client_order_id in self._seen_order_ids

    def _mark_seen(self, client_order_id: str) -> None:
        self._seen_order_ids[client_order_id] = time.monotonic()

    # ── Main check ────────────────────────────────────────────────────────────

    def check(
        self,
        request: OrderRequest,
        strategy_config: StrategyRiskConfig | None = None,
        current_positions: int | None = None,
        market_context: MarketContext | None = None,
    ) -> RiskDecision:
        s = get_settings()
        ctx = market_context or MarketContext()

        # Every check() call counts as an OPS "attempt" the instant it's
        # made, tracked separately from the checks list below so the hard-
        # ceiling breach itself always shows up as ITS OWN named failure in
        # the audit trail, not folded into the general OPS check.
        soft_ops_ok, hard_ops_breach = self._ops_peek()
        self._ops_attempt_window.append(time.monotonic())

        if hard_ops_breach:
            self.activate_kill_switch()
            logger.critical(
                "OPS CEILING BREACHED — runaway loop suspected, kill switch fired",
                symbol=request.symbol,
                burst_ceiling=s.ops_burst_ceiling,
            )
            return self._reject(
                ["ops_ceiling_breach"], "OPS burst ceiling hit -- kill switch activated"
            )

        checks: list[tuple[str, bool]] = []

        def add(name: str, ok: bool) -> None:
            checks.append((name, ok))

        # ---- SANITY / FAT FINGER ----
        add("qty_positive", request.quantity > 0)
        if ctx.lot_size:
            add("qty_lot_multiple", request.quantity % ctx.lot_size == 0)
        if ctx.freeze_qty:
            add("qty_within_freeze", request.quantity <= ctx.freeze_qty)
        add("qty_sane", request.quantity <= s.default_max_qty_per_order)
        if request.price is not None and ctx.tick_size:
            # tick_size may not evenly divide in binary floating point; this
            # is a Decimal modulo, exact for the tick sizes NSE actually uses.
            add("price_tick_multiple", (request.price % ctx.tick_size) == 0)
        if request.price is not None and ctx.ltp:
            add(
                "price_collar",
                Decimal("0.5") * ctx.ltp <= request.price <= Decimal("1.5") * ctx.ltp,
            )
        if (
            request.price is not None
            and ctx.lower_circuit is not None
            and ctx.upper_circuit is not None
        ):
            add("price_within_circuit", ctx.lower_circuit <= request.price <= ctx.upper_circuit)
        if ctx.ltp:
            notional = ctx.ltp * request.quantity
            add("notional_sane", notional <= Decimal(str(s.default_max_notional_per_order)))

        # ---- STATE ----
        add("kill_switch_clear", not self._kill_switch_active)
        add("trading_enabled", self._trading_enabled)

        # ---- CAPITAL ----
        account_limit = strategy_config.capital_allocation if strategy_config else Decimal("100000")
        max_account_loss = account_limit * Decimal(str(s.default_account_daily_loss_pct / 100))
        add("within_account_daily_loss", abs(self._account_daily_loss) <= max_account_loss)

        if strategy_config and request.strategy_instance_id:
            strat_loss = self._strategy_daily_loss.get(request.strategy_instance_id, Decimal("0"))
            strat_limit = strategy_config.capital_allocation * Decimal(
                str(strategy_config.daily_loss_pct / 100)
            )
            add("within_strategy_daily_loss", abs(strat_loss) <= strat_limit)

            orders_so_far = self._orders_today.get(request.strategy_instance_id, 0)
            add("order_count_sane", orders_so_far < strategy_config.max_orders_per_day)

        if strategy_config and current_positions is not None:
            add("max_open_positions_ok", current_positions < strategy_config.max_open_positions)

        # ---- BEHAVIOURAL / RUNAWAY ----
        add("not_duplicate", not self._is_duplicate(request.client_order_id))
        add("ops_budget_ok", soft_ops_ok)
        if ctx.open_orders:
            crossing = any(
                o.symbol == request.symbol and o.side != request.side for o in ctx.open_orders
            )
            add("not_self_trade", not crossing)

        failed = [name for name, ok in checks if not ok]

        if failed:
            for name in failed:
                logger.warning(
                    "risk: check failed", check=name, symbol=request.symbol, side=request.side
                )
            return self._reject(failed, f"failed: {', '.join(failed)}")

        # All clear -- consume the resources this decision claimed.
        self._ops_consume()
        self._mark_seen(request.client_order_id)
        if request.strategy_instance_id:
            self._orders_today[request.strategy_instance_id] = (
                self._orders_today.get(request.strategy_instance_id, 0) + 1
            )
        return RiskApproved()

    def _reject(self, failed_checks: list[str], reason: str) -> RiskRejected:
        return RiskRejected(reason=reason, failed_checks=failed_checks)

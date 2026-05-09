"""
Risk Manager: pre-trade gate that every order must pass.
Phase 5 implementation: OPS limiter, daily loss gates, kill switch, position limits.
"""
import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import structlog

from xillion.config import get_settings
from xillion.core.events import OrderRequest

logger = structlog.get_logger(__name__)


@dataclass
class RiskApproved:
    pass


@dataclass
class RiskRejected:
    reason: str


RiskDecision = RiskApproved | RiskRejected


@dataclass
class StrategyRiskConfig:
    capital_allocation: Decimal
    daily_loss_pct: float = 0.0
    max_open_positions: int = 0

    def __post_init__(self) -> None:
        s = get_settings()
        if self.daily_loss_pct == 0.0:
            self.daily_loss_pct = s.default_per_strategy_daily_loss_pct
        if self.max_open_positions == 0:
            self.max_open_positions = s.default_max_open_positions


class RiskManager:
    """
    Pre-trade gate. All strategies route orders through here before reaching a broker.
    """

    def __init__(self) -> None:
        self._kill_switch_active: bool = False
        self._kill_switch_at: Optional[datetime] = None
        self._account_daily_loss: Decimal = Decimal("0")
        self._strategy_daily_loss: dict[str, Decimal] = {}  # instance_id → loss today
        # OPS sliding window: stores timestamps of recent order submissions
        self._ops_window: deque[float] = deque()
        self._notify_callback = None  # optional async callable(title, body, severity)

    # ── Kill switch ────────────────────────────────────────────────────────────

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch_active

    def activate_kill_switch(self) -> None:
        self._kill_switch_active = True
        self._kill_switch_at = datetime.now(timezone.utc)
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

    def set_notify(self, callback) -> None:
        """Wire a notification callback: async fn(title, body, severity)."""
        self._notify_callback = callback

    def status(self) -> dict:
        return {
            "kill_switch_active": self._kill_switch_active,
            "kill_switch_at": self._kill_switch_at.isoformat() if self._kill_switch_at else None,
            "account_daily_loss": str(self._account_daily_loss),
            "ops_limit": get_settings().ops_limit_per_second,
        }

    # ── P&L tracking ──────────────────────────────────────────────────────────

    def record_loss(self, instance_id: Optional[str], amount: Decimal) -> None:
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
        logger.info("risk: daily P&L reset")

    # ── OPS gate ──────────────────────────────────────────────────────────────

    def _ops_check(self) -> Optional[str]:
        now = time.monotonic()
        limit = get_settings().ops_limit_per_second
        cutoff = now - 1.0
        while self._ops_window and self._ops_window[0] < cutoff:
            self._ops_window.popleft()
        if len(self._ops_window) >= limit:
            return f"OPS limit {limit}/s reached — order throttled"
        self._ops_window.append(now)
        return None

    # ── Main check ────────────────────────────────────────────────────────────

    def check(
        self,
        request: OrderRequest,
        strategy_config: Optional[StrategyRiskConfig] = None,
        current_positions: Optional[int] = None,
    ) -> RiskDecision:
        s = get_settings()

        if self._kill_switch_active:
            return RiskRejected(reason="kill switch is active")

        if request.quantity <= 0:
            return RiskRejected(reason=f"invalid quantity {request.quantity}")

        # OPS limiter
        ops_err = self._ops_check()
        if ops_err:
            logger.warning("risk: OPS limit", error=ops_err)
            return RiskRejected(reason=ops_err)

        # Account daily loss gate
        account_limit = strategy_config.capital_allocation if strategy_config else Decimal("100000")
        max_account_loss = account_limit * Decimal(str(s.default_account_daily_loss_pct / 100))
        if abs(self._account_daily_loss) > max_account_loss:
            return RiskRejected(
                reason=f"account daily loss limit hit (loss: {self._account_daily_loss})"
            )

        # Per-strategy daily loss gate
        if strategy_config and request.strategy_instance_id:
            strat_loss = self._strategy_daily_loss.get(request.strategy_instance_id, Decimal("0"))
            strat_limit = strategy_config.capital_allocation * Decimal(
                str(strategy_config.daily_loss_pct / 100)
            )
            if abs(strat_loss) > strat_limit:
                return RiskRejected(
                    reason=f"strategy daily loss limit hit (loss: {strat_loss})"
                )

        # Max open positions gate
        if (
            strategy_config
            and current_positions is not None
            and current_positions >= strategy_config.max_open_positions
        ):
            return RiskRejected(
                reason=f"max open positions ({strategy_config.max_open_positions}) reached"
            )

        return RiskApproved()

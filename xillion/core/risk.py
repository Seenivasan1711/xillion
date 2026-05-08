"""
Risk Manager: pre-trade gate that every order must pass.
Returns Approved or Rejected(reason) before the order goes to a broker.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import structlog

from xillion.config import settings
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
        if self.daily_loss_pct == 0.0:
            self.daily_loss_pct = settings.default_per_strategy_daily_loss_pct
        if self.max_open_positions == 0:
            self.max_open_positions = settings.default_max_open_positions


class RiskManager:
    """
    Pre-trade gate. All strategies route orders through here.
    In Phase 1-2 this is intentionally simple; full implementation is Phase 5.
    """

    def __init__(self) -> None:
        self._kill_switch_active: bool = False
        self._ops_counter: list[float] = []
        self._account_realised_pnl: Decimal = Decimal("0")

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch_active

    def activate_kill_switch(self) -> None:
        self._kill_switch_active = True
        logger.critical("KILL SWITCH ACTIVATED")

    def reset_kill_switch(self) -> None:
        self._kill_switch_active = False
        logger.info("kill switch reset")

    def check(
        self,
        request: OrderRequest,
        strategy_config: Optional[StrategyRiskConfig] = None,
        current_positions: Optional[int] = None,
    ) -> RiskDecision:
        if self._kill_switch_active:
            return RiskRejected(reason="kill switch is active")

        if request.quantity <= 0:
            return RiskRejected(reason=f"invalid quantity {request.quantity}")

        if (
            strategy_config
            and current_positions is not None
            and current_positions >= strategy_config.max_open_positions
        ):
            return RiskRejected(
                reason=f"max open positions ({strategy_config.max_open_positions}) reached"
            )

        return RiskApproved()

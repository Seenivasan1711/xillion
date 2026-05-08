"""
Execution Router: receives risk-approved order requests, routes to the
appropriate broker plugin, tracks order state, updates positions.
"""
from datetime import datetime, timezone
from typing import Optional

import structlog

from xillion.core.broker_base import Broker
from xillion.core.events import Order, OrderRequest, OrderStatus, Position
from xillion.core.risk import RiskDecision, RiskManager, RiskRejected

logger = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ExecutionRouter:
    """
    Routes orders through Risk → Broker. Tracks order and position state
    in memory (source of truth is the DB, populated by the strategy engine).
    """

    def __init__(self, broker: Broker, risk_manager: RiskManager) -> None:
        self._broker = broker
        self._risk = risk_manager
        self._orders: dict[str, Order] = {}

    async def submit(self, request: OrderRequest) -> Order:
        decision: RiskDecision = self._risk.check(request)
        if isinstance(decision, RiskRejected):
            logger.warning(
                "order rejected by risk manager",
                reason=decision.reason,
                symbol=request.symbol,
                side=request.side,
                qty=request.quantity,
            )
            now = _now()
            rejected = Order(
                client_order_id=request.client_order_id,
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
                order_type=request.order_type,
                status=OrderStatus.REJECTED,
                submitted_at=now,
                updated_at=now,
                rejection_reason=decision.reason,
                strategy_instance_id=request.strategy_instance_id,
                tag=request.tag,
            )
            self._orders[rejected.client_order_id] = rejected
            return rejected

        order = await self._broker.place_order(request)
        self._orders[order.client_order_id] = order
        logger.info(
            "order submitted",
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            qty=order.quantity,
            status=order.status,
        )
        return order

    async def cancel(self, client_order_id: str) -> bool:
        order = self._orders.get(client_order_id)
        if not order or not order.broker_order_id:
            return False
        return await self._broker.cancel_order(order.broker_order_id)

    def get_order(self, client_order_id: str) -> Optional[Order]:
        return self._orders.get(client_order_id)

    def get_open_orders(
        self, strategy_instance_id: Optional[str] = None
    ) -> list[Order]:
        open_statuses = {OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.ACCEPTED, OrderStatus.PARTIAL}
        orders = [o for o in self._orders.values() if o.status in open_statuses]
        if strategy_instance_id:
            orders = [o for o in orders if o.strategy_instance_id == strategy_instance_id]
        return orders

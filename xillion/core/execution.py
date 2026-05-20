"""
Execution Router: receives risk-approved order requests, routes to the
appropriate broker plugin, persists order/fill records to DB, and tracks
order state.
"""
import asyncio
from datetime import date, datetime, timezone
from typing import Optional

import structlog

from xillion.core.broker_base import Broker
from xillion.core.events import Order, OrderRequest, OrderStatus, Position
from xillion.core.risk import RiskDecision, RiskManager, RiskRejected

logger = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


class ExecutionRouter:
    """
    Routes orders through Risk → Broker. Persists OrderRecord + FillRecord
    to DB on fill. Tracks order state in memory for fast access.
    """

    def __init__(
        self,
        broker: Broker,
        risk_manager: RiskManager,
        db_factory=None,
        broker_connection_id: Optional[int] = None,
    ) -> None:
        self._broker = broker
        self._risk = risk_manager
        self._db_factory = db_factory
        self._broker_connection_id = broker_connection_id
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

        # Fire-and-forget DB persistence — does not block strategy execution
        if self._db_factory is not None and self._broker_connection_id is not None:
            asyncio.create_task(self._persist_order(order))

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
        open_statuses = {
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIAL,
        }
        orders = [o for o in self._orders.values() if o.status in open_statuses]
        if strategy_instance_id:
            orders = [o for o in orders if o.strategy_instance_id == strategy_instance_id]
        return orders

    # ── DB persistence ─────────────────────────────────────────────────────────

    async def _persist_order(self, order: Order) -> None:
        """Write OrderRecord + FillRecord and increment today's order count."""
        from xillion.db.models import DailyRiskState, FillRecord, OrderRecord

        today = date.today().isoformat()
        now = _now_iso()

        try:
            async with self._db_factory()() as session:
                # Upsert OrderRecord
                existing = await session.get(OrderRecord, order.client_order_id)
                if existing is None:
                    rec = OrderRecord(
                        id=order.client_order_id,
                        broker_order_id=order.broker_order_id,
                        broker_connection_id=self._broker_connection_id,
                        strategy_instance_id=order.strategy_instance_id,
                        symbol=order.symbol,
                        exchange="NSE",
                        side=order.side.value,
                        quantity=order.quantity,
                        filled_quantity=order.filled_quantity,
                        order_type=order.order_type.value,
                        price=float(order.price) if order.price else None,
                        stop_price=None,
                        status=order.status.value,
                        avg_fill_price=float(order.avg_fill_price) if order.avg_fill_price else None,
                        rejection_reason=order.rejection_reason,
                        tag=order.tag,
                        submitted_at=order.submitted_at.isoformat(),
                        updated_at=now,
                    )
                    session.add(rec)
                else:
                    existing.status = order.status.value
                    existing.filled_quantity = order.filled_quantity
                    existing.avg_fill_price = float(order.avg_fill_price) if order.avg_fill_price else None
                    existing.updated_at = now

                # Write FillRecord if order is filled
                if order.status == OrderStatus.FILLED and order.avg_fill_price:
                    fill = FillRecord(
                        order_id=order.client_order_id,
                        symbol=order.symbol,
                        side=order.side.value,
                        quantity=order.filled_quantity,
                        price=float(order.avg_fill_price),
                        fees=0.0,
                        ts=now,
                    )
                    session.add(fill)

                # Increment today's order count in DailyRiskState
                risk_row = await session.get(DailyRiskState, today)
                if risk_row is None:
                    risk_row = DailyRiskState(
                        trading_date=today,
                        account_realised_pnl=0.0,
                        account_unrealised_pnl=0.0,
                        total_orders_placed=1,
                        kill_switch_active=False,
                    )
                    session.add(risk_row)
                else:
                    risk_row.total_orders_placed = (risk_row.total_orders_placed or 0) + 1

                await session.commit()

        except Exception as exc:
            logger.error(
                "persist_order failed",
                client_order_id=order.client_order_id,
                error=str(exc),
            )

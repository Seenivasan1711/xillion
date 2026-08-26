"""
Execution Router: receives risk-approved order requests, routes to the
appropriate broker plugin, persists order/fill records to DB, and tracks
order state.
"""

import asyncio
from datetime import UTC, date, datetime

import structlog

from xillion.core.broker_base import Broker
from xillion.core.events import Order, OrderRequest, OrderStatus
from xillion.core.risk import (
    MarketContext,
    RiskDecision,
    RiskManager,
    RiskRejected,
    StrategyRiskConfig,
)

logger = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


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
        broker_connection_id: int | None = None,
        risk_config: StrategyRiskConfig | None = None,
    ) -> None:
        self._broker = broker
        self._risk = risk_manager
        self._db_factory = db_factory
        self._broker_connection_id = broker_connection_id
        self._orders: dict[str, Order] = {}
        # Was previously never passed to risk.check() at all, silently
        # disabling per-strategy daily-loss and max-open-positions gates for
        # every live/paper order regardless of what the UI showed as
        # configured (see docs/status/task-tracker.md CP9). set_risk_config()
        # is the hot-reload path -- PATCH /instances/{id} updates this same
        # object in place on the running instance, no restart needed.
        self.risk_config = risk_config

    def set_risk_config(self, risk_config: StrategyRiskConfig) -> None:
        self.risk_config = risk_config

    async def submit(
        self,
        request: OrderRequest,
        current_positions: int | None = None,
        market_context: MarketContext | None = None,
    ) -> Order:
        # CP13's not_self_trade check needs this instance's own open orders;
        # build it here rather than requiring every caller to pass it, same
        # as current_positions is already computed by the caller today.
        ctx = market_context or MarketContext()
        if not ctx.open_orders:
            ctx.open_orders = self.get_open_orders(request.strategy_instance_id)

        decision: RiskDecision = self._risk.check(
            request,
            strategy_config=self.risk_config,
            current_positions=current_positions,
            market_context=ctx,
        )
        # CP13: every decision (approved or rejected) is recorded to the
        # append-only audit log -- xillion/core/audit.py's AuditLog/
        # AuditLogRecord existed since early on but nothing ever called
        # .record(), so risk decisions were previously only ever visible in
        # structlog output, not in the durable, hash-chained audit trail
        # the automation spec needs. AWAITED, not fire-and-forget, unlike
        # _persist_order/_persist_trade_close below -- the spec's K04 job
        # is explicit that order-event/risk-decision audit writes are
        # synchronous on the critical path ("an unlogged order must not
        # reach the broker"), unlike the non-critical bookkeeping those
        # other writes represent.
        if self._db_factory is not None:
            await self._audit_risk_decision(request, decision)

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

    async def _audit_risk_decision(self, request: OrderRequest, decision: RiskDecision) -> None:
        from xillion.core.audit import AuditLog

        approved = isinstance(decision, RiskRejected) is False
        # dict[str, object]: this is a loose JSON-like audit payload with
        # heterogeneous value types (str/int/bool, plus list[str] appended
        # below) -- narrower inference from the literal above would reject
        # the failed_checks/reason assignment even though it's correct.
        payload: dict[str, object] = {
            "client_order_id": request.client_order_id,
            "symbol": request.symbol,
            "side": request.side.value,
            "quantity": request.quantity,
            "approved": approved,
        }
        if isinstance(decision, RiskRejected):
            payload["failed_checks"] = decision.failed_checks
            payload["reason"] = decision.reason
        try:
            await AuditLog(self._db_factory()).record(
                event_type="risk_decision",
                payload=payload,
                actor_type="strategy",
                actor_id=request.strategy_instance_id,
            )
        except Exception as exc:
            logger.error("audit_risk_decision failed", error=str(exc))

    async def cancel(self, client_order_id: str) -> bool:
        order = self._orders.get(client_order_id)
        if not order or not order.broker_order_id:
            return False
        return await self._broker.cancel_order(order.broker_order_id)

    def get_order(self, client_order_id: str) -> Order | None:
        return self._orders.get(client_order_id)

    def get_open_orders(self, strategy_instance_id: str | None = None) -> list[Order]:
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
                        avg_fill_price=(
                            float(order.avg_fill_price) if order.avg_fill_price else None
                        ),
                        rejection_reason=order.rejection_reason,
                        tag=order.tag,
                        submitted_at=order.submitted_at.isoformat(),
                        updated_at=now,
                    )
                    session.add(rec)
                else:
                    existing.status = order.status.value
                    existing.filled_quantity = order.filled_quantity
                    existing.avg_fill_price = (
                        float(order.avg_fill_price) if order.avg_fill_price else None
                    )
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

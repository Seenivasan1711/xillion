"""
CP13's Verify line: "a deliberately fat-fingered order is rejected before it
reaches the broker adapter, with the specific failed check named in the
audit log." xillion/core/audit.py's AuditLog/AuditLogRecord existed since
early on but nothing ever called .record() -- risk decisions were only ever
visible in structlog output. ExecutionRouter.submit() now writes every
decision here, synchronously (spec's K04: order-event audit writes are on
the critical path, not fire-and-forget).
"""
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from brokers._dummy import DummyBroker
from xillion.core.events import Order, OrderRequest, OrderStatus, OrderType, Side
from xillion.core.execution import ExecutionRouter
from xillion.core.risk import MarketContext, RiskManager, StrategyRiskConfig
from xillion.db.models import AuditLogRecord
from xillion.db.session import get_session_factory, init_db


class _RestingOrderBroker(DummyBroker):
    """Leaves the order ACCEPTED (resting), not FILLED -- so it shows up
    via ExecutionRouter.get_open_orders() for the self-trade guard to see."""

    async def place_order(self, request: OrderRequest) -> Order:
        now = datetime.now(timezone.utc)
        order = Order(
            client_order_id=request.client_order_id, symbol=request.symbol, side=request.side,
            quantity=request.quantity, order_type=request.order_type, status=OrderStatus.ACCEPTED,
            submitted_at=now, updated_at=now, price=request.price,
            strategy_instance_id=request.strategy_instance_id,
        )
        self.placed_orders.append(order)
        return order


def _order(price=None, qty: int = 1) -> OrderRequest:
    return OrderRequest(
        symbol="NIFTY", side=Side.BUY, quantity=qty,
        order_type=OrderType.LIMIT if price else OrderType.MARKET,
        price=Decimal(str(price)) if price else None,
        strategy_instance_id="audit-test-instance",
    )


async def _risk_decision_events() -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(AuditLogRecord).where(AuditLogRecord.event_type == "risk_decision")
            .order_by(AuditLogRecord.id.desc())
        )
        rows = result.scalars().all()
    return [json.loads(r.payload_json) for r in rows]


@pytest.mark.asyncio
async def test_fat_fingered_price_is_rejected_before_reaching_the_broker():
    await init_db()
    broker = DummyBroker()
    router = ExecutionRouter(
        broker, RiskManager(), db_factory=get_session_factory,
        risk_config=StrategyRiskConfig(capital_allocation=Decimal("100000")),
    )
    ctx = MarketContext(ltp=Decimal("100"))  # a real 10x fat-finger vs this LTP

    order = await router.submit(_order(price=1000), market_context=ctx)

    assert order.status.value == "REJECTED"
    assert broker.placed_orders == []  # never reached the broker adapter


@pytest.mark.asyncio
async def test_rejection_names_the_specific_failed_check_in_the_audit_log():
    await init_db()
    broker = DummyBroker()
    router = ExecutionRouter(
        broker, RiskManager(), db_factory=get_session_factory,
        risk_config=StrategyRiskConfig(capital_allocation=Decimal("100000")),
    )
    ctx = MarketContext(ltp=Decimal("100"))

    order = await router.submit(_order(price=1000), market_context=ctx)
    assert order.status.value == "REJECTED"

    events = await _risk_decision_events()
    assert events, "no risk_decision was ever written to the audit log"
    latest = events[0]
    assert latest["approved"] is False
    assert "price_collar" in latest["failed_checks"]
    assert latest["symbol"] == "NIFTY"


@pytest.mark.asyncio
async def test_approved_decisions_are_also_audited():
    await init_db()
    broker = DummyBroker()
    router = ExecutionRouter(
        broker, RiskManager(), db_factory=get_session_factory,
        risk_config=StrategyRiskConfig(capital_allocation=Decimal("100000")),
    )
    order = await router.submit(_order())
    assert order.status.value == "FILLED"

    events = await _risk_decision_events()
    assert events[0]["approved"] is True


@pytest.mark.asyncio
async def test_self_trade_guard_blocked_before_broker_via_full_router():
    """End-to-end through the real ExecutionRouter (not RiskManager
    directly): an opposite-side open order on the same symbol, from the
    router's own get_open_orders(), blocks a new order without the caller
    having to build MarketContext.open_orders by hand."""
    await init_db()
    broker = _RestingOrderBroker()
    router = ExecutionRouter(
        broker, RiskManager(), db_factory=get_session_factory,
        risk_config=StrategyRiskConfig(capital_allocation=Decimal("100000")),
    )
    sell_req = OrderRequest(
        symbol="NIFTY", side=Side.SELL, quantity=1, order_type=OrderType.LIMIT,
        price=Decimal("100"), strategy_instance_id="audit-test-instance",
    )
    first = await router.submit(sell_req)
    assert first.status.value == "ACCEPTED"

    buy_req = _order()
    second = await router.submit(buy_req)
    assert second.status.value == "REJECTED"
    assert "not_self_trade" in second.rejection_reason

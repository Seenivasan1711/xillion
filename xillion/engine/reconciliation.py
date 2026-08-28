"""
Broker reconciliation (CP14 / automation-platform-spec 08-JOBS-POSTMARKET.md
M01): "The most important post-market job. Divergence between our state and
the broker's is the root cause of most serious incidents."

Scope note: the full spec reconciles orders, fills, positions, AND funds
(broker P&L vs computed P&L). This implementation covers POSITIONS -- the
check the spec itself calls the sharpest ("must be FLAT at EOD for
intraday strategies; any open position -> P0"), and the one X02 (square-off,
xillion/engine/square_off.py) is specifically meant to have already
resolved, so M01 here is the independent verification that X02 actually
worked -- plus, as of 2026-08-29, ORDERS: today's OrderRecord rows compared
against broker.get_orders_today() by broker_order_id, catching a status/
fill-quantity/fill-price mismatch (we think PENDING, broker says FILLED;
or the reverse) as well as an order either side doesn't know about.

Still honestly NOT done: fine-grained per-FILL reconciliation (multiple
partial fills making up one order aren't compared individually -- only the
order's own aggregate filled_quantity/avg_fill_price are, since neither the
Broker ABC nor FillRecord's own writer (ExecutionRouter._persist_order)
tracks partial fills as separate rows today; see execution.py, which only
writes a FillRecord when an order reaches FILLED).

Funds reconciliation (broker P&L vs computed P&L) closed 2026-08-29 --
see _reconcile_funds below. It needed a "today's realised P&L" broker
capability the Broker ABC didn't expose (get_margins() is account
balances, not P&L; get_positions() only covers currently-open positions,
so a position closed earlier today would already be missing from it) --
Broker.get_realised_pnl_today() / BrokerCapabilities.
supports_realised_pnl_query now exist, implemented for both Zerodha (Kite's
"day" positions array) and Dhan (summing realizedProfit across every
returned position, closed ones included).
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select

from xillion.core.broker_base import Broker
from xillion.db.models import (
    BrokerConnection,
    DailyStrategyPnl,
    OrderRecord,
    PositionRecord,
    StrategyInstance,
)
from xillion.db.models import ReconciliationReport as ReconciliationReportRecord

logger = structlog.get_logger(__name__)


@dataclass
class PositionMismatch:
    symbol: str
    issue: str  # "broker_only" | "internal_only" | "quantity_mismatch"
    broker_qty: int | None = None
    internal_qty: int | None = None


@dataclass
class OrderMismatch:
    broker_order_id: str
    symbol: str
    issue: str  # "broker_only" | "internal_only" | "status_mismatch" | "fill_mismatch"
    broker_status: str | None = None
    internal_status: str | None = None
    broker_filled_qty: int | None = None
    internal_filled_qty: int | None = None
    broker_avg_price: str | None = None
    internal_avg_price: str | None = None


@dataclass
class FundsMismatch:
    broker_realised_pnl: str
    internal_realised_pnl: str
    diff: str


@dataclass
class ReconciliationResult:
    status: str  # CLEAN | DISCREPANCY | FAILED
    trading_date: date
    checked_at: datetime
    position_mismatches: list[PositionMismatch] = field(default_factory=list)
    eod_open_positions: list[str] = field(default_factory=list)
    order_mismatches: list[OrderMismatch] = field(default_factory=list)
    funds_mismatch: FundsMismatch | None = None
    notes: list[str] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(UTC)


async def run_reconciliation(
    broker: Broker,
    broker_name: str,
    db_factory,
    notify: Callable[[str, str, str], Awaitable[None]] | None = None,
) -> ReconciliationResult:
    """Compares the broker's live positions against xillion's own
    PositionRecord table for any strategy still showing a nonzero
    quantity. Persists the result and alerts on anything but CLEAN.
    Never raises -- a broker fetch failure is a FAILED report, not an
    exception, since this job has to produce a record either way."""
    trading_date = _now().date()

    try:
        broker_positions = await broker.get_positions()
    except Exception as exc:
        logger.critical("M01: broker position fetch failed", error=str(exc))
        result = ReconciliationResult(
            status="FAILED",
            trading_date=trading_date,
            checked_at=_now(),
            notes=[f"broker fetch failed: {exc}"],
        )
        await _persist(db_factory, broker_name, result)
        await _alert(
            notify, "M01 RECONCILIATION FAILED", f"Could not reach broker: {exc}", "critical"
        )
        return result

    broker_by_symbol = {p.symbol: p.quantity for p in broker_positions if p.quantity != 0}

    async with db_factory()() as session:
        db_result = await session.execute(
            select(PositionRecord).where(PositionRecord.quantity != 0)
        )
        internal_by_symbol = {r.symbol: r.quantity for r in db_result.scalars().all()}

    all_symbols = set(broker_by_symbol) | set(internal_by_symbol)
    mismatches: list[PositionMismatch] = []
    for symbol in sorted(all_symbols):
        b_qty = broker_by_symbol.get(symbol)
        i_qty = internal_by_symbol.get(symbol)
        if b_qty is not None and i_qty is None:
            mismatches.append(PositionMismatch(symbol, "broker_only", broker_qty=b_qty))
        elif i_qty is not None and b_qty is None:
            mismatches.append(PositionMismatch(symbol, "internal_only", internal_qty=i_qty))
        elif b_qty != i_qty:
            mismatches.append(
                PositionMismatch(symbol, "quantity_mismatch", broker_qty=b_qty, internal_qty=i_qty)
            )

    # EOD rule: for intraday strategies, ANY open position -- broker or
    # internal, matched or not -- is itself a discrepancy. This is the
    # independent check that X02 actually flattened everything.
    eod_open = sorted(all_symbols)

    order_mismatches, order_notes, orders_fetch_failed = await _reconcile_orders(
        broker, broker_name, db_factory
    )
    funds_mismatch, funds_notes, funds_fetch_failed = await _reconcile_funds(
        broker, broker_name, db_factory
    )

    status = (
        "CLEAN"
        if not mismatches
        and not eod_open
        and not order_mismatches
        and not orders_fetch_failed
        and funds_mismatch is None
        and not funds_fetch_failed
        else "DISCREPANCY"
    )
    result = ReconciliationResult(
        status=status,
        trading_date=trading_date,
        checked_at=_now(),
        position_mismatches=mismatches,
        eod_open_positions=eod_open,
        order_mismatches=order_mismatches,
        funds_mismatch=funds_mismatch,
        notes=order_notes + funds_notes,
    )

    await _persist(db_factory, broker_name, result)

    if status != "CLEAN":
        funds_detail = f", funds mismatch: {funds_mismatch.diff}" if funds_mismatch else ""
        detail = (
            f"{len(mismatches)} position mismatch(es), {len(eod_open)} position(s) open at EOD, "
            f"{len(order_mismatches)} order mismatch(es){funds_detail}: {eod_open}"
        )
        logger.critical("M01: reconciliation DISCREPANCY", detail=detail)
        await _alert(notify, "M01 RECONCILIATION: DISCREPANCY", detail, "critical")
    else:
        logger.info("M01: reconciliation clean")

    return result


_FILL_PRICE_TOLERANCE = 0.01


async def _reconcile_orders(
    broker: Broker, broker_name: str, db_factory
) -> tuple[list[OrderMismatch], list[str], bool]:
    """Today's OrderRecord rows (this broker connection only) vs.
    broker.get_orders_today(), matched by broker_order_id -- the one id
    both sides agree on unambiguously (client_order_id/tag round-tripping
    through a broker's own order list isn't reliable across adapters, see
    e.g. brokers/zerodha.py's _kite_to_order falling back to the order tag).

    Returns (mismatches, notes, fetch_failed). fetch_failed forces the
    overall run to DISCREPANCY -- same "uncertainty isn't safe" stance
    position reconciliation already takes on a broker.get_positions()
    failure (which short-circuits the whole run before this is even
    called). A missing BrokerConnection row is different: that's a clean
    skip (test doubles, a broker never registered through the normal
    connect flow), not evidence of anything wrong, so it does NOT force
    non-CLEAN."""
    trading_date_str = _now().date().isoformat()

    try:
        broker_orders = await broker.get_orders_today()
    except Exception as exc:
        logger.error("M01: broker order fetch failed", error=str(exc))
        return [], [f"order fetch failed: {exc}"], True

    async with db_factory()() as session:
        conn_result = await session.execute(
            select(BrokerConnection).where(BrokerConnection.name == broker_name)
        )
        connection = conn_result.scalars().first()
        if connection is None:
            # No matching BrokerConnection row (e.g. a test double, or a
            # broker never registered through the normal connect flow) --
            # nothing to compare internal orders against. Not an error;
            # position reconciliation above still ran.
            return (
                [],
                [f"no BrokerConnection row named {broker_name!r} -- order check skipped"],
                False,
            )

        internal_result = await session.execute(
            select(OrderRecord).where(
                OrderRecord.broker_connection_id == connection.id,
                OrderRecord.broker_order_id.is_not(None),
                OrderRecord.submitted_at.like(f"{trading_date_str}%"),
            )
        )
        internal_orders = internal_result.scalars().all()

    broker_by_id = {o.broker_order_id: o for o in broker_orders if o.broker_order_id}
    internal_by_id = {r.broker_order_id: r for r in internal_orders if r.broker_order_id}

    mismatches: list[OrderMismatch] = []
    for order_id in sorted(set(broker_by_id) | set(internal_by_id)):
        b = broker_by_id.get(order_id)
        i = internal_by_id.get(order_id)
        if b is not None and i is None:
            mismatches.append(
                OrderMismatch(order_id, b.symbol, "broker_only", broker_status=b.status.value)
            )
        elif i is not None and b is None:
            mismatches.append(
                OrderMismatch(order_id, i.symbol, "internal_only", internal_status=i.status)
            )
        elif b is not None and i is not None:
            if b.status.value != i.status:
                mismatches.append(
                    OrderMismatch(
                        order_id,
                        b.symbol,
                        "status_mismatch",
                        broker_status=b.status.value,
                        internal_status=i.status,
                    )
                )
            elif b.filled_quantity != i.filled_quantity or (
                b.avg_fill_price is not None
                and i.avg_fill_price is not None
                # i.avg_fill_price comes back as Decimal at runtime despite
                # the model's `float | None` hint (SQLAlchemy's Numeric
                # type doesn't coerce) -- float() both sides explicitly
                # rather than relying on the hint.
                and abs(float(b.avg_fill_price) - float(i.avg_fill_price)) > _FILL_PRICE_TOLERANCE
            ):
                mismatches.append(
                    OrderMismatch(
                        order_id,
                        b.symbol,
                        "fill_mismatch",
                        broker_filled_qty=b.filled_quantity,
                        internal_filled_qty=i.filled_quantity,
                        broker_avg_price=str(b.avg_fill_price) if b.avg_fill_price else None,
                        internal_avg_price=(
                            str(i.avg_fill_price) if i.avg_fill_price is not None else None
                        ),
                    )
                )

    return mismatches, [], False


_FUNDS_TOLERANCE = Decimal("1.00")  # absorbs paisa-level rounding noise, not a real discrepancy


async def _reconcile_funds(
    broker: Broker, broker_name: str, db_factory
) -> tuple[FundsMismatch | None, list[str], bool]:
    """Broker-reported today's realised P&L (Broker.get_realised_pnl_today())
    vs. xillion's own internally computed figure -- DailyStrategyPnl,
    populated from actual fill prices when a position closes
    (strategy_engine.py's persist_trade_close), genuinely independent of
    what the broker reports, not a comparison against itself. Scoped per
    broker connection via StrategyInstance.broker_connection_id, the same
    join every other check in this module already uses.

    Returns (mismatch, notes, fetch_failed). A broker without
    supports_realised_pnl_query is a clean skip, same stance as a missing
    BrokerConnection row below -- a capability that was never promised
    isn't evidence of anything wrong. A fetch failure forces DISCREPANCY,
    same "uncertainty isn't safe" stance _reconcile_orders takes."""
    if not broker.capabilities.supports_realised_pnl_query:
        return None, [f"{broker_name}: funds check skipped -- broker doesn't support it"], False

    trading_date_str = _now().date().isoformat()

    try:
        broker_pnl = await broker.get_realised_pnl_today()
    except Exception as exc:
        logger.error("M01: broker realised P&L fetch failed", error=str(exc))
        return None, [f"funds fetch failed: {exc}"], True

    async with db_factory()() as session:
        conn_result = await session.execute(
            select(BrokerConnection).where(BrokerConnection.name == broker_name)
        )
        connection = conn_result.scalars().first()
        if connection is None:
            return (
                None,
                [f"no BrokerConnection row named {broker_name!r} -- funds check skipped"],
                False,
            )

        pnl_result = await session.execute(
            select(DailyStrategyPnl.realised_pnl)
            .join(StrategyInstance, StrategyInstance.id == DailyStrategyPnl.strategy_instance_id)
            .where(
                StrategyInstance.broker_connection_id == connection.id,
                DailyStrategyPnl.trading_date == trading_date_str,
            )
        )
        internal_pnl = sum((Decimal(str(v)) for v in pnl_result.scalars().all()), Decimal("0"))

    diff = broker_pnl - internal_pnl
    if abs(diff) <= _FUNDS_TOLERANCE:
        return None, [], False

    return (
        FundsMismatch(
            broker_realised_pnl=str(broker_pnl),
            internal_realised_pnl=str(internal_pnl),
            diff=str(diff),
        ),
        [],
        False,
    )


async def _persist(db_factory, broker_name: str, result: ReconciliationResult) -> None:
    try:
        async with db_factory()() as session:
            session.add(
                ReconciliationReportRecord(
                    trading_date=result.trading_date.isoformat(),
                    broker_name=broker_name,
                    checked_at=result.checked_at.isoformat(),
                    status=result.status,
                    position_mismatches_json=json.dumps(
                        [
                            {
                                "symbol": m.symbol,
                                "issue": m.issue,
                                "broker_qty": m.broker_qty,
                                "internal_qty": m.internal_qty,
                            }
                            for m in result.position_mismatches
                        ]
                    ),
                    eod_open_positions_json=json.dumps(result.eod_open_positions),
                    order_mismatches_json=json.dumps(
                        [
                            {
                                "broker_order_id": m.broker_order_id,
                                "symbol": m.symbol,
                                "issue": m.issue,
                                "broker_status": m.broker_status,
                                "internal_status": m.internal_status,
                                "broker_filled_qty": m.broker_filled_qty,
                                "internal_filled_qty": m.internal_filled_qty,
                                "broker_avg_price": m.broker_avg_price,
                                "internal_avg_price": m.internal_avg_price,
                            }
                            for m in result.order_mismatches
                        ]
                    ),
                    funds_mismatch_json=(
                        json.dumps(
                            {
                                "broker_realised_pnl": result.funds_mismatch.broker_realised_pnl,
                                "internal_realised_pnl": result.funds_mismatch.internal_realised_pnl,
                                "diff": result.funds_mismatch.diff,
                            }
                        )
                        if result.funds_mismatch is not None
                        else None
                    ),
                    notes_json=json.dumps(result.notes),
                )
            )
            await session.commit()
    except Exception as exc:
        logger.error("M01: failed to persist reconciliation report", error=str(exc))


async def unresolved_blocker_exists(db_factory) -> bool:
    """True if the most recent trading day that has any reconciliation
    report includes a non-CLEAN, not-yet-acknowledged one. Used at process
    startup (main.py) so a restart can't silently clear an unresolved M01
    DISCREPANCY -- the in-memory RiskManager.pause_trading() from
    eod_scheduler.py doesn't survive a restart on its own, but the DB
    record does, and the gate must survive until someone actually signs
    off (xillion/api/reconciliation.py)."""
    async with db_factory()() as session:
        latest_date_result = await session.execute(
            select(ReconciliationReportRecord.trading_date)
            .order_by(ReconciliationReportRecord.trading_date.desc())
            .limit(1)
        )
        latest_date = latest_date_result.scalar_one_or_none()
        if latest_date is None:
            return False
        reports_result = await session.execute(
            select(ReconciliationReportRecord).where(
                ReconciliationReportRecord.trading_date == latest_date
            )
        )
        reports = reports_result.scalars().all()
        return any(r.status != "CLEAN" and not r.acknowledged for r in reports)


async def _alert(notify, title: str, body: str, severity: str) -> None:
    if notify is None:
        return
    try:
        await notify(title, body, severity)
    except Exception as exc:
        logger.error("M01: alert failed", error=str(exc))

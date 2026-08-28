"""
Broker failover (automation-platform-spec 13-IMPLEMENTATION-ROADMAP.md
"Broker failover: Dhan <-> Zerodha"; 15-RUNBOOK-AND-OBSERVABILITY.md's
"Broker API down mid-session" runbook: "If failover configured -> switch
to secondary broker for exits only").

EXIT ONLY, deliberately: opening new risk through an unfamiliar broker path
mid-outage is a materially different (and much worse) risk than closing
what's already open, so this never places new entries -- only flattens.

The down broker is, by definition, unreachable -- run_square_off's own
"query the broker directly" approach (xillion/engine/square_off.py) can't
work here, since the broker being down is the whole premise. This instead
trusts xillion's own PositionRecord as the source of truth for what's
open (scoped to strategy instances configured on the down connection) and
places closing orders through the FAILOVER broker instead -- the same
canonical NSE tradingsymbol both brokers.zerodha and brokers.dhan accept
as OrderRequest.symbol, resolved to each broker's own internal id
(tradingsymbol / securityId) inside that broker's own place_order.

Does not touch PositionRecord itself afterward, same as X02 -- M01's next
run reconciles internal state against whichever broker is actually
holding a position by then, rather than this function guessing at it.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select

from xillion.core.broker_base import Broker
from xillion.core.events import OrderRequest, OrderType, Side
from xillion.db.models import PositionRecord, StrategyInstance

logger = structlog.get_logger(__name__)

FAILOVER_EXIT_TAG = "BROKER_FAILOVER_EXIT"


@dataclass
class FailoverExitReport:
    status: str  # CLEAN | FLATTENED | FAILED
    positions_found: list[tuple[str, str, int]] = field(
        default_factory=list
    )  # (strategy_instance_id, symbol, quantity)
    exited: list[str] = field(default_factory=list)  # symbols successfully closed
    failed_to_exit: list[str] = field(default_factory=list)


def _closing_side(quantity: int) -> Side:
    return Side.SELL if quantity > 0 else Side.BUY


async def run_failover_exit(
    down_connection_id: int,
    down_connection_name: str,
    failover_broker: Broker,
    failover_broker_name: str,
    db_factory,
    notify: Callable[[str, str, str], Awaitable[None]] | None = None,
) -> FailoverExitReport:
    """Exit every open position belonging to a strategy instance configured
    on `down_connection_id`, via `failover_broker`. Never raises -- a
    per-position failure is reported and alerted, not thrown, matching
    X02/M01's own "must produce a result either way" stance."""
    async with db_factory()() as session:
        instance_ids_result = await session.execute(
            select(StrategyInstance.id).where(
                StrategyInstance.broker_connection_id == down_connection_id
            )
        )
        instance_ids = [row[0] for row in instance_ids_result.all()]

        if not instance_ids:
            logger.info(
                "failover: no strategy instances configured on down connection",
                connection=down_connection_name,
            )
            return FailoverExitReport(status="CLEAN")

        positions_result = await session.execute(
            select(PositionRecord).where(
                PositionRecord.strategy_instance_id.in_(instance_ids),
                PositionRecord.quantity != 0,
            )
        )
        open_positions = positions_result.scalars().all()

    if not open_positions:
        logger.info(
            "failover: no open positions on the down connection", connection=down_connection_name
        )
        return FailoverExitReport(status="CLEAN")

    logger.critical(
        "failover: exiting open positions via secondary broker",
        down=down_connection_name,
        via=failover_broker_name,
        count=len(open_positions),
    )
    await _alert(
        notify,
        "BROKER FAILOVER TRIGGERED",
        f"{down_connection_name} is unreachable. Exiting {len(open_positions)} open "
        f"position(s) via {failover_broker_name}: "
        f"{[p.symbol for p in open_positions]}",
        "critical",
    )

    positions_found = [(p.strategy_instance_id, p.symbol, p.quantity) for p in open_positions]
    exited: list[str] = []
    failed_to_exit: list[str] = []

    for pos in open_positions:
        try:
            await failover_broker.place_order(
                OrderRequest(
                    symbol=pos.symbol,
                    side=_closing_side(pos.quantity),
                    quantity=abs(pos.quantity),
                    order_type=OrderType.MARKET,
                    strategy_instance_id=pos.strategy_instance_id,
                    tag=FAILOVER_EXIT_TAG,
                )
            )
            exited.append(pos.symbol)
        except Exception as exc:
            logger.error(
                "failover: failed to place exit order",
                symbol=pos.symbol,
                via=failover_broker_name,
                error=str(exc),
            )
            failed_to_exit.append(pos.symbol)

    if failed_to_exit:
        await _alert(
            notify,
            "BROKER FAILOVER INCOMPLETE",
            f"Could not exit via {failover_broker_name}: {failed_to_exit}. "
            "Manual intervention required -- check both brokers' apps directly.",
            "critical",
        )
        return FailoverExitReport(
            status="FAILED",
            positions_found=positions_found,
            exited=exited,
            failed_to_exit=failed_to_exit,
        )

    logger.info("failover: all positions exited via secondary broker", exited=exited)
    await _alert(
        notify,
        "Broker failover exit complete",
        f"Exited via {failover_broker_name}: {', '.join(exited)}. "
        f"{down_connection_name} remains down -- new entries stay blocked until it recovers.",
        "warning",
    )
    return FailoverExitReport(status="FLATTENED", positions_found=positions_found, exited=exited)


async def _alert(notify, title: str, body: str, severity: str) -> None:
    if notify is None:
        return
    try:
        await notify(title, body, severity)
    except Exception as exc:
        logger.error("failover: alert failed", error=str(exc))

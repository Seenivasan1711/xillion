"""
Square-off enforcer (CP14 / automation-platform-spec 08-JOBS-POSTMARKET.md
X02): "The single most important scheduled job in the system. It must
never fail." "This job is independent of every other job. It does not
check whether strategies are armed, whether the risk engine is happy, or
whether the monitor loop is running. It queries the broker for open
positions and closes them. It must work when everything else is broken."

Deliberately NOT driven through StrategyContext/StrategyEngine -- a
strategy instance that crashed, was never started this session, or whose
process died mid-position must not be a precondition for flattening a real
open position. run_square_off() takes only a Broker, nothing else, and
queries it directly.

Scope note: the spec's full ladder (15:15 warning -> 15:18 soft LIMIT ->
15:22 aggressive LIMIT -> 15:25 MARKET -> 15:28 verify) is a 13-minute
price-improvement schedule. This implementation goes straight to MARKET and
verifies immediately -- strictly SAFER (flattens sooner) even though it
isn't price-optimal. The staged ladder is a natural refinement once there's
a scheduler granular enough to run sub-steps a few minutes apart; the
non-negotiable safety property (nothing open past close) is what's built
here.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Awaitable, Callable, Optional

import structlog

from xillion.core.broker_base import Broker
from xillion.core.events import OrderRequest, OrderType, Position, Side

logger = structlog.get_logger(__name__)

SQUARE_OFF_TAG = "X02_SQUARE_OFF"


@dataclass
class SquareOffReport:
    status: str  # CLEAN | FLATTENED | FAILED
    positions_found: list[Position] = field(default_factory=list)
    flattened: list[str] = field(default_factory=list)      # symbols successfully closed
    failed_to_close: list[str] = field(default_factory=list)  # symbols an order couldn't be placed for
    still_open_after_verify: list[str] = field(default_factory=list)  # symbols STILL open on re-query
    error: Optional[str] = None


def _closing_side(quantity: int) -> Side:
    return Side.SELL if quantity > 0 else Side.BUY


async def run_square_off(
    broker: Broker,
    notify: Optional[Callable[[str, str, str], Awaitable[None]]] = None,
) -> SquareOffReport:
    """Query the broker directly, flatten anything open at MARKET, verify.
    `notify` matches TelegramNotifier.alert's shape: async fn(title, body,
    severity). Never raises -- a broker fetch failure or a leg that can't
    be closed is reported in the result and alerted, not thrown, since this
    job must complete and produce a report even when things go wrong."""
    try:
        positions = await broker.get_positions()
    except Exception as exc:
        logger.critical("X02: broker position fetch failed -- cannot verify flat", error=str(exc))
        await _alert(notify, "X02 SQUARE-OFF FAILED", f"Could not reach broker to check positions: {exc}", "critical")
        return SquareOffReport(status="FAILED", error=str(exc))

    open_positions = [p for p in positions if p.quantity != 0]
    if not open_positions:
        logger.info("X02: square-off check found nothing open")
        return SquareOffReport(status="CLEAN", positions_found=[])

    logger.warning("X02: open positions found at square-off time", count=len(open_positions))
    flattened: list[str] = []
    failed_to_close: list[str] = []

    for pos in open_positions:
        try:
            await broker.place_order(OrderRequest(
                symbol=pos.symbol, side=_closing_side(pos.quantity), quantity=abs(pos.quantity),
                order_type=OrderType.MARKET, tag=SQUARE_OFF_TAG,
            ))
            flattened.append(pos.symbol)
        except Exception as exc:
            logger.error("X02: failed to place square-off order", symbol=pos.symbol, error=str(exc))
            failed_to_close.append(pos.symbol)

    # VERIFY -- never trust that the close orders actually landed; query again.
    still_open: list[str] = []
    try:
        after = await broker.get_positions()
        still_open = [p.symbol for p in after if p.quantity != 0]
    except Exception as exc:
        logger.critical("X02: post-flatten verification fetch failed", error=str(exc))
        await _alert(
            notify, "X02 VERIFICATION FAILED",
            f"Square-off orders were placed but the broker could not be re-queried to confirm: {exc}",
            "critical",
        )
        return SquareOffReport(
            status="FAILED", positions_found=open_positions, flattened=flattened,
            failed_to_close=failed_to_close, error=f"verify fetch failed: {exc}",
        )

    if still_open or failed_to_close:
        await _alert(
            notify, "X02 SQUARE-OFF INCOMPLETE",
            f"Still open after square-off: {still_open or 'none'}. "
            f"Orders that failed to place: {failed_to_close or 'none'}. Manual intervention required.",
            "critical",
        )
        return SquareOffReport(
            status="FAILED", positions_found=open_positions, flattened=flattened,
            failed_to_close=failed_to_close, still_open_after_verify=still_open,
        )

    logger.info("X02: square-off complete, verified flat", flattened=flattened)
    await _alert(notify, "X02 square-off complete", f"Flattened at close: {', '.join(flattened)}", "warning")
    return SquareOffReport(status="FLATTENED", positions_found=open_positions, flattened=flattened)


async def _alert(notify, title: str, body: str, severity: str) -> None:
    if notify is None:
        return
    try:
        await notify(title, body, severity)
    except Exception as exc:
        logger.error("X02: alert failed", error=str(exc))

"""
Risk management API: kill switch (with TOTP gate), risk status.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.auth.totp import decrypt_secret, verify_code
from xillion.db.models import AppUser

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/risk", tags=["risk"])


class KillSwitchRequest(BaseModel):
    totp_code: str | None = None
    exit_positions: bool = False


@router.get("/status")
async def risk_status(
    request: Request,
    user: AppUser = Depends(get_current_user),
):
    risk = getattr(request.app.state, "risk", None)
    if risk is None:
        return {"kill_switch_active": False, "status": "unavailable"}
    return risk.status()


def verify_totp_or_raise(user: AppUser, totp_code: str | None) -> None:
    """Shared TOTP gate -- raises HTTPException on failure. Used by the
    kill-switch route below and by the Telegram `/killswitch` command
    (xillion/notifications/telegram_commands.py, 2026-09-22): that gate is
    never bypassed regardless of which surface the request comes from."""
    if user.totp_secret:
        if not totp_code:
            raise HTTPException(400, "TOTP code required to activate kill switch")
        secret = decrypt_secret(user.totp_secret)
        if not verify_code(secret, totp_code):
            raise HTTPException(401, "Invalid TOTP code")


@router.post("/kill-switch/activate")
async def activate_kill_switch(
    body: KillSwitchRequest,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    verify_totp_or_raise(user, body.totp_code)
    return await activate_kill_switch_core(request.app, actor=user.username)


async def activate_kill_switch_core(app, actor: str) -> dict:
    """Core kill-switch logic -- stop every running strategy, cancel every
    open order, flip the risk manager's flag, broadcast + notify. Assumes
    the caller has ALREADY verified TOTP (verify_totp_or_raise above) --
    this function itself does no auth, so never expose it directly without
    that gate in front of it."""
    risk = getattr(app.state, "risk", None)
    if risk is None:
        raise HTTPException(503, "Risk manager not available")

    engine = getattr(app.state, "strategy_engine", None)

    # Stop all running strategies
    stopped = []
    if engine:
        for runner in list(engine.list_runners()):
            try:
                await engine.stop_instance(runner._instance_id, reason="kill_switch")
                stopped.append(runner._instance_id)
            except Exception as exc:
                logger.error("kill switch: failed to stop runner", error=str(exc))

    # Cancel all open orders if Zerodha is connected
    cancelled_orders = 0
    broker_instances = getattr(app.state, "broker_instances", {})
    for info in broker_instances.values():
        broker = info.get("instance")
        if broker and info.get("status") == "connected":
            try:
                orders = await broker.get_orders_today()
                from xillion.core.events import OrderStatus

                open_orders = [
                    o
                    for o in orders
                    if o.status
                    in (
                        OrderStatus.PENDING,
                        OrderStatus.SUBMITTED,
                        OrderStatus.ACCEPTED,
                        OrderStatus.PARTIAL,
                    )
                ]
                for order in open_orders:
                    if order.broker_order_id:
                        await broker.cancel_order(order.broker_order_id)
                        cancelled_orders += 1
            except Exception as exc:
                logger.error("kill switch: order cancellation failed", error=str(exc))

    risk.activate_kill_switch()

    # Broadcast kill switch event to all WS clients
    from xillion.api.ws import broadcast

    await broadcast({"type": "kill_switch", "active": True})

    # Notify via Telegram
    notifier = getattr(app.state, "telegram", None)
    if notifier:
        await notifier.alert(
            "Kill Switch Fired",
            f"Stopped {len(stopped)} strategies, cancelled {cancelled_orders} orders.",
            "critical",
        )

    logger.critical("kill switch activated", actor=actor)

    from xillion.notifications.notion_log import log_action

    await log_action(
        "Kill switch activated",
        {"actor": actor, "strategies_stopped": stopped, "orders_cancelled": cancelled_orders},
    )

    return {
        "activated": True,
        "strategies_stopped": len(stopped),
        "orders_cancelled": cancelled_orders,
    }


@router.post("/kill-switch/reset")
async def reset_kill_switch(
    body: KillSwitchRequest,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    if user.totp_secret:
        if not body.totp_code:
            raise HTTPException(400, "TOTP code required to reset kill switch")
        secret = decrypt_secret(user.totp_secret)
        if not verify_code(secret, body.totp_code):
            raise HTTPException(401, "Invalid TOTP code")

    risk = getattr(request.app.state, "risk", None)
    if risk is None:
        raise HTTPException(503, "Risk manager not available")

    risk.reset_kill_switch()
    from xillion.api.ws import broadcast

    await broadcast({"type": "kill_switch", "active": False})
    logger.info("kill switch reset via API", user=user.username)
    return {"reset": True}

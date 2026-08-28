"""
Broker plugin API endpoints: discovered classes and live connection management.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.db.models import AppUser, BrokerConnection

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/brokers", tags=["brokers"])


@router.get("/classes")
async def list_broker_classes(request: Request):
    """List all discovered broker plugin classes."""
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        return {"brokers": [], "errors": {}}
    registry = loader.registry
    brokers = []
    for _name, cls in registry.brokers.items():
        caps = getattr(cls, "capabilities", None)
        brokers.append(
            {
                "name": cls.name,
                "version": cls.version,
                "capabilities": {
                    "supports_websocket": getattr(caps, "supports_websocket", True),
                    "supports_historical": getattr(caps, "supports_historical", True),
                    "supports_bracket_orders": getattr(caps, "supports_bracket_orders", False),
                    "supports_gtt_orders": getattr(caps, "supports_gtt_orders", False),
                    "supported_timeframes": getattr(caps, "supported_timeframes", []),
                    "supported_exchanges": getattr(caps, "supported_exchanges", []),
                },
            }
        )
    return {"brokers": brokers}


@router.get("/connections")
async def list_connections(request: Request, db: AsyncSession = Depends(db_dep)):
    """List all configured broker connections with live status, plus
    (2026-08-29) failover config and health -- see xillion/engine/
    broker_health.py / broker_failover.py."""
    instances = getattr(request.app.state, "broker_instances", {})
    health = getattr(request.app.state, "broker_health", {})

    db_result = await db.execute(select(BrokerConnection))
    db_conns = {c.name: c for c in db_result.scalars().all()}
    id_to_name = {c.id: c.name for c in db_conns.values()}

    connections = []
    for info in instances.values():
        name = info["name"]
        db_conn = db_conns.get(name)
        h = health.get(name)
        failover_target = None
        if db_conn is not None and db_conn.failover_connection_id is not None:
            failover_target = id_to_name.get(db_conn.failover_connection_id)
        connections.append(
            {
                "name": name,
                "broker_name": info["broker_name"],
                "status": info["status"],
                "last_error": info.get("last_error"),
                "connected_at": info.get("connected_at"),
                "failover_connection_name": failover_target,
                "health": (
                    {
                        "consecutive_failures": h.consecutive_failures,
                        "last_checked_at": h.last_checked_at,
                        "last_healthy_at": h.last_healthy_at,
                        "failover_triggered": h.failover_triggered,
                    }
                    if h is not None
                    else None
                ),
            }
        )
    return {"connections": connections}


class SetFailoverTargetRequest(BaseModel):
    target_name: str | None = None  # None clears it


@router.patch("/connections/{name}/failover-target")
async def set_failover_target(
    name: str,
    body: SetFailoverTargetRequest,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    """Configure (or clear) which connection this one fails over to for
    EXIT-ONLY order placement if it goes unhealthy (automation-platform-
    spec's "switch to secondary broker for exits only"). Nothing fails
    over automatically until this is set -- see broker_health.py."""
    result = await db.execute(select(BrokerConnection).where(BrokerConnection.name == name))
    conn = result.scalars().first()
    if conn is None:
        raise HTTPException(404, f"Connection '{name}' not found")

    if body.target_name is None:
        conn.failover_connection_id = None
        await db.commit()
        logger.info("failover target cleared", connection=name, user=user.username)
        return {"name": name, "failover_connection_name": None}

    if body.target_name == name:
        raise HTTPException(400, "A connection cannot fail over to itself")

    target_result = await db.execute(
        select(BrokerConnection).where(BrokerConnection.name == body.target_name)
    )
    target = target_result.scalars().first()
    if target is None:
        raise HTTPException(404, f"Target connection '{body.target_name}' not found")

    conn.failover_connection_id = target.id
    await db.commit()
    logger.info("failover target set", connection=name, target=body.target_name, user=user.username)
    return {"name": name, "failover_connection_name": body.target_name}


@router.post("/connections/{name}/failover")
async def trigger_failover(
    name: str,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    """Manually trigger the exit-only failover right now, regardless of
    the health-monitoring loop's own state -- the runbook's own documented
    operator action ("switch to secondary broker for exits only"), not
    only an automatic response to a sustained outage."""
    from xillion.db.session import get_session_factory
    from xillion.engine.broker_failover import run_failover_exit

    result = await db.execute(select(BrokerConnection).where(BrokerConnection.name == name))
    down_conn = result.scalars().first()
    if down_conn is None:
        raise HTTPException(404, f"Connection '{name}' not found")
    if down_conn.failover_connection_id is None:
        raise HTTPException(400, f"'{name}' has no failover target configured")

    target_result = await db.execute(
        select(BrokerConnection).where(BrokerConnection.id == down_conn.failover_connection_id)
    )
    target_conn = target_result.scalars().first()
    if target_conn is None:
        raise HTTPException(409, "Configured failover target connection no longer exists")

    broker_instances = getattr(request.app.state, "broker_instances", {})
    target_info = broker_instances.get(target_conn.name)
    target_broker = target_info.get("instance") if isinstance(target_info, dict) else None
    target_status = target_info.get("status") if isinstance(target_info, dict) else None
    if target_broker is None or target_status != "connected":
        raise HTTPException(409, f"Failover target '{target_conn.name}' is not connected")

    notifier = getattr(request.app.state, "telegram", None)
    logger.critical("manual broker failover triggered via API", connection=name, user=user.username)
    report = await run_failover_exit(
        down_connection_id=down_conn.id,
        down_connection_name=name,
        failover_broker=target_broker,
        failover_broker_name=target_conn.name,
        db_factory=get_session_factory,
        notify=notifier.alert if notifier else None,
    )
    return {
        "status": report.status,
        "positions_found": len(report.positions_found),
        "exited": report.exited,
        "failed_to_exit": report.failed_to_exit,
    }


_RECONNECT_HANDLERS = {
    "Zerodha Primary": "_try_connect_zerodha",
    "Dhan Primary": "_try_connect_dhan",
}


@router.post("/connections/{name}/reconnect")
async def reconnect_broker(name: str, request: Request):
    """Trigger a reconnect for a specific broker connection. Used to be
    hardcoded to "Zerodha Primary" only -- Dhan's own Reconnect button in
    Settings > Active connections would 400. Dispatches by connection name
    the same way the connections themselves are keyed elsewhere
    (app.state.broker_instances), so a future broker just needs an entry
    here rather than a new branch."""
    instances = getattr(request.app.state, "broker_instances", {})
    if name not in instances:
        raise HTTPException(status_code=404, detail=f"Connection '{name}' not found")

    handler_name = _RECONNECT_HANDLERS.get(name)
    if handler_name is None:
        raise HTTPException(status_code=400, detail="Reconnect not implemented for this broker")

    import xillion.main as main_module

    await getattr(main_module, handler_name)(request.app)
    info = request.app.state.broker_instances.get(name, {})
    return {"name": name, "status": info.get("status", "unknown")}


@router.get("/connections/{name}/status")
async def connection_status(name: str, request: Request):
    instances = getattr(request.app.state, "broker_instances", {})
    info = instances.get(name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Connection '{name}' not found")

    broker = info.get("instance")
    live_status = None
    if broker:
        try:
            healthy = await broker.healthcheck()
            live_status = "connected" if healthy else "degraded"
        except Exception as exc:
            live_status = f"error: {exc}"

    return {
        "name": info["name"],
        "broker_name": info["broker_name"],
        "status": live_status or info["status"],
        "last_error": info.get("last_error"),
        "connected_at": info.get("connected_at"),
    }


@router.post("/refresh-instruments")
async def refresh_instruments(request: Request):
    """Manually refresh the shared `instrument` table (options strike
    resolution) from whichever broker is connected, instead of waiting for
    the 8:45 AM IST scheduled refresh. Useful right after connecting a new
    broker for the first time -- resolve_strike() reads this table, so an
    instance can be "running" with zero trades simply because nothing has
    populated it yet, not because anything is actually broken."""
    import xillion.main as main_module
    from xillion.core.instrument_cache import refresh_instrument_cache
    from xillion.db.session import get_session_factory

    broker, source = main_module._select_instrument_cache_broker(request.app)
    if broker is None:
        raise HTTPException(
            status_code=409, detail="No broker connected to refresh instruments from"
        )

    count = await refresh_instrument_cache(broker, get_session_factory)
    return {"source": source, "row_count": count}

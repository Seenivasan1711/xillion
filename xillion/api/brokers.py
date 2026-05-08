"""
Broker plugin API endpoints: discovered classes and live connection management.
"""
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/brokers", tags=["brokers"])


@router.get("/classes")
async def list_broker_classes(request: Request):
    """List all discovered broker plugin classes."""
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        return {"brokers": [], "errors": {}}
    registry = loader.registry
    brokers = []
    for name, cls in registry.brokers.items():
        caps = getattr(cls, "capabilities", None)
        brokers.append(
            {
                "name": cls.name,
                "version": cls.version,
                "capabilities": {
                    "supports_websocket": getattr(caps, "supports_websocket", True),
                    "supports_historical": getattr(caps, "supports_historical", True),
                    "supports_bracket_orders": getattr(caps, "supports_bracket_orders", False),
                    "supported_timeframes": getattr(caps, "supported_timeframes", []),
                    "supported_exchanges": getattr(caps, "supported_exchanges", []),
                },
            }
        )
    return {"brokers": brokers}


@router.get("/connections")
async def list_connections(request: Request):
    """List all configured broker connections with live status."""
    instances = getattr(request.app.state, "broker_instances", {})
    connections = [
        {
            "name": info["name"],
            "broker_name": info["broker_name"],
            "status": info["status"],
            "last_error": info.get("last_error"),
            "connected_at": info.get("connected_at"),
        }
        for info in instances.values()
    ]
    return {"connections": connections}


@router.post("/connections/{name}/reconnect")
async def reconnect_broker(name: str, request: Request):
    """Trigger a reconnect for a specific broker connection."""
    instances = getattr(request.app.state, "broker_instances", {})
    if name not in instances:
        raise HTTPException(status_code=404, detail=f"Connection '{name}' not found")

    if name == "Zerodha Primary":
        from xillion.main import _try_connect_zerodha
        await _try_connect_zerodha(request.app)
        info = request.app.state.broker_instances.get(name, {})
        return {"name": name, "status": info.get("status", "unknown")}

    raise HTTPException(status_code=400, detail="Reconnect not implemented for this broker")


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

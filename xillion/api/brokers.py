"""
Broker plugin API endpoints.
"""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/brokers", tags=["brokers"])


@router.get("/classes")
async def list_broker_classes(request: Request):
    """List all discovered broker classes."""
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
                    "supported_timeframes": getattr(caps, "supported_timeframes", []),
                    "supported_exchanges": getattr(caps, "supported_exchanges", []),
                },
            }
        )
    return {"brokers": brokers}

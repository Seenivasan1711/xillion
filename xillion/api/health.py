from datetime import datetime, timezone

from fastapi import APIRouter, Request

from xillion import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request):
    broker_instances = getattr(request.app.state, "broker_instances", {})
    brokers = [
        {
            "name": info["name"],
            "broker_name": info["broker_name"],
            "status": info["status"],
            "last_error": info.get("last_error"),
            "connected_at": info.get("connected_at"),
        }
        for info in broker_instances.values()
    ]
    all_connected = all(b["status"] == "connected" for b in brokers) if brokers else False
    return {
        "status": "ok",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "brokers": brokers,
        "broker_count": len(brokers),
        "brokers_connected": all_connected,
    }

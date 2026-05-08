"""
Strategy plugin and instance API endpoints.
"""
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("/classes")
async def list_strategy_classes(request: Request):
    """List all discovered strategy classes."""
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        return {"strategies": [], "errors": {}}
    registry = loader.registry
    strategies = []
    for name, cls in registry.strategies.items():
        strategies.append(
            {
                "name": cls.name,
                "version": cls.version,
                "description": cls.description,
                "author": cls.author,
                "timeframe": cls.timeframe,
                "instruments": cls.instruments,
                "params_schema": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "default": p.default,
                        "description": p.description,
                        "min": p.min,
                        "max": p.max,
                        "choices": p.choices,
                    }
                    for p in cls.params_schema
                ],
                "code_hash": registry.strategy_file_hashes.get(name, ""),
            }
        )
    return {"strategies": strategies, "errors": registry.errors}


@router.post("/reload")
async def reload_plugins(request: Request):
    """Trigger a full plugin rediscovery."""
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        raise HTTPException(status_code=503, detail="Plugin loader not available")
    registry = await loader.discover_all()
    engine = getattr(request.app.state, "strategy_engine", None)
    if engine:
        engine.set_registry(registry)
    return {
        "reloaded": True,
        "strategy_count": len(registry.strategies),
        "broker_count": len(registry.brokers),
        "errors": registry.errors,
    }


@router.get("/runners")
async def list_runners(request: Request):
    """List all currently running strategy instances."""
    engine = getattr(request.app.state, "strategy_engine", None)
    if engine is None:
        return {"runners": []}
    runners = []
    for runner in engine.list_runners():
        runners.append(
            {
                "instance_id": runner._instance_id,
                "status": runner.status,
                "last_error": runner.last_error,
            }
        )
    return {"runners": runners}

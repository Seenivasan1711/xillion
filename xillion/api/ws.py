"""
WebSocket endpoint for live UI updates: market data, order events, system logs.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])

_connections: list[WebSocket] = []


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _connections.append(websocket)
    try:
        # Send a welcome message
        await websocket.send_json(
            {
                "type": "connected",
                "ts": datetime.now(timezone.utc).isoformat(),
                "message": "Xillion WebSocket connected",
            }
        )
        # Keep alive: echo pings and wait for disconnect
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send a heartbeat
                await websocket.send_json(
                    {"type": "heartbeat", "ts": datetime.now(timezone.utc).isoformat()}
                )
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _connections:
            _connections.remove(websocket)


async def broadcast(event: dict) -> None:
    """Broadcast an event to all connected WebSocket clients."""
    dead: list[WebSocket] = []
    for ws in _connections:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _connections:
            _connections.remove(ws)

"""
Strategy instance CRUD and lifecycle management (Phase 4).
Instances are persisted in DB; the strategy engine manages the running tasks.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.db.models import AppUser, BrokerClass, BrokerConnection, StrategyClass, StrategyInstance

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/instances", tags=["instances"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _inst_to_dict(inst: StrategyInstance, strategy_name: str, runner=None) -> dict:
    pnl = None
    trade_count = None
    win_count = None
    if runner:
        try:
            pnl = float(runner._ctx.realised_pnl_today())
            trade_count = runner.trade_count
            win_count = runner.win_count
        except Exception:
            pass
    return {
        "id": inst.id,
        "name": inst.name,
        "strategy_class_name": strategy_name,
        "strategy_class_version": inst.strategy_class_version,
        "mode": inst.mode,
        "status": runner.status if runner else inst.status,
        "last_error": runner.last_error if runner else inst.last_error,
        "instruments": json.loads(inst.instruments_json),
        "timeframe": inst.timeframe,
        "params": json.loads(inst.params_json),
        "capital_allocation": float(inst.capital_allocation),
        "risk_limits": json.loads(inst.risk_limits_json),
        "last_started_at": inst.last_started_at,
        "last_stopped_at": inst.last_stopped_at,
        "created_at": inst.created_at,
        "updated_at": inst.updated_at,
        "pnl": pnl,
        "trade_count": trade_count,
        "win_count": win_count,
    }


async def _strategy_name_for(inst: StrategyInstance, db: AsyncSession) -> str:
    result = await db.execute(select(StrategyClass).where(StrategyClass.id == inst.strategy_class_id))
    sc = result.scalar_one_or_none()
    return sc.name if sc else str(inst.strategy_class_id)


async def _ensure_broker_connection(db: AsyncSession, mode: str, request: Request) -> int:
    """Return an existing BrokerConnection.id or create a placeholder one."""
    result = await db.execute(select(BrokerConnection))
    conns = result.scalars().all()
    if conns:
        return conns[0].id

    # No connections yet — create a placeholder row so the FK constraint is satisfied
    result = await db.execute(select(BrokerClass))
    bcs = result.scalars().all()
    if not bcs:
        raise HTTPException(503, "No broker classes in DB. Reload plugins first.")

    bc = bcs[0]
    now = _now()
    conn = BrokerConnection(
        broker_class_id=bc.id,
        name="Default Paper",
        credentials_ref="PAPER",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return conn.id


# ── CRUD endpoints ─────────────────────────────────────────────────────────────


class CreateInstanceRequest(BaseModel):
    name: str
    strategy_class_name: str
    mode: str = "paper"
    instruments: list[str]
    timeframe: str = "15m"
    params: dict = {}
    capital_allocation: float = 100000.0
    risk_limits: dict = {}


@router.get("")
async def list_instances(
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    result = await db.execute(select(StrategyInstance))
    instances = result.scalars().all()
    engine = getattr(request.app.state, "strategy_engine", None)
    out = []
    for inst in instances:
        runner = engine.get_runner(inst.id) if engine else None
        name = await _strategy_name_for(inst, db)
        out.append(_inst_to_dict(inst, name, runner))
    return {"instances": out}


@router.post("")
async def create_instance(
    body: CreateInstanceRequest,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        raise HTTPException(503, "Plugin loader not available")

    cls = loader.registry.strategies.get(body.strategy_class_name)
    if cls is None:
        raise HTTPException(404, f"Strategy '{body.strategy_class_name}' not found")

    # Find the DB strategy_class record
    result = await db.execute(
        select(StrategyClass).where(StrategyClass.name == body.strategy_class_name)
    )
    sc = result.scalar_one_or_none()
    if sc is None:
        raise HTTPException(
            404,
            f"Strategy '{body.strategy_class_name}' has no DB record — reload plugins first.",
        )

    broker_conn_id = await _ensure_broker_connection(db, body.mode, request)
    now = _now()
    inst = StrategyInstance(
        id=str(uuid4()),
        strategy_class_id=sc.id,
        strategy_class_version=cls.version,
        name=body.name,
        mode=body.mode,
        status="idle",
        broker_connection_id=broker_conn_id,
        instruments_json=json.dumps(body.instruments),
        timeframe=body.timeframe,
        params_json=json.dumps(body.params),
        capital_allocation=body.capital_allocation,
        risk_limits_json=json.dumps(body.risk_limits),
        created_at=now,
        updated_at=now,
    )
    db.add(inst)
    await db.commit()
    logger.info("instance created", id=inst.id, name=body.name, mode=body.mode)
    return {"id": inst.id, "name": body.name, "status": "idle"}


@router.get("/{instance_id}")
async def get_instance(
    instance_id: str,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    result = await db.execute(select(StrategyInstance).where(StrategyInstance.id == instance_id))
    inst = result.scalar_one_or_none()
    if inst is None:
        raise HTTPException(404, "Instance not found")
    engine = getattr(request.app.state, "strategy_engine", None)
    runner = engine.get_runner(instance_id) if engine else None
    name = await _strategy_name_for(inst, db)
    return _inst_to_dict(inst, name, runner)


class UpdateInstanceRequest(BaseModel):
    name: Optional[str] = None
    params: Optional[dict] = None
    capital_allocation: Optional[float] = None
    risk_limits: Optional[dict] = None


@router.patch("/{instance_id}")
async def update_instance(
    instance_id: str,
    body: UpdateInstanceRequest,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    result = await db.execute(select(StrategyInstance).where(StrategyInstance.id == instance_id))
    inst = result.scalar_one_or_none()
    if inst is None:
        raise HTTPException(404, "Instance not found")

    engine = getattr(request.app.state, "strategy_engine", None)
    runner = engine.get_runner(instance_id) if engine else None
    if runner and runner.status == "running":
        raise HTTPException(400, "Stop the instance before changing its config")

    if body.name is not None:
        inst.name = body.name
    if body.params is not None:
        inst.params_json = json.dumps(body.params)
    if body.capital_allocation is not None:
        inst.capital_allocation = body.capital_allocation
    if body.risk_limits is not None:
        inst.risk_limits_json = json.dumps(body.risk_limits)
    inst.updated_at = _now()
    await db.commit()
    return {"updated": True, "id": instance_id}


# ── Lifecycle: start / stop / delete ──────────────────────────────────────────


@router.post("/{instance_id}/start")
async def start_instance(
    instance_id: str,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    result = await db.execute(select(StrategyInstance).where(StrategyInstance.id == instance_id))
    inst = result.scalar_one_or_none()
    if inst is None:
        raise HTTPException(404, "Instance not found")

    engine = getattr(request.app.state, "strategy_engine", None)
    if engine is None:
        raise HTTPException(503, "Strategy engine not available")

    if engine.get_runner(instance_id):
        raise HTTPException(400, "Instance is already running")

    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        raise HTTPException(503, "Plugin loader not available")

    # Resolve strategy class
    sc_result = await db.execute(
        select(StrategyClass).where(StrategyClass.id == inst.strategy_class_id)
    )
    sc = sc_result.scalar_one_or_none()
    if sc is None:
        raise HTTPException(404, "Strategy class DB record not found")
    if sc.name not in loader.registry.strategies:
        raise HTTPException(404, f"Strategy '{sc.name}' not found in loaded plugins")

    # Build broker
    broker = _resolve_broker(inst.mode, request)
    await broker.connect({})

    instruments = json.loads(inst.instruments_json)

    # Subscribe to live ticks if Zerodha is connected (paper mode uses real ticks)
    tick_source: str = "none"
    if inst.mode in ("paper", "live"):
        zerodha_info = getattr(request.app.state, "broker_instances", {}).get("Zerodha Primary")
        if zerodha_info and zerodha_info.get("status") == "connected":
            zerodha = zerodha_info["instance"]
            try:
                await zerodha.subscribe_ticks(instruments)
                tick_source = "zerodha"
                logger.info("subscribed instruments to Zerodha", instruments=instruments)
            except Exception as exc:
                logger.warning("tick subscription failed (non-fatal)", error=str(exc))
        else:
            logger.warning(
                "instance starting without a live tick source — strategy will idle. "
                "Connect Zerodha (Settings) or use Backtest to validate strategy logic.",
                instance_id=instance_id,
                mode=inst.mode,
                instruments=instruments,
            )

    from xillion.api.ws import broadcast as ws_broadcast
    runner = await engine.spawn(
        instance_id=instance_id,
        strategy_name=sc.name,
        broker=broker,
        instruments=instruments,
        timeframe=inst.timeframe,
        capital=Decimal(str(inst.capital_allocation)),
        params=json.loads(inst.params_json),
        mode=inst.mode,
        broker_connection_id=inst.broker_connection_id,
        instance_name=inst.name,
        on_trade_close=ws_broadcast,
    )

    inst.status = "running"
    inst.last_started_at = _now()
    inst.updated_at = _now()
    await db.commit()
    logger.info("instance started", id=instance_id, mode=inst.mode, tick_source=tick_source)
    return {
        "started": True,
        "instance_id": instance_id,
        "status": runner.status,
        "tick_source": tick_source,
        "warning": (
            "No live tick source. Strategy will idle until Zerodha is connected. "
            "Use Backtest to validate strategy logic offline."
            if tick_source == "none" and inst.mode == "paper"
            else None
        ),
    }


def _resolve_broker(mode: str, request: Request):
    """Return the right broker object for the given mode."""
    from brokers.paper import PaperBroker

    if mode == "paper":
        broker = PaperBroker(slippage_bps=10)
        # Wire MarketDataBus ticks to update PaperBroker's last prices
        bus = getattr(request.app.state, "bus", None)
        if bus:
            async def _on_bus_tick(tick):
                broker.on_tick(tick)
            # We'll register the handler without knowing the symbols yet;
            # register for all bus symbols by adding a wildcard handler at the bus level
            # (not implemented in bus — handled at subscribe_ticks call instead)
        return broker

    if mode == "live":
        instances = getattr(request.app.state, "broker_instances", {})
        info = instances.get("Zerodha Primary")
        if info and info.get("status") == "connected" and info.get("instance"):
            return info["instance"]
        raise HTTPException(400, "Zerodha not connected. Cannot start in live mode.")

    raise HTTPException(400, f"Unsupported mode: {mode!r}")


@router.post("/{instance_id}/stop")
async def stop_instance(
    instance_id: str,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    result = await db.execute(select(StrategyInstance).where(StrategyInstance.id == instance_id))
    inst = result.scalar_one_or_none()
    if inst is None:
        raise HTTPException(404, "Instance not found")

    engine = getattr(request.app.state, "strategy_engine", None)
    if engine:
        await engine.stop_instance(instance_id, reason="user_stopped")

    inst.status = "idle"
    inst.last_stopped_at = _now()
    inst.updated_at = _now()
    await db.commit()
    logger.info("instance stopped", id=instance_id)
    return {"stopped": True, "instance_id": instance_id}


@router.delete("/{instance_id}")
async def delete_instance(
    instance_id: str,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    result = await db.execute(select(StrategyInstance).where(StrategyInstance.id == instance_id))
    inst = result.scalar_one_or_none()
    if inst is None:
        raise HTTPException(404, "Instance not found")

    engine = getattr(request.app.state, "strategy_engine", None)
    runner = engine.get_runner(instance_id) if engine else None
    if runner and runner.status == "running":
        raise HTTPException(400, "Stop the instance before deleting it")

    await db.delete(inst)
    await db.commit()
    logger.info("instance deleted", id=instance_id)
    return {"deleted": True, "instance_id": instance_id}

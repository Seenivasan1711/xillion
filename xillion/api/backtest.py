"""
Backtest API endpoints — trigger and retrieve backtest runs.
"""
import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.auth.data_provider_credstore import load_provider_credentials
from xillion.core.events import Bar
from xillion.data.backtest_runs import get_backtest_run, list_backtest_runs, persist_backtest_run
from xillion.data.coverage import BarCoverageRepository
from xillion.data.repository import BarRepository
from xillion.data.warehouse import BarWarehouse
from xillion.db.models import AppUser
from xillion.db.session import get_session_factory
from xillion.engine.backtest_engine import BacktestEngine, FeeConfig

router = APIRouter(prefix="/backtest", tags=["backtest"])


def _parse_csv_bars(content: bytes, default_timeframe: str = "1m") -> tuple[list[Bar], list[str]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    bars: list[Bar] = []
    errors: list[str] = []
    for i, row in enumerate(reader, start=2):
        try:
            bars.append(
                Bar(
                    symbol=row["symbol"],
                    timeframe=row.get("timeframe") or default_timeframe,
                    ts=datetime.fromisoformat(row["ts"]),
                    open=Decimal(row["open"]),
                    high=Decimal(row["high"]),
                    low=Decimal(row["low"]),
                    close=Decimal(row["close"]),
                    volume=int(row.get("volume") or 0),
                )
            )
        except Exception as exc:
            errors.append(f"row {i}: {exc}")
            if len(errors) > 10:
                break
    return bars, errors


class RunBacktestRequest(BaseModel):
    strategy_name: str
    instruments: list[str]
    timeframe: str = "5m"
    initial_capital: float = 100000.0
    slippage_bps: int = 5
    params: dict = {}
    bars: Optional[list[dict]] = None  # inline bars for testing


@router.post("/run")
async def run_backtest(body: RunBacktestRequest, request: Request):
    """Run a backtest. Bars can be provided inline or pre-loaded via /upload."""
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        raise HTTPException(503, "Plugin loader not available")

    cls = loader.registry.strategies.get(body.strategy_name)
    if cls is None:
        raise HTTPException(404, f"Strategy '{body.strategy_name}' not found")

    if not body.bars:
        raise HTTPException(422, "No bars provided. Use 'bars' field or upload CSV first.")

    bars: list[Bar] = []
    for b in body.bars:
        bars.append(
            Bar(
                symbol=b["symbol"],
                timeframe=b.get("timeframe", body.timeframe),
                ts=datetime.fromisoformat(b["ts"]),
                open=Decimal(str(b["open"])),
                high=Decimal(str(b["high"])),
                low=Decimal(str(b["low"])),
                close=Decimal(str(b["close"])),
                volume=int(b.get("volume", 0)),
            )
        )

    strategy = cls()
    engine = BacktestEngine()
    result = await engine.run(
        strategy=strategy,
        bars=bars,
        instruments=body.instruments,
        timeframe=body.timeframe,
        initial_capital=body.initial_capital,
        params=body.params,
        slippage_bps=body.slippage_bps,
    )
    await persist_backtest_run(get_session_factory(), result)

    return {
        "run_id": result.run_id,
        "strategy_name": result.strategy_name,
        "status": result.status,
        "error": result.error,
        "metrics": result.metrics,
        "equity_curve": result.equity_curve,
        "trade_count": len(result.trades),
        "from_ts": result.from_ts.isoformat(),
        "to_ts": result.to_ts.isoformat(),
    }


@router.post("/run-csv")
async def run_backtest_csv(
    request: Request,
    file: UploadFile = File(...),
    strategy_name: str = Form(...),
    instruments: str = Form(""),
    timeframe: str = Form("5m"),
    initial_capital: float = Form(100000.0),
    slippage_bps: int = Form(5),
    params: str = Form("{}"),
):
    """
    Upload a CSV of bars and run a backtest in one shot.
    CSV columns: symbol, ts (ISO datetime), open, high, low, close, volume [, timeframe]
    """
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        raise HTTPException(503, "Plugin loader not available")

    cls = loader.registry.strategies.get(strategy_name)
    if cls is None:
        raise HTTPException(404, f"Strategy '{strategy_name}' not found")

    try:
        params_dict = json.loads(params) if params else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"Invalid params JSON: {exc}")

    content = await file.read()
    bars, parse_errors = _parse_csv_bars(content, default_timeframe=timeframe)
    if not bars:
        detail = "; ".join(parse_errors) if parse_errors else "empty CSV"
        raise HTTPException(422, f"No bars parsed from CSV: {detail}")

    instr_list = [s.strip() for s in instruments.split(",") if s.strip()] or [bars[0].symbol]

    strategy = cls()
    engine = BacktestEngine()
    result = await engine.run(
        strategy=strategy,
        bars=bars,
        instruments=instr_list,
        timeframe=timeframe,
        initial_capital=initial_capital,
        params=params_dict,
        slippage_bps=slippage_bps,
    )
    await persist_backtest_run(get_session_factory(), result)

    return {
        "run_id": result.run_id,
        "strategy_name": result.strategy_name,
        "status": result.status,
        "error": result.error,
        "metrics": result.metrics,
        "equity_curve": result.equity_curve,
        "trade_count": len(result.trades),
        "from_ts": result.from_ts.isoformat(),
        "to_ts": result.to_ts.isoformat(),
        "bars_loaded": len(bars),
        "parse_errors": parse_errors,
    }


class RunBacktestProviderRequest(BaseModel):
    strategy_name: str
    provider_name: str
    symbol: str
    exchange: str = "NFO"
    instrument_type: str = "option"
    timeframe: str = "1d"
    from_date: date
    to_date: date
    initial_capital: float = 100000.0
    slippage_bps: int = 5
    params: dict = {}


@router.post("/run-provider")
async def run_backtest_provider(
    body: RunBacktestProviderRequest,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    """Fetch historical bars from a configured data provider and run a
    backtest in one shot — the provider-based alternative to /run-csv."""
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        raise HTTPException(503, "Plugin loader not available")

    strategy_cls = loader.registry.strategies.get(body.strategy_name)
    if strategy_cls is None:
        raise HTTPException(404, f"Strategy '{body.strategy_name}' not found")

    provider_cls = loader.registry.data_providers.get(body.provider_name)
    if provider_cls is None:
        raise HTTPException(404, f"Data provider '{body.provider_name}' not found")

    provider = provider_cls()
    caps = provider.capabilities

    credentials = None
    if caps.requires_credentials:
        credentials = await load_provider_credentials(db, body.provider_name)
        if credentials is None:
            raise HTTPException(
                422,
                f"'{body.provider_name}' needs credentials — configure it under Settings → Data Providers",
            )

    broker = None
    if caps.requires_broker:
        broker_instances = getattr(request.app.state, "broker_instances", {})
        connected = next(
            (info["instance"] for info in broker_instances.values() if info.get("status") == "connected"),
            None,
        )
        if connected is None:
            raise HTTPException(
                422,
                f"'{body.provider_name}' needs a connected broker — connect one under Settings → Brokers",
            )
        broker = connected

    session_factory = get_session_factory()
    warehouse = BarWarehouse(
        BarRepository(session_factory),
        BarCoverageRepository(session_factory),
    )
    try:
        bars = await warehouse.get_bars(
            provider,
            body.symbol,
            body.exchange,
            body.timeframe,
            body.from_date,
            body.to_date,
            instrument_type=body.instrument_type,
            credentials=credentials,
            broker=broker,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    if not bars:
        raise HTTPException(
            422,
            f"No bars returned from '{body.provider_name}' for {body.symbol} "
            f"between {body.from_date} and {body.to_date}",
        )

    strategy = strategy_cls()
    engine = BacktestEngine()
    result = await engine.run(
        strategy=strategy,
        bars=bars,
        instruments=[body.symbol],
        timeframe=body.timeframe,
        initial_capital=body.initial_capital,
        params=body.params,
        slippage_bps=body.slippage_bps,
    )
    await persist_backtest_run(session_factory, result)

    return {
        "run_id": result.run_id,
        "strategy_name": result.strategy_name,
        "status": result.status,
        "error": result.error,
        "metrics": result.metrics,
        "equity_curve": result.equity_curve,
        "trade_count": len(result.trades),
        "from_ts": result.from_ts.isoformat(),
        "to_ts": result.to_ts.isoformat(),
        "bars_loaded": len(bars),
    }


class BacktestRunSummary(BaseModel):
    id: str
    strategy_class_id: int
    status: str
    timeframe: str
    from_ts: str
    to_ts: str
    initial_capital: float
    started_at: str
    finished_at: Optional[str]
    metrics: dict
    error: Optional[str] = None


@router.get("/runs")
async def get_backtest_runs(limit: int = 50):
    """Recent backtest run history -- persisted since CP3 (previously every
    result was gone the moment the response left the server)."""
    runs = await list_backtest_runs(get_session_factory(), limit=limit)
    return {
        "runs": [
            BacktestRunSummary(
                id=r.id,
                strategy_class_id=r.strategy_class_id,
                status=r.status,
                timeframe=r.timeframe,
                from_ts=r.from_ts,
                to_ts=r.to_ts,
                initial_capital=float(r.initial_capital),
                started_at=r.started_at,
                finished_at=r.finished_at,
                metrics=json.loads(r.metrics_json) if r.metrics_json else {},
                error=r.error,
            )
            for r in runs
        ]
    }


@router.get("/runs/{run_id}")
async def get_backtest_run_detail(run_id: str):
    run, trades = await get_backtest_run(get_session_factory(), run_id)
    if run is None:
        raise HTTPException(404, f"Backtest run '{run_id}' not found")
    return {
        "id": run.id,
        "strategy_class_id": run.strategy_class_id,
        "strategy_class_version": run.strategy_class_version,
        "params": json.loads(run.params_json),
        "instruments": json.loads(run.instruments_json),
        "timeframe": run.timeframe,
        "from_ts": run.from_ts,
        "to_ts": run.to_ts,
        "initial_capital": float(run.initial_capital),
        "slippage_bps": run.slippage_bps,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "error": run.error,
        "metrics": json.loads(run.metrics_json) if run.metrics_json else {},
        "equity_curve": json.loads(run.equity_curve_json) if run.equity_curve_json else [],
        "trades": [
            {
                "symbol": t.symbol,
                "side": t.side,
                "quantity": t.quantity,
                "entry_ts": t.entry_ts,
                "entry_price": float(t.entry_price),
                "exit_ts": t.exit_ts,
                "exit_price": float(t.exit_price) if t.exit_price is not None else None,
                "pnl": float(t.pnl) if t.pnl is not None else None,
                "tag": t.tag,
            }
            for t in trades
        ],
    }

"""
Backtest API endpoints — trigger and retrieve backtest runs.
"""
import csv
import io
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from xillion.core.events import Bar
from xillion.engine.backtest_engine import BacktestEngine, FeeConfig

router = APIRouter(prefix="/backtest", tags=["backtest"])


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


@router.post("/upload-csv")
async def upload_csv(file: UploadFile, request: Request):
    """
    Upload a CSV of historical bars.
    Expected columns: symbol, ts (ISO datetime), open, high, low, close, volume
    Optional: timeframe, exchange
    """
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    bars: list[Bar] = []
    errors: list[str] = []
    for i, row in enumerate(reader, start=2):
        try:
            bars.append(
                Bar(
                    symbol=row["symbol"],
                    timeframe=row.get("timeframe", "1m"),
                    ts=datetime.fromisoformat(row["ts"]),
                    open=Decimal(row["open"]),
                    high=Decimal(row["high"]),
                    low=Decimal(row["low"]),
                    close=Decimal(row["close"]),
                    volume=int(row.get("volume", 0)),
                )
            )
        except Exception as exc:
            errors.append(f"row {i}: {exc}")
            if len(errors) > 10:
                break

    # Store in app state for subsequent backtest calls
    store = getattr(request.app.state, "uploaded_bars", {})
    key = f"{bars[0].symbol}:{bars[0].timeframe}" if bars else "unknown"
    store[key] = bars
    request.app.state.uploaded_bars = store

    return {"loaded": len(bars), "errors": errors, "key": key}

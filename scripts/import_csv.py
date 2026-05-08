#!/usr/bin/env python
"""
Import historical OHLCV bars from a CSV file into the xillion database.

CSV format (header required):
  symbol, ts, open, high, low, close, volume [, timeframe, exchange]

Example:
  python scripts/import_csv.py data/nifty_5m.csv --timeframe 5m --symbol NIFTY50
"""
import asyncio
import csv
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).parent.parent))

app = typer.Typer()


@app.command()
def main(
    file: Path = typer.Argument(..., help="Path to CSV file"),
    symbol: str = typer.Option("", help="Override symbol from CSV"),
    timeframe: str = typer.Option("1m", help="Timeframe (default: 1m)"),
    exchange: str = typer.Option("NSE", help="Exchange"),
    batch_size: int = typer.Option(1000, help="DB write batch size"),
) -> None:
    """Import OHLCV bars from a CSV file into the database."""

    async def _run() -> None:
        from xillion.core.events import Bar
        from xillion.data.repository import BarRepository
        from xillion.db.session import get_session_factory, init_db

        await init_db()
        factory = get_session_factory()
        repo = BarRepository(factory)

        bars: list[Bar] = []
        count = 0
        errors = 0

        with open(file) as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, 1):
                try:
                    sym = symbol or row.get("symbol", "")
                    tf = row.get("timeframe", timeframe)
                    ts = datetime.fromisoformat(row["ts"])
                    bar = Bar(
                        symbol=sym,
                        timeframe=tf,
                        ts=ts,
                        open=Decimal(row["open"]),
                        high=Decimal(row["high"]),
                        low=Decimal(row["low"]),
                        close=Decimal(row["close"]),
                        volume=int(row.get("volume", 0)),
                    )
                    bars.append(bar)
                    if len(bars) >= batch_size:
                        await repo.upsert_bars(bars, exchange=exchange)
                        count += len(bars)
                        bars.clear()
                        print(f"  Imported {count} bars...")
                except Exception as exc:
                    errors += 1
                    if errors <= 5:
                        print(f"  Row {i} error: {exc}", file=sys.stderr)

        if bars:
            await repo.upsert_bars(bars, exchange=exchange)
            count += len(bars)

        print(f"Done. Imported {count} bars. Errors: {errors}.")

    asyncio.run(_run())


if __name__ == "__main__":
    app()

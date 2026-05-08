"""
Database access layer for historical bar data (read/write).
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.core.events import Bar
from xillion.db.models import BarRecord

try:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    _has_pg = True
except ImportError:
    _has_pg = False


class BarRepository:
    def __init__(self, session_factory) -> None:
        self._factory = session_factory

    async def upsert_bars(self, bars: list[Bar], exchange: str = "NSE") -> None:
        async with self._factory() as session:
            for bar in bars:
                record = BarRecord(
                    symbol=bar.symbol,
                    exchange=exchange,
                    timeframe=bar.timeframe,
                    ts=bar.ts.isoformat(),
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=bar.volume,
                )
                await session.merge(record)
            await session.commit()

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        from_ts: datetime,
        to_ts: datetime,
        exchange: str = "NSE",
    ) -> list[Bar]:
        async with self._factory() as session:
            result = await session.execute(
                select(BarRecord)
                .where(
                    BarRecord.symbol == symbol,
                    BarRecord.timeframe == timeframe,
                    BarRecord.ts >= from_ts.isoformat(),
                    BarRecord.ts <= to_ts.isoformat(),
                )
                .order_by(BarRecord.ts)
            )
            records = result.scalars().all()
            return [
                Bar(
                    symbol=r.symbol,
                    timeframe=r.timeframe,
                    ts=datetime.fromisoformat(r.ts),
                    open=r.open,  # type: ignore[arg-type]
                    high=r.high,  # type: ignore[arg-type]
                    low=r.low,  # type: ignore[arg-type]
                    close=r.close,  # type: ignore[arg-type]
                    volume=r.volume,
                )
                for r in records
            ]

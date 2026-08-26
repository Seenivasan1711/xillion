"""
Database access layer for historical bar data (read/write).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from xillion.core.events import Bar
from xillion.db.models import BarRecord

_UPDATE_COLUMNS = ("open", "high", "low", "close", "volume")
_COLUMNS_PER_ROW = 9  # symbol, exchange, timeframe, ts, open, high, low, close, volume

# SQLite's default build caps bound parameters per statement at 999
# (SQLITE_MAX_VARIABLE_NUMBER); a whole-file bhavcopy fetch persists
# hundreds-to-low-thousands of contracts in one upsert_bars() call, which
# blew past that limit the first time this ran against real data ("too many
# SQL variables"). Postgres' limit (65535) is high enough that 100-row
# batches are just extra round-trips there, not a fix it needed -- but
# batching the same way for both dialects keeps this one code path correct
# everywhere instead of special-casing sqlite.
_BATCH_SIZE = 100


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


class BarRepository:
    def __init__(self, session_factory) -> None:
        self._factory = session_factory

    async def upsert_bars(self, bars: list[Bar], exchange: str = "NSE") -> None:
        """Bulk upsert via INSERT .. ON CONFLICT DO UPDATE, batched (dialect-
        aware: postgresql in production, sqlite in tests) instead of one
        `session.merge()` round-trip per bar -- the whole-file bhavcopy lever
        persists hundreds of rows per fetch, so a per-row merge loop would
        turn "one HTTP call" back into hundreds of DB round-trips."""
        if not bars:
            return
        async with self._factory() as session:
            dialect = session.get_bind().dialect.name
            insert_fn = pg_insert if dialect == "postgresql" else sqlite_insert
            rows = [
                {
                    "symbol": bar.symbol,
                    "exchange": exchange,
                    "timeframe": bar.timeframe,
                    "ts": bar.ts.isoformat(),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": bar.volume,
                }
                for bar in bars
            ]
            for batch in _chunks(rows, _BATCH_SIZE):
                stmt = insert_fn(BarRecord).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "exchange", "timeframe", "ts"],
                    set_={col: getattr(stmt.excluded, col) for col in _UPDATE_COLUMNS},
                )
                await session.execute(stmt)
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
                    BarRecord.exchange == exchange,
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

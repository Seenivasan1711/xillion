"""
Tracks which date range is already fetched for a (symbol, exchange,
timeframe, provider) combination -- the cache-coverage half of BarWarehouse.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from xillion.db.models import BarCoverage

WILDCARD_SYMBOL = (
    "*"  # coverage key for whole-file-bulk providers (per exchange/day, not per symbol)
)


@dataclass(frozen=True)
class CoverageRange:
    from_date: date
    to_date: date


def compute_gaps(
    existing: CoverageRange | None, requested_from: date, requested_to: date
) -> list[tuple[date, date]]:
    """Return the sub-ranges of [requested_from, requested_to] not already
    covered by `existing`. At most two gaps (before and after), since
    coverage is tracked as a single contiguous range."""
    if existing is None:
        return [(requested_from, requested_to)]
    gaps: list[tuple[date, date]] = []
    if requested_from < existing.from_date:
        gaps.append((requested_from, existing.from_date - timedelta(days=1)))
    if requested_to > existing.to_date:
        start = max(requested_from, existing.to_date + timedelta(days=1))
        gaps.append((start, requested_to))
    return gaps


class BarCoverageRepository:
    def __init__(self, session_factory) -> None:
        self._factory = session_factory

    async def get(
        self, symbol: str, exchange: str, timeframe: str, provider_name: str
    ) -> CoverageRange | None:
        async with self._factory() as session:
            row = await session.get(BarCoverage, (symbol, exchange, timeframe, provider_name))
            if row is None:
                return None
            return CoverageRange(
                from_date=date.fromisoformat(row.from_date),
                to_date=date.fromisoformat(row.to_date),
            )

    async def extend(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        provider_name: str,
        from_date: date,
        to_date: date,
    ) -> None:
        """Widen the covered range to include [from_date, to_date]."""
        existing = await self.get(symbol, exchange, timeframe, provider_name)
        if existing is not None:
            from_date = min(from_date, existing.from_date)
            to_date = max(to_date, existing.to_date)

        async with self._factory() as session:
            dialect = session.get_bind().dialect.name
            insert_fn = pg_insert if dialect == "postgresql" else sqlite_insert
            stmt = insert_fn(BarCoverage).values(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                provider_name=provider_name,
                from_date=from_date.isoformat(),
                to_date=to_date.isoformat(),
                updated_at=datetime.utcnow().isoformat(),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "exchange", "timeframe", "provider_name"],
                set_={
                    "from_date": stmt.excluded.from_date,
                    "to_date": stmt.excluded.to_date,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)
            await session.commit()

"""
Point-in-time option chain snapshots -- what a backtest needs to answer
"what strikes/expiries existed for NIFTY, as of trading date X", which the
live `instrument` table (a truncate-and-reload cache of TODAY only) can't
answer for a date in the past. Mirrors xillion/data/warehouse.py's
cache-on-fetch pattern (CP2), one day at a time rather than a date range,
since resolve_strike/get_spot are called per-simulated-day, not as a batch.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from xillion.core.instruments import InstrumentRow
from xillion.db.models import OptionChainSnapshot

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class HistoricalOptionRow:
    """One contract's metadata + close, as it stood on `trade_date`."""
    tradingsymbol: str
    exchange: str
    underlying: str
    expiry: Optional[date]
    strike: Optional[Decimal]
    option_type: Optional[str]  # "CE" | "PE" | None (futures)
    lot_size: int
    close: Decimal
    underlying_price: Optional[Decimal]

    def as_instrument_row(self) -> InstrumentRow:
        """resolve_option()/select_expiry()/nearest_strike() (xillion/core/
        instruments.py) already do exactly the strike-ladder-walking this
        needs -- reuse them rather than writing a second resolver. Neither
        function reads instrument_token/segment/tick_size, so those are
        synthesized placeholders, not real exchange values (bhavcopy
        doesn't carry a tick size or token at all)."""
        return InstrumentRow(
            instrument_token=hash(self.tradingsymbol) & 0x7FFFFFFF,
            exchange=self.exchange, tradingsymbol=self.tradingsymbol, name=self.underlying,
            expiry=self.expiry, strike=self.strike, option_type=self.option_type,
            segment=f"{self.exchange}-OPT", lot_size=self.lot_size,
            tick_size=Decimal("0.05"),
        )


class OptionChainProvider(Protocol):
    async def fetch_option_chain_for_day(self, day: date) -> list[HistoricalOptionRow]: ...


class OptionChainRepository:
    def __init__(self, session_factory) -> None:
        self._factory = session_factory

    async def upsert(self, rows: list[HistoricalOptionRow], trade_date: date) -> None:
        if not rows:
            return
        async with self._factory() as session:
            dialect = session.get_bind().dialect.name
            insert_fn = pg_insert if dialect == "postgresql" else sqlite_insert
            values = [
                {
                    "trade_date": trade_date.isoformat(), "exchange": r.exchange,
                    "tradingsymbol": r.tradingsymbol, "underlying": r.underlying,
                    "expiry": r.expiry.isoformat() if r.expiry else None,
                    "strike": float(r.strike) if r.strike is not None else None,
                    "option_type": r.option_type, "lot_size": r.lot_size,
                    "close": float(r.close),
                    "underlying_price": float(r.underlying_price) if r.underlying_price is not None else None,
                }
                for r in rows
            ]
            # Same 100-row batching as BarRepository.upsert_bars -- SQLite's
            # 999-bound-parameter ceiling bit that code on a real whole-file
            # fetch; this table gets whole-file-sized batches too.
            for i in range(0, len(values), 100):
                batch = values[i:i + 100]
                stmt = insert_fn(OptionChainSnapshot).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["trade_date", "exchange", "tradingsymbol"],
                    set_={
                        col: getattr(stmt.excluded, col)
                        for col in ("underlying", "expiry", "strike", "option_type",
                                    "lot_size", "close", "underlying_price")
                    },
                )
                await session.execute(stmt)
            await session.commit()

    async def get(self, underlying: str, exchange: str, trade_date: date) -> list[HistoricalOptionRow]:
        async with self._factory() as session:
            result = await session.execute(
                select(OptionChainSnapshot).where(
                    OptionChainSnapshot.underlying == underlying,
                    OptionChainSnapshot.exchange == exchange,
                    OptionChainSnapshot.trade_date == trade_date.isoformat(),
                )
            )
            records = result.scalars().all()
        return [
            HistoricalOptionRow(
                tradingsymbol=r.tradingsymbol, exchange=r.exchange, underlying=r.underlying,
                expiry=date.fromisoformat(r.expiry) if r.expiry else None,
                strike=Decimal(str(r.strike)) if r.strike is not None else None,
                option_type=r.option_type, lot_size=r.lot_size, close=Decimal(str(r.close)),
                underlying_price=Decimal(str(r.underlying_price)) if r.underlying_price is not None else None,
            )
            for r in records
        ]

    async def has_any_for_day(self, exchange: str, trade_date: date) -> bool:
        """Cheap "was this exchange/day fetched at all" check -- used to
        avoid re-fetching a day already known to have nothing (a holiday),
        the same purpose bar_coverage serves for BarWarehouse."""
        async with self._factory() as session:
            result = await session.execute(
                select(OptionChainSnapshot.tradingsymbol).where(
                    OptionChainSnapshot.exchange == exchange,
                    OptionChainSnapshot.trade_date == trade_date.isoformat(),
                ).limit(1)
            )
            return result.scalar_one_or_none() is not None


class OptionChainWarehouse:
    """Cache-through: check the DB for (underlying, exchange, day); on a
    miss, fetch the WHOLE day's chain from the provider (every underlying at
    once -- same whole-file-bulk lever as BarWarehouse) and persist it, so a
    later request for a *different* underlying on an already-fetched day is
    free."""

    def __init__(self, provider: OptionChainProvider, repository: OptionChainRepository) -> None:
        self._provider = provider
        self._repo = repository
        # Per-process memo of "day already confirmed fetched" to avoid a
        # DB round-trip on every single call within one backtest run.
        self._fetched_days: set[tuple[str, date]] = set()

    async def get_chain(self, underlying: str, exchange: str, day: date) -> list[HistoricalOptionRow]:
        if (exchange, day) not in self._fetched_days:
            if not await self._repo.has_any_for_day(exchange, day):
                if day.weekday() < 5:
                    all_rows = await self._provider.fetch_option_chain_for_day(day)
                    await self._repo.upsert(all_rows, day)
                    logger.info(
                        "option chain warehouse: day fetched",
                        exchange=exchange, day=str(day), contracts=len(all_rows),
                    )
            self._fetched_days.add((exchange, day))
        return await self._repo.get(underlying, exchange, day)

    async def get_underlying_price(self, underlying: str, exchange: str, day: date) -> Optional[Decimal]:
        rows = await self.get_chain(underlying, exchange, day)
        for r in rows:
            if r.underlying_price is not None:
                return r.underlying_price
        return None

    async def get_close(self, tradingsymbol: str, exchange: str, underlying: str, day: date) -> Optional[Decimal]:
        rows = await self.get_chain(underlying, exchange, day)
        for r in rows:
            if r.tradingsymbol == tradingsymbol:
                return r.close
        return None

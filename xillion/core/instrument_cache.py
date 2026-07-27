"""
Instrument dump cache: refreshes the `instrument` DB table from a broker's
instrument dump and reads it back into the resolver's InstrumentRow
dataclass. Kite's dump doesn't change intraday except around rare
instrument suspensions -- refreshed once daily (see main.py).
"""
from datetime import date as _date
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import delete, select

from xillion.core.instruments import InstrumentRow
from xillion.db.models import Instrument

logger = structlog.get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def refresh_instrument_cache(
    broker, db_factory, exchanges: Optional[list[str]] = None,
) -> int:
    """Fetch the broker's instrument dump and reload the `instrument` table.
    Truncate + reload -- cheap (tens of thousands of rows), run once/day."""
    rows = await broker.fetch_instrument_dump(exchanges)
    now = _now_iso()

    async with db_factory()() as session:
        await session.execute(delete(Instrument))
        for row in rows:
            session.add(Instrument(
                instrument_token=row.instrument_token,
                exchange=row.exchange,
                tradingsymbol=row.tradingsymbol,
                name=row.name,
                expiry=row.expiry.isoformat() if row.expiry else None,
                strike=float(row.strike) if row.strike is not None else None,
                option_type=row.option_type,
                segment=row.segment,
                lot_size=row.lot_size,
                tick_size=float(row.tick_size),
                last_updated=now,
            ))
        await session.commit()

    logger.info("instrument cache refreshed", row_count=len(rows), exchanges=exchanges)
    return len(rows)


async def load_instrument_rows(db_factory, name: Optional[str] = None) -> list[InstrumentRow]:
    """Read cached instrument rows back into the resolver's dataclass,
    optionally filtered to one underlying."""
    async with db_factory()() as session:
        stmt = select(Instrument)
        if name is not None:
            stmt = stmt.where(Instrument.name == name)
        result = await session.execute(stmt)
        instruments = result.scalars().all()

    return [
        InstrumentRow(
            instrument_token=inst.instrument_token,
            exchange=inst.exchange,
            tradingsymbol=inst.tradingsymbol,
            name=inst.name,
            expiry=_date.fromisoformat(inst.expiry) if inst.expiry else None,
            strike=Decimal(str(inst.strike)) if inst.strike is not None else None,
            option_type=inst.option_type,
            segment=inst.segment,
            lot_size=inst.lot_size,
            tick_size=Decimal(str(inst.tick_size)),
        )
        for inst in instruments
    ]

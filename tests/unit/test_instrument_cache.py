"""Tests for the instrument dump cache: DB round-trip of InstrumentRow data."""
from datetime import date
from decimal import Decimal

import pytest

from xillion.core.instrument_cache import load_instrument_rows, refresh_instrument_cache
from xillion.core.instruments import InstrumentRow
from xillion.db.session import get_session_factory, init_db


class _FakeBroker:
    def __init__(self, rows: list[InstrumentRow]) -> None:
        self._rows = rows

    async def fetch_instrument_dump(self, exchanges=None) -> list[InstrumentRow]:
        return self._rows


def _row(token: int, name: str, exchange: str, tradingsymbol: str,
         expiry=None, strike=None, option_type=None) -> InstrumentRow:
    return InstrumentRow(
        instrument_token=token,
        exchange=exchange,
        tradingsymbol=tradingsymbol,
        name=name,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        segment=f"{exchange}-OPT" if option_type else f"{exchange}-INDICES",
        lot_size=25,
        tick_size=Decimal("0.05"),
    )


@pytest.mark.asyncio
async def test_refresh_and_load_round_trip():
    await init_db()

    rows = [
        _row(1, "NIFTY", "NFO", "NIFTY26JUL2925000CE",
             expiry=date(2026, 7, 29), strike=Decimal(25000), option_type="CE"),
        _row(2, "NIFTY", "NFO", "NIFTY26JUL2925000PE",
             expiry=date(2026, 7, 29), strike=Decimal(25000), option_type="PE"),
        _row(3, "SENSEX", "BFO", "SENSEX26JUL3080000CE",
             expiry=date(2026, 7, 30), strike=Decimal(80000), option_type="CE"),
    ]
    broker = _FakeBroker(rows)

    count = await refresh_instrument_cache(broker, get_session_factory)
    assert count == 3

    all_rows = await load_instrument_rows(get_session_factory)
    assert len(all_rows) == 3

    nifty_rows = await load_instrument_rows(get_session_factory, name="NIFTY")
    assert len(nifty_rows) == 2
    assert {r.option_type for r in nifty_rows} == {"CE", "PE"}
    assert all(r.expiry == date(2026, 7, 29) for r in nifty_rows)
    assert all(r.strike == Decimal(25000) for r in nifty_rows)

    sensex_rows = await load_instrument_rows(get_session_factory, name="SENSEX")
    assert len(sensex_rows) == 1
    assert sensex_rows[0].exchange == "BFO"


@pytest.mark.asyncio
async def test_refresh_truncates_previous_rows():
    await init_db()

    broker_v1 = _FakeBroker([_row(10, "NIFTY", "NFO", "NIFTY_OLD")])
    await refresh_instrument_cache(broker_v1, get_session_factory)
    assert len(await load_instrument_rows(get_session_factory)) == 1

    broker_v2 = _FakeBroker([
        _row(11, "NIFTY", "NFO", "NIFTY_NEW_A"),
        _row(12, "NIFTY", "NFO", "NIFTY_NEW_B"),
    ])
    count = await refresh_instrument_cache(broker_v2, get_session_factory)
    assert count == 2

    remaining = await load_instrument_rows(get_session_factory)
    assert len(remaining) == 2
    assert {r.tradingsymbol for r in remaining} == {"NIFTY_NEW_A", "NIFTY_NEW_B"}

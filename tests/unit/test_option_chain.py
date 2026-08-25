"""
OptionChainWarehouse (Options Stage 2 / CP11 follow-up): the "own the data"
verification for options -- same shape as test_bar_warehouse.py's CP2 test
(second request for an already-fetched day makes zero provider calls), plus
the NSE bhavcopy row parser against the real column names confirmed live
(2026-08-24), and the InstrumentRow conversion resolve_option() consumes.
"""
from datetime import date
from decimal import Decimal

import pytest

from data_providers.nse_bhavcopy import NSEBhavcopyProvider
from xillion.core.instruments import resolve_option
from xillion.data.option_chain import HistoricalOptionRow, OptionChainRepository, OptionChainWarehouse
from xillion.db.session import get_session_factory, init_db


# Real header + two rows, shaped exactly like a live bhavcopy file fetched
# and inspected directly against nsearchives.nseindia.com on 2026-08-24.
_REAL_HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,"
    "FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,"
    "LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,"
    "TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4"
)
_REAL_ROW = (
    "2026-08-24,2026-08-24,FO,NSE,IDO,1,,NIFTY,,2026-08-25,2026-08-25,24200.00,PE,"
    "NIFTY26AUG24200PE,100,110,95,105.5,105,104,24219.05,105.5,1000,10,500,1000000,"
    "50,F1,65,,,,,"
)


class _FakeBhavcopyProvider:
    """Scripted stand-in returning parsed rows for one canned day, so the
    warehouse test doesn't depend on network access."""

    def __init__(self) -> None:
        self.calls: list[date] = []
        real = NSEBhavcopyProvider()
        import csv
        import io
        reader = csv.DictReader(io.StringIO(_REAL_HEADER + "\n" + _REAL_ROW))
        self._canned_rows = [real._row_to_option_row(r) for r in reader]

    async def fetch_option_chain_for_day(self, day: date):
        self.calls.append(day)
        return list(self._canned_rows)


def test_row_parser_reads_real_column_names():
    """Confirms the parser reads the ACTUAL live bhavcopy schema, not a
    guessed one -- StrkPric/XpryDt/OptnTp/UndrlygPric/NewBrdLotQty/ClsPric."""
    provider = NSEBhavcopyProvider()
    import csv
    import io
    reader = csv.DictReader(io.StringIO(_REAL_HEADER + "\n" + _REAL_ROW))
    row = provider._row_to_option_row(next(reader))

    assert row is not None
    assert row.tradingsymbol == "NIFTY26AUG24200PE"
    assert row.underlying == "NIFTY"
    assert row.exchange == "NFO"
    assert row.expiry == date(2026, 8, 25)
    assert row.strike == Decimal("24200.00")
    assert row.option_type == "PE"
    assert row.lot_size == 65
    assert row.close == Decimal("105.5")
    assert row.underlying_price == Decimal("24219.05")


def test_row_parser_returns_none_on_malformed_row():
    provider = NSEBhavcopyProvider()
    assert provider._row_to_option_row({"FinInstrmNm": "", "TckrSymb": ""}) is None


def test_as_instrument_row_is_consumable_by_resolve_option():
    row = HistoricalOptionRow(
        tradingsymbol="NIFTY26AUG24200PE", exchange="NFO", underlying="NIFTY",
        expiry=date(2026, 8, 25), strike=Decimal("24200"), option_type="PE",
        lot_size=65, close=Decimal("105.5"), underlying_price=Decimal("24219.05"),
    )
    instrument_row = row.as_instrument_row()
    resolved = resolve_option(
        [instrument_row], "NIFTY", "this_week", 0, "PE", Decimal("24219.05"),
        as_of=date(2026, 8, 24),
    )
    assert resolved.tradingsymbol == "NIFTY26AUG24200PE"
    assert resolved.lot_size == 65


def _warehouse(provider) -> OptionChainWarehouse:
    factory = get_session_factory()
    return OptionChainWarehouse(provider, OptionChainRepository(factory))


@pytest.mark.asyncio
async def test_second_request_for_same_day_makes_zero_provider_calls():
    await init_db()
    provider = _FakeBhavcopyProvider()
    warehouse = _warehouse(provider)

    first = await warehouse.get_chain("NIFTY", "NFO", date(2026, 8, 24))
    assert len(first) == 1
    assert len(provider.calls) == 1

    second = await warehouse.get_chain("NIFTY", "NFO", date(2026, 8, 24))
    assert second == first
    assert len(provider.calls) == 1  # cached -- no new fetch


@pytest.mark.asyncio
async def test_get_underlying_price_reads_undrlygpric():
    await init_db()
    warehouse = _warehouse(_FakeBhavcopyProvider())
    price = await warehouse.get_underlying_price("NIFTY", "NFO", date(2026, 8, 24))
    assert price == Decimal("24219.05")


@pytest.mark.asyncio
async def test_get_close_reads_the_contracts_own_close():
    await init_db()
    warehouse = _warehouse(_FakeBhavcopyProvider())
    price = await warehouse.get_close("NIFTY26AUG24200PE", "NFO", "NIFTY", date(2026, 8, 24))
    assert price == Decimal("105.5")


@pytest.mark.asyncio
async def test_a_different_underlying_on_an_already_fetched_day_is_free():
    """The whole-file-bulk lever: one fetch persists every underlying that
    day, so a second underlying's request on the same day costs nothing."""
    await init_db()

    class _MultiUnderlyingProvider:
        def __init__(self) -> None:
            self.calls: list[date] = []

        async def fetch_option_chain_for_day(self, day: date):
            self.calls.append(day)
            return [
                HistoricalOptionRow(
                    tradingsymbol="NIFTY26AUG24200PE", exchange="NFO", underlying="NIFTY",
                    expiry=date(2026, 8, 25), strike=Decimal("24200"), option_type="PE",
                    lot_size=65, close=Decimal("105.5"), underlying_price=Decimal("24219.05"),
                ),
                HistoricalOptionRow(
                    tradingsymbol="BANKNIFTY26AUG51000PE", exchange="NFO", underlying="BANKNIFTY",
                    expiry=date(2026, 8, 25), strike=Decimal("51000"), option_type="PE",
                    lot_size=30, close=Decimal("210.0"), underlying_price=Decimal("51042.10"),
                ),
            ]

    provider = _MultiUnderlyingProvider()
    warehouse = _warehouse(provider)
    day = date(2026, 8, 18)  # unique to this test -- avoids colliding with other tests' cached days

    await warehouse.get_chain("NIFTY", "NFO", day)
    assert len(provider.calls) == 1

    banknifty_chain = await warehouse.get_chain("BANKNIFTY", "NFO", day)
    assert len(banknifty_chain) == 1
    assert len(provider.calls) == 1  # still just the one whole-file fetch

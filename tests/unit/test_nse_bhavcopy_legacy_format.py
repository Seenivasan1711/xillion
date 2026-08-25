"""
NSE Bhavcopy's legacy (pre-2024) format fallback: the current "UDiFF" URL
genuinely 404s for any date before 2024-01-01 (confirmed by direct probing,
not assumed) -- a real 2-5yr backfill needs NSE's older archive format,
which has different columns and no ready-made tradingsymbol field. Verified
against a real downloaded file (2021-06-15) before writing this parser, not
guessed from search results -- see data_providers/nse_bhavcopy.py's module
docstring for the exact real column names and the two approximations
(underlying_price via nearest-future-close proxy, lot_size=0) the option-
chain path carries that the new-format path doesn't need.
"""
import io
import zipfile
from datetime import date
from decimal import Decimal

import httpx
import pytest

from data_providers.nse_bhavcopy import NSEBhavcopyProvider

_LEGACY_HEADER = (
    "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,"
    "SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP,\n"
)
_LEGACY_ROWS = [
    # Two BANKNIFTY futures (24-Jun nearest, 29-Jul further out) + one option.
    "FUTIDX,BANKNIFTY,24-Jun-2021,0,XX,35035,35425.95,34960.6,35330.4,35330.4,102335,902876.61,1488475,-31500,15-JUN-2021,\n",
    "FUTIDX,BANKNIFTY,29-Jul-2021,0,XX,35190,35548.95,35146.25,35458.4,35458.4,5718,50632.62,178750,11700,15-JUN-2021,\n",
    "OPTIDX,BANKNIFTY,17-Jun-2021,28100,CE,7163.95,7163.95,7120.85,7120.85,7153.4,2,17.62,875,0,15-JUN-2021,\n",
    "OPTIDX,BANKNIFTY,17-Jun-2021,28100,PE,10,12,8,9.5,9.5,5,1.0,100,0,15-JUN-2021,\n",
    # A different underlying -- must be excluded by underlying_filter.
    "FUTSTK,RELIANCE,24-Jun-2021,0,XX,2100,2150,2090,2130,2130,500,1000,20000,0,15-JUN-2021,\n",
]


def _legacy_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("fo15JUN2021bhav.csv", _LEGACY_HEADER + "".join(_LEGACY_ROWS))
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        pass


async def _fake_get_new_404_legacy_200(self, url):
    if "archives.nseindia.com/content/historical" in url:
        return _FakeResponse(_legacy_zip_bytes())
    return _FakeResponse(b"", status_code=404)


@pytest.mark.asyncio
async def test_bars_fall_back_to_legacy_format_on_a_new_format_404(monkeypatch):
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get_new_404_legacy_200)
    provider = NSEBhavcopyProvider()

    bars = await provider.fetch_all_bars_for_day(
        "NFO", "1d", date(2021, 6, 15), underlying_filter={"BANKNIFTY"},
    )

    symbols = {b.symbol for b in bars}
    assert symbols == {"BANKNIFTY24JUN21FUT", "BANKNIFTY29JUL21FUT", "BANKNIFTY17JUN2128100CE", "BANKNIFTY17JUN2128100PE"}
    assert "RELIANCE24JUN21FUT" not in symbols  # filtered out


@pytest.mark.asyncio
async def test_legacy_bar_values_are_parsed_correctly(monkeypatch):
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get_new_404_legacy_200)
    provider = NSEBhavcopyProvider()

    bars = await provider.fetch_all_bars_for_day("NFO", "1d", date(2021, 6, 15), underlying_filter={"BANKNIFTY"})
    fut = next(b for b in bars if b.symbol == "BANKNIFTY24JUN21FUT")

    assert fut.open == 35035
    assert fut.high == Decimal("35425.95")
    assert fut.low == Decimal("34960.6")
    assert fut.close == Decimal("35330.4")
    assert fut.volume == 102335  # CONTRACTS column, legacy's volume proxy


@pytest.mark.asyncio
async def test_option_chain_falls_back_to_legacy_and_approximates_spot_from_nearest_future(monkeypatch):
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get_new_404_legacy_200)
    provider = NSEBhavcopyProvider()

    chain = await provider.fetch_option_chain_for_day(date(2021, 6, 15))
    bnf_option = next(r for r in chain if r.tradingsymbol == "BANKNIFTY17JUN2128100CE")

    assert bnf_option.underlying == "BANKNIFTY"
    assert bnf_option.strike == 28100
    assert bnf_option.option_type == "CE"
    assert bnf_option.close == Decimal("7120.85")
    # Spot proxy: nearest-expiry future (24-Jun, not 29-Jul) close, not NSE's
    # own recorded value (legacy file has none) -- see the module docstring.
    assert bnf_option.underlying_price == Decimal("35330.4")
    # No lot-size source pre-2024 -- deliberately 0, not guessed.
    assert bnf_option.lot_size == 0


@pytest.mark.asyncio
async def test_legacy_futures_row_has_no_strike_or_option_type(monkeypatch):
    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get_new_404_legacy_200)
    provider = NSEBhavcopyProvider()

    chain = await provider.fetch_option_chain_for_day(date(2021, 6, 15))
    fut = next(r for r in chain if r.tradingsymbol == "BANKNIFTY24JUN21FUT")

    assert fut.strike is None
    assert fut.option_type is None


@pytest.mark.asyncio
async def test_a_genuine_holiday_returns_empty_even_after_legacy_fallback(monkeypatch):
    """Both the new AND legacy URLs 404 for a real holiday -- must not
    fabricate data, and must not raise."""
    async def _both_404(self, url):
        return _FakeResponse(b"", status_code=404)

    monkeypatch.setattr(httpx.AsyncClient, "get", _both_404)
    provider = NSEBhavcopyProvider()

    bars = await provider.fetch_all_bars_for_day("NFO", "1d", date(2021, 6, 16))
    chain = await provider.fetch_option_chain_for_day(date(2021, 6, 16))

    assert bars == []
    assert chain == []


def test_legacy_tradingsymbol_rejects_a_malformed_row():
    assert NSEBhavcopyProvider._legacy_tradingsymbol_from_row({"INSTRUMENT": "FUTIDX", "SYMBOL": "", "EXPIRY_DT": "24-Jun-2021"}) is None
    assert NSEBhavcopyProvider._legacy_tradingsymbol_from_row({"INSTRUMENT": "EQ", "SYMBOL": "RELIANCE", "EXPIRY_DT": "24-Jun-2021"}) is None
    assert NSEBhavcopyProvider._legacy_tradingsymbol_from_row({"INSTRUMENT": "OPTIDX", "SYMBOL": "NIFTY", "EXPIRY_DT": "not-a-date", "STRIKE_PR": "15000", "OPTION_TYP": "CE"}) is None

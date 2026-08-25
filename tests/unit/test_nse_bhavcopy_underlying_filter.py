"""
underlying_filter on NSEBhavcopyProvider.fetch_all_bars_for_day: a real
multi-year whole-market NFO backfill is ~85M+ rows (every contract, every
trading day) -- far past what a free-tier Postgres instance can hold. This
lets a caller (scripts/backfill.py's --underlying-filter) keep only the
underlyings a strategy actually trades (e.g. NIFTY, BANKNIFTY) while still
downloading the same whole-day file (NSE doesn't offer a narrower one).
"""
import io
import zipfile
from datetime import date

import httpx
import pytest

from data_providers.nse_bhavcopy import NSEBhavcopyProvider

_CSV_HEADER = "TckrSymb,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol\n"
_ROWS = [
    "NIFTY,NIFTY26AUG24000CE,100,110,90,105,1000\n",
    "BANKNIFTY,BANKNIFTY26AUG50000CE,200,210,190,205,2000\n",
    "RELIANCE,RELIANCE26AUGFUT,300,310,290,305,3000\n",
]


def _fake_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("BhavCopy.csv", _CSV_HEADER + "".join(_ROWS))
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content
        self.status_code = 200

    def raise_for_status(self):
        pass


@pytest.mark.asyncio
async def test_underlying_filter_keeps_only_matching_contracts(monkeypatch):
    provider = NSEBhavcopyProvider()

    async def _fake_get(self, url):
        return _FakeResponse(_fake_zip_bytes())

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    bars = await provider.fetch_all_bars_for_day(
        "NFO", "1d", date(2026, 8, 24), underlying_filter={"NIFTY", "BANKNIFTY"},
    )

    symbols = {b.symbol for b in bars}
    assert symbols == {"NIFTY26AUG24000CE", "BANKNIFTY26AUG50000CE"}
    assert "RELIANCE26AUGFUT" not in symbols


@pytest.mark.asyncio
async def test_no_filter_keeps_everything_unfiltered_shape_unchanged(monkeypatch):
    provider = NSEBhavcopyProvider()

    async def _fake_get(self, url):
        return _FakeResponse(_fake_zip_bytes())

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    bars = await provider.fetch_all_bars_for_day("NFO", "1d", date(2026, 8, 24))

    symbols = {b.symbol for b in bars}
    assert symbols == {"NIFTY26AUG24000CE", "BANKNIFTY26AUG50000CE", "RELIANCE26AUGFUT"}

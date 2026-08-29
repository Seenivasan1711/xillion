"""
AlphaVantageFXProvider (Gold Lane B1's backup backtest data source,
2026-08-29, for when the MT5 bridge isn't reachable). Response shapes here
match the FX_DAILY parameter names verified live against Alpha Vantage's
real API (accepted from_symbol=XAU/to_symbol=USD, just gated on a real key)
and the numbered-field convention ("1. open" etc) confirmed against
TIME_SERIES_DAILY's own live demo response -- see the module's own
docstring for the honest caveat about what wasn't independently confirmed
(the exact FX-specific top-level key name, and volume-field presence). No
network calls here -- httpx is stubbed.
"""

from datetime import date

import httpx
import pytest

from data_providers.alpha_vantage_fx import AlphaVantageFXProvider


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _stub_get(payload: dict, monkeypatch, captured: dict | None = None):
    async def _fake_get(self, url, params=None):
        if captured is not None:
            captured.update(params or {})
        return _FakeResponse(payload)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)


@pytest.mark.asyncio
async def test_fetch_bars_parses_the_documented_fx_time_series_key(monkeypatch):
    _stub_get(
        {
            "Time Series FX (Daily)": {
                "2026-01-02": {
                    "1. open": "2000.0",
                    "2. high": "2010.0",
                    "3. low": "1990.0",
                    "4. close": "2005.0",
                },
                "2026-01-03": {
                    "1. open": "2005.0",
                    "2. high": "2020.0",
                    "3. low": "2000.0",
                    "4. close": "2015.0",
                },
            }
        },
        monkeypatch,
    )
    provider = AlphaVantageFXProvider()

    bars = await provider.fetch_bars(
        "XAUUSD", "MT5", "1d", date(2026, 1, 1), date(2026, 1, 31), credentials={"api_key": "k"}
    )

    assert len(bars) == 2
    assert str(bars[0].close) == "2005.0"
    assert bars[0].volume == 0  # FX has no volume field -- must not crash, default to 0
    assert bars[0].ts < bars[1].ts  # sorted ascending


@pytest.mark.asyncio
async def test_fetch_bars_falls_back_to_the_equity_style_key_defensively(monkeypatch):
    """Honest-uncertainty parsing (see module docstring) -- if Alpha
    Vantage's real FX key differs from what's documented, this must not
    silently return zero bars."""
    _stub_get(
        {
            "Time Series (Daily)": {
                "2026-01-02": {
                    "1. open": "2000.0",
                    "2. high": "2010.0",
                    "3. low": "1990.0",
                    "4. close": "2005.0",
                },
            }
        },
        monkeypatch,
    )
    provider = AlphaVantageFXProvider()

    bars = await provider.fetch_bars(
        "XAUUSD", "MT5", "1d", date(2026, 1, 1), date(2026, 1, 31), credentials={"api_key": "k"}
    )

    assert len(bars) == 1


@pytest.mark.asyncio
async def test_fetch_bars_filters_to_the_requested_date_range(monkeypatch):
    _stub_get(
        {
            "Time Series FX (Daily)": {
                "2025-12-31": {"1. open": "1", "2. high": "1", "3. low": "1", "4. close": "1"},
                "2026-01-15": {"1. open": "2", "2. high": "2", "3. low": "2", "4. close": "2"},
                "2026-02-01": {"1. open": "3", "2. high": "3", "3. low": "3", "4. close": "3"},
            }
        },
        monkeypatch,
    )
    provider = AlphaVantageFXProvider()

    bars = await provider.fetch_bars(
        "XAUUSD", "MT5", "1d", date(2026, 1, 1), date(2026, 1, 31), credentials={"api_key": "k"}
    )

    assert len(bars) == 1
    assert str(bars[0].close) == "2"


@pytest.mark.asyncio
async def test_fetch_bars_splits_symbol_into_from_and_to_symbol(monkeypatch):
    captured: dict = {}
    _stub_get({"Time Series FX (Daily)": {}}, monkeypatch, captured)
    provider = AlphaVantageFXProvider()

    await provider.fetch_bars(
        "XAUUSD", "MT5", "1d", date(2026, 1, 1), date(2026, 1, 31), credentials={"api_key": "k"}
    )

    assert captured["from_symbol"] == "XAU"
    assert captured["to_symbol"] == "USD"
    assert captured["function"] == "FX_DAILY"


@pytest.mark.asyncio
async def test_fetch_bars_raises_clearly_on_rate_limit_note(monkeypatch):
    """Alpha Vantage returns HTTP 200 with a "Note" key for a rate-limit
    hit, not an HTTP error status -- must not be silently treated as
    "zero bars available for this range"."""
    _stub_get({"Note": "Thank you for using Alpha Vantage! ... call frequency ..."}, monkeypatch)
    provider = AlphaVantageFXProvider()

    with pytest.raises(RuntimeError, match="did not return data"):
        await provider.fetch_bars(
            "XAUUSD", "MT5", "1d", date(2026, 1, 1), date(2026, 1, 31), credentials={"api_key": "k"}
        )


@pytest.mark.asyncio
async def test_fetch_bars_rejects_intraday_timeframes():
    provider = AlphaVantageFXProvider()
    with pytest.raises(ValueError, match="daily"):
        await provider.fetch_bars(
            "XAUUSD", "MT5", "5m", date(2026, 1, 1), date(2026, 1, 31), credentials={"api_key": "k"}
        )


@pytest.mark.asyncio
async def test_fetch_bars_requires_an_api_key():
    provider = AlphaVantageFXProvider()
    with pytest.raises(ValueError, match="API key"):
        await provider.fetch_bars(
            "XAUUSD", "MT5", "1d", date(2026, 1, 1), date(2026, 1, 31), credentials=None
        )


@pytest.mark.asyncio
async def test_fetch_bars_requires_a_six_character_symbol():
    provider = AlphaVantageFXProvider()
    with pytest.raises(ValueError, match="6-character"):
        await provider.fetch_bars(
            "GOLD", "MT5", "1d", date(2026, 1, 1), date(2026, 1, 31), credentials={"api_key": "k"}
        )

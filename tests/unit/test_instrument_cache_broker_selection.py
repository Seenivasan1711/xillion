"""
xillion.main's daily instrument-cache refresh (and the new manual
POST /brokers/refresh-instruments endpoint) used to be hardcoded to
"Zerodha Primary" only. A Dhan-only setup (no Zerodha connected at all)
silently never populated the `instrument` table -- resolve_strike() reads
it, so a Dhan-only paper/live instance could start and run but could never
actually resolve an option strike to trade. Found 2026-08-26 while a real
Dhan-only paper instance sat at 0 trades with no error surfaced anywhere.
"""
from fastapi import FastAPI

from xillion.main import _select_instrument_cache_broker


def _app_with(instances: dict) -> FastAPI:
    app = FastAPI()
    app.state.broker_instances = instances
    return app


def test_prefers_zerodha_when_both_connected():
    zerodha = object()
    dhan = object()
    app = _app_with({
        "Zerodha Primary": {"instance": zerodha},
        "Dhan Primary": {"instance": dhan},
    })

    broker, source = _select_instrument_cache_broker(app)

    assert broker is zerodha
    assert source == "Zerodha Primary"


def test_falls_back_to_dhan_when_zerodha_not_connected():
    dhan = object()
    app = _app_with({"Dhan Primary": {"instance": dhan}})

    broker, source = _select_instrument_cache_broker(app)

    assert broker is dhan
    assert source == "Dhan Primary"


def test_returns_none_when_nothing_connected():
    app = _app_with({})

    broker, source = _select_instrument_cache_broker(app)

    assert broker is None
    assert source is None


def test_ignores_a_present_but_disconnected_entry():
    # broker_instances can hold a name with instance=None (connect attempt
    # failed but the entry was still recorded) -- must not treat that as
    # "connected" just because the key exists.
    dhan = object()
    app = _app_with({
        "Zerodha Primary": {"instance": None, "status": "error"},
        "Dhan Primary": {"instance": dhan},
    })

    broker, source = _select_instrument_cache_broker(app)

    assert broker is dhan
    assert source == "Dhan Primary"

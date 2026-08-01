"""
Integration test: options StrategyContext extensions (Phase 3) --
resolve_strike/get_spot/get_option_price/subscribe_instrument -- against a
stub broker and a pre-populated instrument cache. No FastAPI, no alert mode,
no market hours involved.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from brokers._dummy import DummyBroker
from xillion.core.instrument_cache import refresh_instrument_cache
from xillion.core.instruments import InstrumentRow
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy, StrategyContext
from xillion.data.bus import MarketDataBus
from xillion.db.session import get_session_factory, init_db
from xillion.engine.strategy_engine import StrategyEngine


class _FakeInstrumentBroker(DummyBroker):
    """DummyBroker plus a fetch_instrument_dump, for cache-refresh testing."""

    def __init__(self, rows: list[InstrumentRow], **kw) -> None:
        super().__init__(**kw)
        self._rows = rows

    async def fetch_instrument_dump(self, exchanges=None) -> list[InstrumentRow]:
        return self._rows


class _OptionsProbeStrategy(Strategy):
    name = "Options Probe"
    version = "1.0.0"
    instruments = ["NIFTY 50"]
    timeframe = "1m"

    async def on_start(self, ctx: StrategyContext) -> None:
        resolved = await ctx.resolve_strike("NIFTY", "this_week", 0, "CE")
        ctx.state["resolved"] = resolved
        await ctx.subscribe_instrument(resolved.tradingsymbol, resolved.exchange)
        ctx.state["option_price"] = await ctx.get_option_price(resolved.tradingsymbol, resolved.exchange)


def _row(token: int, tradingsymbol: str, strike: Decimal, expiry: date) -> InstrumentRow:
    return InstrumentRow(
        instrument_token=token, exchange="NFO", tradingsymbol=tradingsymbol, name="NIFTY",
        expiry=expiry, strike=strike, option_type="CE", segment="NFO-OPT",
        lot_size=25, tick_size=Decimal("0.05"),
    )


@pytest.mark.asyncio
async def test_resolve_strike_and_subscribe_instrument():
    await init_db()

    # Relative to today (not a fixed calendar date) so this fixture can't go
    # stale: resolve_option() correctly refuses to resolve an already-expired
    # contract (real trading-safety behavior), so a hardcoded past date would
    # make this test fail for a reason that has nothing to do with the code
    # under test. 2 days out keeps it comfortably inside the "this_week"
    # weekly-expiry window (_WEEKLY_MAX_DAYS_OUT = 10 in xillion/core/instruments.py).
    expiry = date.today() + timedelta(days=2)
    rows = [
        _row(1001, "NIFTY26JUL2924950CE", Decimal(24950), expiry),
        _row(1002, "NIFTY26JUL2925000CE", Decimal(25000), expiry),
        _row(1003, "NIFTY26JUL2925050CE", Decimal(25050), expiry),
    ]
    broker = _FakeInstrumentBroker(rows, default_fill_price=Decimal("25010"))
    await refresh_instrument_cache(broker, get_session_factory)

    registry = PluginRegistry()
    registry.strategies["Options Probe"] = _OptionsProbeStrategy

    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)

    runner = await engine.spawn(
        instance_id="test-options-probe",
        strategy_name="Options Probe",
        broker=broker,
        instruments=["NIFTY 50"],
        timeframe="1m",
        capital=Decimal("100000"),
        params={},
        mode="alert",
    )

    ctx = runner._ctx
    resolved = ctx.state["resolved"]
    assert resolved.strike == Decimal(25000)  # nearest to spot 25010
    assert resolved.tradingsymbol == "NIFTY26JUL2925000CE"
    assert resolved.exchange == "NFO"
    assert ctx.state["option_price"] == Decimal("25010")

    # subscribe_instrument wired the resolved symbol into the runner's dynamic set,
    # and asked the broker to subscribe to it too.
    assert resolved.tradingsymbol in runner._dynamic_instruments
    assert any(call == "subscribe_ticks" for call, _ in broker.calls)

    await engine.stop_instance("test-options-probe")
    assert runner._dynamic_instruments == []

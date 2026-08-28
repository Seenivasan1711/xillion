"""
DhanBroker.place_protective_gtt/cancel_gtt (2026-08-29, Rakesh's decision to
switch Dhan's product type from INTRADAY to MARGIN): Forever Orders are
Dhan's GTT equivalent. Request/response shapes here match DhanHQ's real docs
(dhanhq.co/docs/v2/forever/) and the installed dhanhq SDK's own
place_forever() signature, not guessed. No network calls -- the dhanhq
facade is stubbed.

Honest caveat repeated from brokers/dhan.py's own module docstring: Dhan's
Forever Order docs restrict productType to CNC/MTF specifically, not MARGIN
(the product type place_order() actually uses everywhere else) -- these
tests prove the REQUEST is built correctly per that documentation, not that
Dhan's server will actually accept it for an F&O leg carried under MARGIN.
That can only be confirmed against a real account.
"""

from decimal import Decimal

import pytest

from brokers.dhan import DhanBroker
from xillion.core.dhan_instruments import ResolvedSecurity
from xillion.core.events import Side


class _StubDhan:
    def __init__(self, forever_response=None, positions_response=None):
        self.place_forever_calls: list[dict] = []
        self.cancel_forever_calls: list = []
        self._response = forever_response if forever_response is not None else {"orderId": "F-123"}
        self._positions_response = positions_response if positions_response is not None else []

    def place_forever(self, **kwargs):
        self.place_forever_calls.append(kwargs)
        return self._response

    def cancel_forever(self, order_id):
        self.cancel_forever_calls.append(order_id)
        return {"orderId": order_id, "orderStatus": "CANCELLED"}

    def get_positions(self):
        return self._positions_response


def _resolved(**overrides):
    defaults = dict(
        security_id="99999",
        exchange_segment="NSE_FNO",
        instrument="OPTIDX",
        lot_size=65,
        tick_size="0.05",
    )
    defaults.update(overrides)
    return ResolvedSecurity(**defaults)


def _broker(stub: _StubDhan, monkeypatch) -> DhanBroker:
    b = DhanBroker()
    b._dhan = stub

    async def _fake_resolve(symbol):
        return _resolved()

    monkeypatch.setattr(b, "_resolve", _fake_resolve)
    return b


def test_capabilities_declare_gtt_support():
    assert DhanBroker.capabilities.supports_gtt_orders is True


def test_product_type_is_margin_not_intraday():
    """The whole reason this method exists at all -- Dhan's Forever Order
    endpoint rejects INTRADAY outright, and the strategies this codebase
    trades hold positions across days until expiry."""
    from brokers.dhan import _PRODUCT_TYPE

    assert _PRODUCT_TYPE == "MARGIN"


@pytest.mark.asyncio
async def test_stop_only_places_a_single_flag_forever_order(monkeypatch):
    stub = _StubDhan()
    broker = _broker(stub, monkeypatch)

    order_id = await broker.place_protective_gtt(
        symbol="NIFTY26AUG24000CE",
        exchange="NFO",
        side=Side.BUY,
        quantity=65,
        stop_price=Decimal("120.5"),
        target_price=None,
        last_price=Decimal("90"),
    )

    assert order_id == "F-123"
    assert len(stub.place_forever_calls) == 1
    call = stub.place_forever_calls[0]
    assert call["security_id"] == "99999"
    assert call["exchange_segment"] == "NSE_FNO"
    assert call["transaction_type"] == "BUY"
    assert call["product_type"] == "MARGIN"
    assert call["order_flag"] == "SINGLE"
    assert call["price"] == 120.5
    assert call["trigger_Price"] == 120.5
    assert call["quantity"] == 65
    # No target leg on a stop-only GTT.
    assert call["price1"] == 0
    assert call["trigger_Price1"] == 0
    assert call["quantity1"] == 0


@pytest.mark.asyncio
async def test_stop_and_target_place_an_oco_forever_order(monkeypatch):
    """price/triggerPrice are the STOP_LOSS_LEG, price1/triggerPrice1 are
    the TARGET_LEG -- per Dhan's own field docs ("Target price for OCO
    order" on price1 specifically)."""
    stub = _StubDhan()
    broker = _broker(stub, monkeypatch)

    await broker.place_protective_gtt(
        symbol="NIFTY26AUG24000CE",
        exchange="NFO",
        side=Side.BUY,
        quantity=65,
        stop_price=Decimal("120.5"),
        target_price=Decimal("40.0"),
        last_price=Decimal("90"),
    )

    call = stub.place_forever_calls[0]
    assert call["order_flag"] == "OCO"
    assert call["price"] == 120.5
    assert call["trigger_Price"] == 120.5
    assert call["price1"] == 40.0
    assert call["trigger_Price1"] == 40.0
    assert call["quantity1"] == 65


@pytest.mark.asyncio
async def test_place_protective_gtt_raises_on_failure_envelope(monkeypatch):
    stub = _StubDhan(forever_response={"status": "failure", "remarks": "Invalid productType"})
    broker = _broker(stub, monkeypatch)

    with pytest.raises(RuntimeError, match="Invalid productType"):
        await broker.place_protective_gtt(
            symbol="X",
            exchange="NFO",
            side=Side.BUY,
            quantity=1,
            stop_price=Decimal("10"),
            target_price=None,
            last_price=Decimal("9"),
        )


@pytest.mark.asyncio
async def test_cancel_gtt_calls_cancel_forever_with_the_order_id(monkeypatch):
    stub = _StubDhan()
    broker = _broker(stub, monkeypatch)

    await broker.cancel_gtt("F-123")

    assert stub.cancel_forever_calls == ["F-123"]


@pytest.mark.asyncio
async def test_cancel_gtt_swallows_errors_rather_than_raising(monkeypatch):
    """Same precedent as X02/M01's own alert-must-never-break-the-caller
    stance -- a cancel failure here shouldn't crash the strategy's exit
    path, just log it."""
    stub = _StubDhan()

    def _raise(order_id):
        raise RuntimeError("network blip")

    stub.cancel_forever = _raise
    broker = _broker(stub, monkeypatch)

    await broker.cancel_gtt("F-123")  # must not raise


# ── get_realised_pnl_today (M01 funds-reconciliation follow-up, 2026-08-29) ─


def test_capabilities_declare_realised_pnl_support():
    assert DhanBroker.capabilities.supports_realised_pnl_query is True


@pytest.mark.asyncio
async def test_realised_pnl_sums_realized_profit_across_all_positions(monkeypatch):
    """Includes CLOSED rows (Dhan's docs show a positionType: "CLOSED"
    value) -- not just the currently-open ones get_positions() itself
    keeps, which drops a position's row (and its booked P&L) the moment
    it's fully closed."""
    stub = _StubDhan(
        positions_response=[
            {"netQty": 0, "positionType": "CLOSED", "realizedProfit": 500.0},
            {"netQty": 65, "positionType": "OPEN", "realizedProfit": -50.0},
        ]
    )
    broker = _broker(stub, monkeypatch)

    result = await broker.get_realised_pnl_today()

    assert result == Decimal("450.0")


@pytest.mark.asyncio
async def test_realised_pnl_is_zero_when_no_positions(monkeypatch):
    stub = _StubDhan(positions_response=[])
    broker = _broker(stub, monkeypatch)

    result = await broker.get_realised_pnl_today()

    assert result == Decimal("0")


@pytest.mark.asyncio
async def test_realised_pnl_unwraps_the_data_envelope(monkeypatch):
    """Dhan's SDK sometimes wraps list responses as {"data": [...]}, same
    envelope get_positions() itself already unwraps."""
    stub = _StubDhan(positions_response={"data": [{"realizedProfit": 200.0}]})
    broker = _broker(stub, monkeypatch)

    result = await broker.get_realised_pnl_today()

    assert result == Decimal("200.0")

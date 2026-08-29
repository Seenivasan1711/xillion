"""
ZerodhaBroker.place_protective_gtt/cancel_gtt (CP11 follow-up): Kite Connect
discontinued bracket orders entirely (verified against the current API docs
-- "bo" is not a valid `variety` any more), so GTT is the real broker-native
protective mechanism, not the old supports_bracket_orders flag's claim.
Request/response shapes here match kiteconnect.KiteConnect's actual
installed SDK source (place_gtt/_get_gtt_payload), not guessed. No network
calls -- the KiteConnect client is stubbed.
"""

from decimal import Decimal

import pytest

from brokers.zerodha import ZerodhaBroker
from xillion.core.events import Side


class _StubKite:
    PRODUCT_MIS = "MIS"
    PRODUCT_NRML = "NRML"
    GTT_TYPE_SINGLE = "single"
    GTT_TYPE_OCO = "two-leg"

    def __init__(self, gtt_response=None, positions_response=None):
        self.place_gtt_calls: list[dict] = []
        self.delete_gtt_calls: list = []
        self._gtt_response = gtt_response if gtt_response is not None else {"trigger_id": 123}
        self._positions_response = positions_response if positions_response is not None else {}

    def place_gtt(self, **kwargs):
        self.place_gtt_calls.append(kwargs)
        return self._gtt_response

    def delete_gtt(self, trigger_id):
        self.delete_gtt_calls.append(trigger_id)

    def positions(self):
        return self._positions_response


def _broker(stub: _StubKite, product_type: str | None = None) -> ZerodhaBroker:
    b = ZerodhaBroker()
    b._kite = stub
    if product_type is not None:
        b._credentials = {"product_type": product_type}
    return b


def test_capabilities_reflect_real_kite_connect_not_the_old_bo_flag():
    """bo (bracket orders) is genuinely gone from Kite Connect -- this flag
    must not claim otherwise. GTT is the real replacement."""
    assert ZerodhaBroker.capabilities.supports_bracket_orders is False
    assert ZerodhaBroker.capabilities.supports_gtt_orders is True


@pytest.mark.asyncio
async def test_stop_only_places_a_single_type_gtt():
    stub = _StubKite()
    broker = _broker(stub)

    trigger_id = await broker.place_protective_gtt(
        symbol="NIFTY26AUG24000CE",
        exchange="NFO",
        side=Side.BUY,
        quantity=65,
        stop_price=Decimal("120.5"),
        target_price=None,
        last_price=Decimal("90"),
    )

    assert trigger_id == "123"
    assert len(stub.place_gtt_calls) == 1
    call = stub.place_gtt_calls[0]
    assert call["trigger_type"] == "single"
    assert call["trigger_values"] == [120.5]
    assert len(call["orders"]) == 1
    assert call["orders"][0] == {
        "transaction_type": "BUY",
        "quantity": 65,
        "order_type": "LIMIT",
        "product": "MIS",
        "price": 120.5,
    }
    assert call["last_price"] == 90.0


@pytest.mark.asyncio
async def test_stop_and_target_place_a_two_leg_oco_gtt_in_stop_then_target_order():
    stub = _StubKite()
    broker = _broker(stub)

    await broker.place_protective_gtt(
        symbol="NIFTY26AUG24000CE",
        exchange="NFO",
        side=Side.BUY,
        quantity=65,
        stop_price=Decimal("120.5"),
        target_price=Decimal("40.0"),
        last_price=Decimal("90"),
    )

    call = stub.place_gtt_calls[0]
    assert call["trigger_type"] == "two-leg"
    assert call["trigger_values"] == [120.5, 40.0]
    assert [o["price"] for o in call["orders"]] == [120.5, 40.0]
    assert all(o["product"] == "MIS" for o in call["orders"])


@pytest.mark.asyncio
async def test_place_protective_gtt_accepts_a_bare_id_response_too():
    """Real docs show {"trigger_id": N}, but response-shape ambiguity is
    treated defensively here the same way this codebase treats it
    elsewhere (e.g. Dhan's login token key handling) -- a bare id must not
    crash this."""
    stub = _StubKite(gtt_response=456)
    broker = _broker(stub)

    trigger_id = await broker.place_protective_gtt(
        symbol="X",
        exchange="NFO",
        side=Side.BUY,
        quantity=1,
        stop_price=Decimal("10"),
        target_price=None,
        last_price=Decimal("9"),
    )
    assert trigger_id == "456"


@pytest.mark.asyncio
async def test_cancel_gtt_calls_delete_gtt_with_the_trigger_id():
    stub = _StubKite()
    broker = _broker(stub)

    await broker.cancel_gtt("123")

    assert stub.delete_gtt_calls == ["123"]


# ── get_realised_pnl_today (M01 funds-reconciliation follow-up, 2026-08-29) ─


def test_capabilities_declare_realised_pnl_support():
    assert ZerodhaBroker.capabilities.supports_realised_pnl_query is True


@pytest.mark.asyncio
async def test_realised_pnl_sums_the_day_array_not_net():
    """Kite's own docs describe "day" specifically as the array for
    computing intraday P&L -- "net" mixes in carried-forward multi-day
    positions' historical realised total, not just today's activity."""
    stub = _StubKite(
        positions_response={
            "day": [{"realised": 120.5}, {"realised": -20.0}],
            "net": [{"realised": 9999.0}],
        }
    )
    broker = _broker(stub)

    result = await broker.get_realised_pnl_today()

    assert result == Decimal("100.5")


@pytest.mark.asyncio
async def test_realised_pnl_is_zero_when_day_array_is_empty():
    stub = _StubKite(positions_response={"day": [], "net": []})
    broker = _broker(stub)

    result = await broker.get_realised_pnl_today()

    assert result == Decimal("0")


# ── Product type, UI-configurable per connection (2026-08-29) ───────────────


def test_product_type_defaults_to_mis_when_unconfigured():
    broker = _broker(_StubKite())
    assert broker._product_type() == "MIS"


def test_product_type_is_configurable_to_nrml():
    broker = _broker(_StubKite(), product_type="NRML")
    assert broker._product_type() == "NRML"


def test_product_type_falls_back_to_mis_on_an_invalid_value():
    """A stale/bad DB value must not silently place NRML- or MIS-neither
    orders -- fall back to the safe, original default rather than passing
    garbage through to Kite."""
    broker = _broker(_StubKite(), product_type="NOT_A_REAL_PRODUCT")
    assert broker._product_type() == "MIS"


@pytest.mark.asyncio
async def test_gtt_uses_nrml_product_when_the_connection_is_configured_for_it():
    stub = _StubKite()
    broker = _broker(stub, product_type="NRML")

    await broker.place_protective_gtt(
        symbol="NIFTY26AUG24000CE",
        exchange="NFO",
        side=Side.BUY,
        quantity=65,
        stop_price=Decimal("120.5"),
        target_price=None,
        last_price=Decimal("90"),
    )

    assert stub.place_gtt_calls[0]["orders"][0]["product"] == "NRML"

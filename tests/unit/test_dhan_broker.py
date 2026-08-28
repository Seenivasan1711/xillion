"""
DhanBroker (CP15) -- order placement/status mapping and response-envelope
handling, mocking the dhanhq SDK facade directly since there are no real
Dhan credentials in this environment (same "structurally correct,
unverified end-to-end" position as data_providers/dhanhq.py). Request/
response shapes here are copied from DhanHQ's real docs
(dhanhq.co/docs/v2/orders/), not guessed.
"""

from decimal import Decimal

import pytest

from brokers.dhan import DhanBroker
from xillion.core.dhan_instruments import ResolvedSecurity
from xillion.core.events import OrderRequest, OrderStatus, OrderType, Side


def _broker() -> DhanBroker:
    b = DhanBroker()
    b._dhan = object()  # replaced per-test by monkeypatching specific methods
    b._client_id = "1000000003"
    return b


def _resolved(**overrides):
    defaults = dict(
        security_id="11536",
        exchange_segment="NSE_EQ",
        instrument="EQUITY",
        lot_size=1,
        tick_size="0.05",
    )
    defaults.update(overrides)
    return ResolvedSecurity(**defaults)


# ── Status / order-type mapping completeness ────────────────────────────────


def test_status_map_covers_every_documented_dhan_status():
    # From dhanhq.co/docs/v2/orders/ Order Book response enum, verbatim.
    documented = {"TRANSIT", "PENDING", "REJECTED", "CANCELLED", "PART_TRADED", "TRADED", "EXPIRED"}
    assert documented.issubset(DhanBroker._STATUS_MAP.keys())


def test_status_map_values_are_valid_orderstatus_members():
    for status in DhanBroker._STATUS_MAP.values():
        assert isinstance(status, OrderStatus)


def test_order_type_map_covers_every_xillion_order_type():
    for ot in OrderType:
        assert ot in DhanBroker._ORDER_TYPE_MAP


# ── place_order: success envelope ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_place_order_success_maps_response_fields(monkeypatch):
    broker = _broker()

    async def _fake_resolve(symbol):
        return _resolved()

    monkeypatch.setattr(broker, "_resolve", _fake_resolve)
    monkeypatch.setattr(
        broker,
        "_dhan",
        type(
            "F",
            (),
            {
                "place_order": staticmethod(
                    lambda **kw: {"orderId": "112111182198", "orderStatus": "PENDING"}
                )
            },
        )(),
    )

    request = OrderRequest(
        symbol="RELIANCE", side=Side.BUY, quantity=5, order_type=OrderType.MARKET
    )
    order = await broker.place_order(request)

    assert order.broker_order_id == "112111182198"
    assert order.status == OrderStatus.ACCEPTED
    assert order.symbol == "RELIANCE"
    assert order.side == Side.BUY


@pytest.mark.asyncio
async def test_place_order_passes_correct_fields_to_the_sdk(monkeypatch):
    broker = _broker()

    async def _fake_resolve(symbol):
        return _resolved(security_id="99999", exchange_segment="NSE_FNO")

    monkeypatch.setattr(broker, "_resolve", _fake_resolve)
    captured = {}

    def fake_place_order(**kw):
        captured.update(kw)
        return {"orderId": "1", "orderStatus": "TRANSIT"}

    monkeypatch.setattr(
        broker, "_dhan", type("F", (), {"place_order": staticmethod(fake_place_order)})()
    )

    request = OrderRequest(
        symbol="NIFTY26AUG24000CE",
        side=Side.SELL,
        quantity=65,
        order_type=OrderType.LIMIT,
        price=Decimal("45.5"),
        tag="my_tag",
    )
    await broker.place_order(request)

    assert captured["security_id"] == "99999"
    assert captured["exchange_segment"] == "NSE_FNO"
    assert captured["transaction_type"] == "SELL"
    assert captured["order_type"] == "LIMIT"
    # MARGIN, not INTRADAY -- 2026-08-29, Rakesh's decision: the credit
    # spread/iron condor strategies hold positions across days until
    # expiry, which INTRADAY would auto-square-off same-day at Dhan.
    assert captured["product_type"] == "MARGIN"
    assert captured["price"] == 45.5
    assert captured["tag"] == "my_tag"


# ── place_order: failure envelope ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_place_order_failure_is_rejected_not_raised(monkeypatch):
    broker = _broker()

    async def _fake_resolve(symbol):
        return _resolved()

    monkeypatch.setattr(broker, "_resolve", _fake_resolve)
    monkeypatch.setattr(
        broker,
        "_dhan",
        type(
            "F",
            (),
            {
                "place_order": staticmethod(
                    lambda **kw: {
                        "status": "failure",
                        "remarks": "Insufficient balance",
                        "data": "",
                    }
                )
            },
        )(),
    )

    request = OrderRequest(
        symbol="RELIANCE", side=Side.BUY, quantity=5, order_type=OrderType.MARKET
    )
    order = await broker.place_order(request)

    assert order.status == OrderStatus.REJECTED
    assert "Insufficient balance" in order.rejection_reason


# ── _dhan_to_order (order book row parsing) ─────────────────────────────────


def test_dhan_to_order_parses_a_real_order_book_row():
    # Verbatim shape from dhanhq.co/docs/v2/orders/ Order Book response.
    row = {
        "dhanClientId": "1000000003",
        "orderId": "112111182198",
        "correlationId": "123abc678",
        "orderStatus": "TRADED",
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "productType": "INTRADAY",
        "orderType": "MARKET",
        "validity": "DAY",
        "tradingSymbol": "RELIANCE",
        "securityId": "11536",
        "quantity": 5,
        "disclosedQuantity": 0,
        "price": 0.0,
        "triggerPrice": 0.0,
        "filledQty": 5,
        "averageTradedPrice": 2456.75,
    }
    broker = _broker()
    order = broker._dhan_to_order(row)

    assert order.broker_order_id == "112111182198"
    assert order.client_order_id == "123abc678"
    assert order.symbol == "RELIANCE"
    assert order.side == Side.BUY
    assert order.quantity == 5
    assert order.filled_quantity == 5
    assert order.status == OrderStatus.FILLED
    assert order.avg_fill_price == Decimal("2456.75")


def test_dhan_to_order_sell_side():
    row = {
        "orderId": "1",
        "transactionType": "SELL",
        "orderStatus": "PENDING",
        "tradingSymbol": "X",
        "quantity": 1,
    }
    order = _broker()._dhan_to_order(row)
    assert order.side == Side.SELL
    assert order.status == OrderStatus.ACCEPTED


def test_dhan_to_order_falls_back_to_order_id_with_no_correlation_id():
    row = {
        "orderId": "555",
        "transactionType": "BUY",
        "orderStatus": "TRANSIT",
        "tradingSymbol": "X",
        "quantity": 1,
    }
    order = _broker()._dhan_to_order(row)
    assert order.client_order_id == "555"


# ── fetch_instrument_dump (2026-08-26 fix: Dhan-only setups couldn't ───────
# resolve option strikes, since only zerodha.py had ever implemented this) ─

_REAL_HEADER = (
    "EXCH_ID,SEGMENT,SECURITY_ID,ISIN,INSTRUMENT,UNDERLYING_SECURITY_ID,UNDERLYING_SYMBOL,"
    "SYMBOL_NAME,DISPLAY_NAME,INSTRUMENT_TYPE,SERIES,LOT_SIZE,SM_EXPIRY_DATE,STRIKE_PRICE,"
    "OPTION_TYPE,TICK_SIZE,EXPIRY_FLAG,BRACKET_FLAG,COVER_FLAG,ASM_GSM_FLAG,ASM_GSM_CATEGORY,"
    "BUY_SELL_INDICATOR,BUY_CO_MIN_MARGIN_PER,BUY_CO_SL_RANGE_MAX_PERC,BUY_CO_SL_RANGE_MIN_PERC,"
    "BUY_BO_MIN_MARGIN_PER,BUY_BO_PROFIT_RANGE_MAX_PERC,BUY_BO_PROFIT_RANGE_MIN_PERC,MTF_LEVERAGE,"
    "SM_UPPER_LIMIT,SM_LOWER_LIMIT,SM_FREEZE_QTY,"
)
# Real NIFTY OPTIDX row, copied verbatim from a live fetch of
# images.dhan.co/api-data/api-scrip-master-detailed.csv (2026-08-26).
_REAL_NIFTY_CE_ROW = (
    "NSE,D,35084,NA,OPTIDX,26000,NIFTY,NIFTY-Sep2026-29150-CE,NIFTY 29 SEP 29150 CALL,OP,NA,65.0,"
    "2026-09-29,29150.00000,CE,5.0000,M,N,N,N,NA,A,0,0,0,0,0,0,0,20.1000,0.0500,1756,"
)
# A NIFTY future -- STRIKE_PRICE is a negative placeholder, not a real strike.
_REAL_NIFTY_FUT_ROW = (
    "NSE,D,49081,NA,FUTIDX,26000,NIFTY,NIFTY-Sep2026-FUT,NIFTY SEP FUT,FF,NA,65.0,"
    "2026-09-29,-0.01000,XX,0.0500,M,N,N,N,NA,A,0,0,0,0,0,0,0,26050.0000,20450.0000,1800,"
)
# An equity row -- should be filtered out (not F&O).
_REAL_EQUITY_ROW = (
    "NSE,E,11536,INE002A01018,EQUITY,NA,RELIANCE,RELIANCE,RELIANCE INDUSTRIES,ES,EQ,1.0,,,,"
    "0.0500,,N,N,N,NA,A,0,0,0,0,0,0,0,0,0,0,"
)


def _write_master(tmp_path, rows):
    p = tmp_path / "scrip_master.csv"
    p.write_text(_REAL_HEADER + "\n" + "\n".join(rows) + "\n")
    return p


@pytest.mark.asyncio
async def test_fetch_instrument_dump_parses_a_real_option_row(tmp_path, monkeypatch):
    master_path = _write_master(tmp_path, [_REAL_NIFTY_CE_ROW, _REAL_EQUITY_ROW])

    async def _fake_ensure(client):
        return master_path

    monkeypatch.setattr("brokers.dhan.ensure_scrip_master", _fake_ensure)

    broker = _broker()
    rows = await broker.fetch_instrument_dump(["NFO"])

    assert len(rows) == 1, "the equity row should have been filtered out"
    row = rows[0]
    assert row.tradingsymbol == "NIFTY-Sep2026-29150-CE", "must match what _resolve() looks up by"
    assert row.name == "NIFTY"
    assert row.exchange == "NFO"
    assert row.option_type == "CE"
    assert row.strike == Decimal("29150.00000")
    assert row.expiry.isoformat() == "2026-09-29"
    assert row.lot_size == 65
    assert row.instrument_token == 35084


@pytest.mark.asyncio
async def test_fetch_instrument_dump_future_has_no_strike_or_option_type(tmp_path, monkeypatch):
    master_path = _write_master(tmp_path, [_REAL_NIFTY_FUT_ROW])

    async def _fake_ensure(client):
        return master_path

    monkeypatch.setattr("brokers.dhan.ensure_scrip_master", _fake_ensure)

    broker = _broker()
    rows = await broker.fetch_instrument_dump(["NFO"])

    assert len(rows) == 1
    assert (
        rows[0].strike is None
    ), "STRIKE_PRICE is a negative placeholder for futures, not a real strike"
    assert rows[0].option_type is None
    assert rows[0].tradingsymbol == "NIFTY-Sep2026-FUT"


@pytest.mark.asyncio
async def test_fetch_instrument_dump_defaults_to_nfo_and_bfo(tmp_path, monkeypatch):
    master_path = _write_master(tmp_path, [_REAL_NIFTY_CE_ROW])

    async def _fake_ensure(client):
        return master_path

    monkeypatch.setattr("brokers.dhan.ensure_scrip_master", _fake_ensure)

    broker = _broker()
    rows = await broker.fetch_instrument_dump()  # no exchanges arg

    assert len(rows) == 1

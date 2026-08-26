"""Tests for core event types."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from xillion.core.events import (
    Bar,
    OrderRequest,
    OrderStatus,
    OrderType,
    Position,
    Side,
    Tick,
)


def test_tick_immutable():
    tick = Tick(symbol="NIFTY", ltp=Decimal("21000"), ltt=datetime.now(UTC))
    with pytest.raises(FrozenInstanceError):
        tick.ltp = Decimal("22000")  # type: ignore[misc]


def test_bar_immutable():
    bar = Bar(
        symbol="NIFTY",
        timeframe="5m",
        ts=datetime.now(UTC),
        open=Decimal("21000"),
        high=Decimal("21050"),
        low=Decimal("20990"),
        close=Decimal("21030"),
        volume=1000,
    )
    with pytest.raises(FrozenInstanceError):
        bar.close = Decimal("21100")  # type: ignore[misc]


def test_order_request_gets_unique_client_id():
    r1 = OrderRequest(symbol="NIFTY", side=Side.BUY, quantity=1, order_type=OrderType.MARKET)
    r2 = OrderRequest(symbol="NIFTY", side=Side.BUY, quantity=1, order_type=OrderType.MARKET)
    assert r1.client_order_id != r2.client_order_id


def test_side_values():
    assert Side.BUY == "BUY"
    assert Side.SELL == "SELL"


def test_order_status_values():
    assert OrderStatus.FILLED == "FILLED"
    assert OrderStatus.REJECTED == "REJECTED"


def test_position_mutable():
    pos = Position(
        symbol="NIFTY",
        quantity=10,
        avg_price=Decimal("21000"),
        realised_pnl=Decimal("0"),
        unrealised_pnl=Decimal("500"),
        last_price=Decimal("21050"),
    )
    pos.quantity = 5
    assert pos.quantity == 5

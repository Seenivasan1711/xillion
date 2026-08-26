"""
CP11 multi-leg position model: sizing arithmetic and leg-ordering discipline.
Sizing numbers are taken directly from docs/strategies/knowledge-base/
10-FIRST-STRATEGY-SPEC.md §7's worked example so a regression here is
immediately comparable to the spec's own table.
"""

from decimal import Decimal

import pytest

from xillion.core.events import OrderType, Side
from xillion.core.multileg import (
    Leg,
    LegRole,
    MultiLegSpec,
    StructureType,
    credit_adequate,
    max_loss_per_lot,
    order_entry_sequence,
    order_exit_sequence,
    size_defined_risk_position,
)


def _spread_spec(short_offset=None) -> MultiLegSpec:
    long_leg = Leg(
        symbol="NIFTY_LONG",
        exchange="NFO",
        role=LegRole.LONG,
        side=Side.BUY,
        quantity=65,
        order_type=OrderType.MARKET,
    )
    short_leg = Leg(
        symbol="NIFTY_SHORT",
        exchange="NFO",
        role=LegRole.SHORT,
        side=Side.SELL,
        quantity=65,
        order_type=OrderType.MARKET,
        protects_leg_index=1,
    )
    return MultiLegSpec(
        structure_type=StructureType.CREDIT_SPREAD,
        underlying="NIFTY",
        legs=[short_leg, long_leg],
        lot_size=65,  # deliberately out of order
        width=Decimal("50"),
        credit=Decimal("10"),
    )


def test_leg_index_assigned_by_position_in_list():
    spec = _spread_spec()
    assert spec.legs[0].symbol == "NIFTY_SHORT" and spec.legs[0].index == 0
    assert spec.legs[1].symbol == "NIFTY_LONG" and spec.legs[1].index == 1


def test_spec_rejects_short_leg_protecting_a_nonexistent_long():
    bad_short = Leg(
        symbol="X",
        exchange="NFO",
        role=LegRole.SHORT,
        side=Side.SELL,
        quantity=65,
        protects_leg_index=5,
    )
    with pytest.raises(ValueError):
        MultiLegSpec(
            structure_type=StructureType.CREDIT_SPREAD,
            underlying="NIFTY",
            legs=[bad_short],
            lot_size=65,
        )


def test_entry_sequence_puts_long_first_regardless_of_list_order():
    spec = _spread_spec()
    ordered = order_entry_sequence(spec)
    assert [leg.role for leg in ordered] == [LegRole.LONG, LegRole.SHORT]


def test_exit_sequence_puts_short_first():
    spec = _spread_spec()
    ordered = order_exit_sequence(spec)
    assert [leg.role for leg in ordered] == [LegRole.SHORT, LegRole.LONG]


# ── Sizing (KB 10 §7 worked example, Rs3,00,000 capital @ 1% risk) ─────────


def test_max_loss_per_lot_credit_spread_nifty_200_wide():
    loss = max_loss_per_lot(
        StructureType.CREDIT_SPREAD, 65, width=Decimal("200"), credit=Decimal("30")
    )
    assert loss == Decimal("11050")  # 170 * 65


def test_size_nifty_200_wide_is_zero_lots_too_big():
    loss = max_loss_per_lot(
        StructureType.CREDIT_SPREAD, 65, width=Decimal("200"), credit=Decimal("30")
    )
    decision = size_defined_risk_position(Decimal("300000"), Decimal("0.01"), loss)
    assert decision.lots == 0
    assert decision.reason is not None


def test_size_nifty_50_wide_is_one_lot():
    loss = max_loss_per_lot(
        StructureType.CREDIT_SPREAD, 65, width=Decimal("50"), credit=Decimal("10")
    )
    assert loss == Decimal("2600")  # 40 * 65
    decision = size_defined_risk_position(Decimal("300000"), Decimal("0.01"), loss)
    assert decision.lots == 1
    assert decision.max_loss_rupees == Decimal("2600")


def test_size_sensex_100_wide_is_one_lot():
    loss = max_loss_per_lot(
        StructureType.CREDIT_SPREAD, 20, width=Decimal("100"), credit=Decimal("18")
    )
    assert loss == Decimal("1640")  # 82 * 20
    decision = size_defined_risk_position(Decimal("300000"), Decimal("0.01"), loss)
    assert decision.lots == 1


def test_size_never_rounds_up():
    # risk budget just under one lot's max loss -- must floor to 0, not 1.
    decision = size_defined_risk_position(Decimal("100000"), Decimal("0.01"), Decimal("1001"))
    assert decision.lots == 0


def test_size_respects_max_lots_cap():
    decision = size_defined_risk_position(
        Decimal("10000000"), Decimal("0.01"), Decimal("100"), max_lots_cap=5
    )
    assert decision.lots == 5


def test_size_rejects_nonpositive_loss_per_lot():
    with pytest.raises(ValueError):
        size_defined_risk_position(Decimal("100000"), Decimal("0.01"), Decimal("0"))


def test_max_loss_per_lot_long_option_uses_debit():
    loss = max_loss_per_lot(StructureType.LONG_OPTION, 65, debit=Decimal("40"))
    assert loss == Decimal("2600")


def test_max_loss_per_lot_missing_args_raises():
    with pytest.raises(ValueError):
        max_loss_per_lot(StructureType.CREDIT_SPREAD, 65, width=Decimal("50"))


# ── Credit adequacy filter (KB 10 §5 Filter 4) ─────────────────────────────


def test_credit_adequate_passes_at_exactly_15_pct():
    assert credit_adequate(Decimal("15"), Decimal("100")) is True


def test_credit_adequate_fails_below_15_pct():
    assert credit_adequate(Decimal("14.99"), Decimal("100")) is False


def test_credit_adequate_zero_width_is_false():
    assert credit_adequate(Decimal("10"), Decimal("0")) is False

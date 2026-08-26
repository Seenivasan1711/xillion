"""
Multi-leg position model (CP11). A credit spread, iron condor, or butterfly is
one logical position spanning 2-4 broker orders -- Indian brokers have no
atomic multi-leg order type, so the framework has to hold that structure
together itself. See docs/architecture/automation-platform-spec/06-JOBS-ENTRY.md
E04/E05 for the spec this implements, and docs/strategies/knowledge-base/
10-FIRST-STRATEGY-SPEC.md §7 for the position-sizing arithmetic.

Pure data + arithmetic, no I/O -- execution lives in multileg_execution.py.
"""

import math
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from xillion.core.events import OrderType, Side


class LegRole(StrEnum):
    """LONG = the protective/risk-defining leg (bought). SHORT = the
    premium-collecting leg (sold), which is only ever acceptable to hold
    while its protecting LONG leg is also held."""

    LONG = "LONG"
    SHORT = "SHORT"


class StructureType(StrEnum):
    CREDIT_SPREAD = "CREDIT_SPREAD"
    IRON_CONDOR = "IRON_CONDOR"
    IRON_FLY = "IRON_FLY"
    BUTTERFLY = "BUTTERFLY"
    LONG_OPTION = "LONG_OPTION"
    CALENDAR = "CALENDAR"


DEFINED_RISK_STRUCTURES = {
    StructureType.CREDIT_SPREAD,
    StructureType.IRON_CONDOR,
    StructureType.IRON_FLY,
    StructureType.BUTTERFLY,
    StructureType.CALENDAR,
}


@dataclass
class Leg:
    """One leg of a multi-leg structure. `index` is this leg's position in
    the owning MultiLegSpec.legs list -- `protects_leg_index` (SHORT legs
    only) points at the LONG leg index that caps this leg's risk, so the
    leg-failure protocol (multileg_execution.py) can tell a "naked short"
    apart from "fully hedged" without hardcoding a 2-leg assumption."""

    symbol: str
    exchange: str
    role: LegRole
    side: Side
    quantity: int  # contracts = lots * lot_size
    order_type: OrderType = OrderType.MARKET
    price: Decimal | None = None
    index: int = 0
    protects_leg_index: int | None = None


@dataclass
class MultiLegSpec:
    """One logical position. `credit` is net premium received (positive for
    a credit structure); `width` is the strike distance between the short
    and its protecting long, in the underlying's points -- both are per-lot,
    lot_size already applied by the caller when comparing to rupee amounts."""

    structure_type: StructureType
    underlying: str
    legs: list[Leg]
    lot_size: int
    width: Decimal | None = None
    credit: Decimal | None = None
    debit: Decimal | None = None
    expiry: str | None = None  # ISO date, for time-stop checks
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        for i, leg in enumerate(self.legs):
            leg.index = i
        long_indices = {leg.index for leg in self.legs if leg.role == LegRole.LONG}
        for leg in self.legs:
            if leg.role == LegRole.SHORT and leg.protects_leg_index is not None:
                if leg.protects_leg_index not in long_indices:
                    raise ValueError(
                        f"leg {leg.index} ({leg.symbol}) claims protects_leg_index="
                        f"{leg.protects_leg_index}, but that index is not a LONG leg"
                    )


def order_entry_sequence(spec: MultiLegSpec) -> list[Leg]:
    """Longs first on entry -- the long leg caps the risk, so it must exist
    before the short leg that creates exposure. Stable within each role so a
    caller's own leg ordering (e.g. put side before call side) is preserved."""
    return sorted(spec.legs, key=lambda leg: 0 if leg.role == LegRole.LONG else 1)


def order_exit_sequence(spec: MultiLegSpec) -> list[Leg]:
    """Shorts first on exit -- closing the short leg first removes the
    unbounded-risk side immediately; the long leg can safely close last
    since holding it alone is never dangerous (bounded loss, if anything
    extra optionality)."""
    return sorted(spec.legs, key=lambda leg: 0 if leg.role == LegRole.SHORT else 1)


def max_loss_per_lot(
    structure_type: StructureType,
    lot_size: int,
    *,
    width: Decimal | None = None,
    credit: Decimal | None = None,
    debit: Decimal | None = None,
) -> Decimal:
    """docs/strategies/knowledge-base/10-FIRST-STRATEGY-SPEC.md §7 /
    automation-platform-spec/06-JOBS-ENTRY.md E03. DEFINED risk only --
    UNDEFINED-risk structures (naked options) have no max loss and are out
    of scope for this sizing function by design (see 07-RANKED-LOW-RISK-
    HIGH-WIN.md's excluded-by-risk-gate list)."""
    if structure_type in (
        StructureType.CREDIT_SPREAD,
        StructureType.IRON_CONDOR,
        StructureType.IRON_FLY,
    ):
        if width is None or credit is None:
            raise ValueError(f"{structure_type} requires width and credit")
        return (width - credit) * lot_size
    if structure_type in (
        StructureType.LONG_OPTION,
        StructureType.BUTTERFLY,
        StructureType.CALENDAR,
    ):
        if debit is None:
            raise ValueError(f"{structure_type} requires debit")
        return debit * lot_size
    raise ValueError(f"max_loss_per_lot: unsupported structure {structure_type}")


@dataclass
class SizeDecision:
    lots: int
    max_loss_rupees: Decimal
    reason: str | None = None  # set when lots == 0


def size_defined_risk_position(
    capital: Decimal,
    risk_pct: Decimal,
    loss_per_lot: Decimal,
    *,
    max_lots_cap: int | None = None,
) -> SizeDecision:
    """lots = floor(risk_pct * capital / max_loss_per_lot); lots < 1 -> skip,
    never round up (KB 10 §7 -- this exact rule is why most Nifty spreads
    don't fit at <=Rs3L capital and Sensex/the butterfly get recommended
    instead). risk_pct is a fraction (0.01 = 1%), not a percentage."""
    if loss_per_lot <= 0:
        raise ValueError(f"loss_per_lot must be positive, got {loss_per_lot}")
    risk_rupees = capital * risk_pct
    lots = math.floor(risk_rupees / loss_per_lot)
    if max_lots_cap is not None:
        lots = min(lots, max_lots_cap)
    if lots < 1:
        return SizeDecision(
            lots=0,
            max_loss_rupees=Decimal("0"),
            reason=(
                f"POSITION_TOO_LARGE_FOR_ACCOUNT: risk budget Rs{risk_rupees} < "
                f"max loss/lot Rs{loss_per_lot} -- narrow the width, switch to a "
                "smaller-lot instrument (e.g. Sensex vs Nifty), or skip"
            ),
        )
    return SizeDecision(lots=lots, max_loss_rupees=Decimal(lots) * loss_per_lot)


def credit_adequate(credit: Decimal, width: Decimal, min_pct: Decimal = Decimal("0.15")) -> bool:
    """KB 10 §5 Filter 4: require credit >= 15% of spread width. If the
    market won't pay that, the risk/reward isn't there."""
    if width <= 0:
        return False
    return credit >= width * min_pct

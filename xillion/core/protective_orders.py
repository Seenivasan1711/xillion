"""
Protective-order levels (CP11 / automation-platform-spec E07). "No position
exists unprotected" -- a stop/target has to become a real, monitored level
the moment a position opens, not just strategy logic that might re-evaluate
next bar.

Scope note (honest, not a shortcut): no broker plugin in this codebase wires
a real bracket-order or GTT construction path today (Zerodha's
`supports_bracket_orders` capability flag exists but nothing in the
execution path builds a bracket order request yet -- see
xillion/core/broker_base.py). So every structure here takes the spec's own
documented fallback: a SOFTWARE stop, monitored every tick by the strategy
that opened the position, which places a REAL market order through the
normal multi-leg exit path the moment it triggers. This is correct per
06-JOBS-ENTRY.md E07's own ELSE branch, not a simplification of it.

The spec's own caveat applies: a software stop needs the process alive to
fire. A background watchdog that survives a strategy crash is CP12's
trailing-stop engine (K03-equivalent) -- this module only computes levels
and evaluates triggers; wiring an always-on monitor independent of the
strategy's own on_tick loop is explicitly out of scope here.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from xillion.core.multileg import StructureType


@dataclass(frozen=True)
class ProtectiveOrderSpec:
    """Structure-dependent stop/target, computed once at fill time from the
    real average entry price (not the pre-trade estimate)."""
    stop_value: Decimal      # trigger when the monitored value crosses this, in the "bad" direction
    target_value: Optional[Decimal] = None
    time_stop_date: Optional[date] = None  # exit regardless, once reached (e.g. 1 DTE)
    reference_credit: Optional[Decimal] = None  # for logging/journal only


def credit_spread_protective_levels(
    entry_credit: Decimal,
    *,
    target_pct_of_credit: Decimal = Decimal("0.50"),
    stop_multiple_of_credit: Decimal = Decimal("2.0"),
    time_stop_date: Optional[date] = None,
) -> ProtectiveOrderSpec:
    """KB 10-FIRST-STRATEGY-SPEC.md §6: stop on SPREAD VALUE, e.g. 2x credit
    received (= a loss equal to 100% of the credit); target on spread value
    decaying to (1 - target_pct) of the entry credit (e.g. 50% of credit
    captured). `spread_value` = cost to buy the structure back = what you'd
    pay to close it -- it starts at entry_credit and should decay toward 0
    as the short option's extrinsic value decays."""
    if entry_credit <= 0:
        raise ValueError(f"entry_credit must be positive, got {entry_credit}")
    stop_value = entry_credit * stop_multiple_of_credit
    target_value = entry_credit * (Decimal("1") - target_pct_of_credit)
    return ProtectiveOrderSpec(
        stop_value=stop_value,
        target_value=target_value,
        time_stop_date=time_stop_date,
        reference_credit=entry_credit,
    )


def spread_value(short_leg_ltp: Decimal, long_leg_ltp: Decimal) -> Decimal:
    """Current cost to close a 2-leg credit spread: buy back the short,
    sell the long. Both LTPs are per-unit option premiums."""
    return short_leg_ltp - long_leg_ltp


def check_exit_trigger(
    spec: ProtectiveOrderSpec,
    current_value: Decimal,
    current_date: date,
) -> Optional[str]:
    """Returns "STOP" | "TARGET" | "TIME_STOP" | None. Time stop is checked
    first -- an expiry-day gamma exit takes priority over a target that
    happens to be sitting right at the boundary. For a credit spread,
    current_value RISING past stop_value is bad (you're now paying more to
    close than you collected); current_value FALLING to/below target_value
    is good (most of the credit has decayed away)."""
    if spec.time_stop_date is not None and current_date >= spec.time_stop_date:
        return "TIME_STOP"
    if current_value >= spec.stop_value:
        return "STOP"
    if spec.target_value is not None and current_value <= spec.target_value:
        return "TARGET"
    return None


def is_defined_risk(structure_type: StructureType) -> bool:
    from xillion.core.multileg import DEFINED_RISK_STRUCTURES
    return structure_type in DEFINED_RISK_STRUCTURES

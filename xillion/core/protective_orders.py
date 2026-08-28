"""
Protective-order levels (CP11 / automation-platform-spec E07). "No position
exists unprotected" -- a stop/target has to become a real, monitored level
the moment a position opens, not just strategy logic that might re-evaluate
next bar.

The primary mechanism is still a SOFTWARE stop: monitored every tick by the
strategy that opened the position, which places a REAL market order through
the normal multi-leg exit path the moment it triggers (06-JOBS-ENTRY.md
E07's own ELSE branch). The spec's own caveat applies -- a software stop
needs the process alive to fire, so it's not a full substitute for a
broker-side order the exchange itself enforces.

**Follow-up, 2026-08-25: a broker-native backstop now exists alongside it,
not instead of it.** Zerodha's Kite Connect discontinued bracket orders
entirely (confirmed against current API docs -- `supports_bracket_orders`
now correctly reads False for Zerodha, see xillion/core/broker_base.py),
but GTT triggers are still real and supported --
Broker.place_protective_gtt()/cancel_gtt(). Strategies that want this call
short_leg_gtt_levels() below and StrategyContext.place_protective_gtt()
after entry fills. **This is a real, honest approximation, not an exact
mirror of the software stop:** Kite's GTT triggers on ONE instrument's own
LTP, but the software stop here triggers on `spread_value` (short leg LTP
minus long leg LTP) -- there's no way to express a two-leg net condition as
a single-instrument broker trigger. short_leg_gtt_levels() converts the
spread-value threshold into an approximate short-leg-only price by holding
the long leg's price fixed at its entry fill -- correct at the moment of
entry, increasingly approximate as the long leg's own price moves. It's a
genuine circuit-breaker for the worst case (process down, software stop
can't fire at all), not a precision replacement for the tick-driven
spread-value check that remains the primary, more accurate protection.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from xillion.core.multileg import StructureType


@dataclass(frozen=True)
class ProtectiveOrderSpec:
    """Structure-dependent stop/target, computed once at fill time from the
    real average entry price (not the pre-trade estimate)."""

    stop_value: Decimal  # trigger when the monitored value crosses this, in the "bad" direction
    target_value: Decimal | None = None
    time_stop_date: date | None = None  # exit regardless, once reached (e.g. 1 DTE)
    reference_credit: Decimal | None = None  # for logging/journal only


def credit_spread_protective_levels(
    entry_credit: Decimal,
    *,
    target_pct_of_credit: Decimal = Decimal("0.50"),
    stop_multiple_of_credit: Decimal = Decimal("2.0"),
    time_stop_date: date | None = None,
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


def short_leg_gtt_levels(
    long_entry_price: Decimal,
    spec: ProtectiveOrderSpec,
) -> tuple[Decimal, Decimal | None]:
    """Converts a spread-value-based ProtectiveOrderSpec into an
    approximate (short-leg-price-only) stop/target pair for a broker-native
    GTT -- see this module's docstring for why it's approximate, not exact.
    spread_value = short_ltp - long_ltp, so holding long_ltp fixed at its
    entry fill: short_ltp = long_entry_price + spread_value_threshold."""
    stop_price = long_entry_price + spec.stop_value
    target_price = long_entry_price + spec.target_value if spec.target_value is not None else None
    return stop_price, target_price


def spread_value(short_leg_ltp: Decimal, long_leg_ltp: Decimal) -> Decimal:
    """Current cost to close a 2-leg credit spread: buy back the short,
    sell the long. Both LTPs are per-unit option premiums."""
    return short_leg_ltp - long_leg_ltp


def condor_value(
    short_call_ltp: Decimal,
    long_call_ltp: Decimal,
    short_put_ltp: Decimal,
    long_put_ltp: Decimal,
) -> Decimal:
    """Current cost to close an iron condor (KB 03 A1): the call-side
    spread and the put-side spread close independently, so this is just
    spread_value() applied to each pair and summed -- there's no cross-term
    between the two. `credit_spread_protective_levels()`/`check_exit_trigger()`
    downstream don't care how this number was computed, only that it starts
    at the entry credit and decays toward 0 as both sides' extrinsic value
    decays, same as a 2-leg spread's spread_value()."""
    return spread_value(short_call_ltp, long_call_ltp) + spread_value(short_put_ltp, long_put_ltp)


def check_exit_trigger(
    spec: ProtectiveOrderSpec,
    current_value: Decimal,
    current_date: date,
) -> str | None:
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

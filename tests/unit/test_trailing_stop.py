"""
CP12 trailing-stop algorithms. The ratchet property test is this
checkpoint's own Verify line: "the stop never loosens across 1000+
randomised price paths" -- implemented with the stdlib `random` module
(seeded, so failures reproduce) rather than adding a `hypothesis`
dependency for one property, matching this codebase's minimal-dependency
convention elsewhere.
"""
import random
from decimal import Decimal

import pytest

from xillion.core.trailing_stop import (
    R_LADDER, TrailDirection, TrailState, apply_breakeven_shift, apply_trail,
    breakeven_shift, credit_trail, fixed_trail, observe_price, r_ladder_trail, ratchet,
)


def _long_state(entry=100, stop=90, hwm=100, risk=10) -> TrailState:
    return TrailState(
        direction=TrailDirection.LONG, entry_price=Decimal(str(entry)),
        stop=Decimal(str(stop)), high_water_mark=Decimal(str(hwm)),
        low_water_mark=Decimal(str(entry)), initial_risk_per_unit=Decimal(str(risk)),
    )


def _short_state(entry=100, stop=110, lwm=100, risk=10) -> TrailState:
    return TrailState(
        direction=TrailDirection.SHORT, entry_price=Decimal(str(entry)),
        stop=Decimal(str(stop)), high_water_mark=Decimal(str(entry)),
        low_water_mark=Decimal(str(lwm)), initial_risk_per_unit=Decimal(str(risk)),
    )


# ── ratchet() -- the enforcement point ──────────────────────────────────────

def test_ratchet_long_takes_the_higher_value():
    assert ratchet(TrailDirection.LONG, Decimal("90"), Decimal("95")) == Decimal("95")
    assert ratchet(TrailDirection.LONG, Decimal("90"), Decimal("85")) == Decimal("90")  # rejected


def test_ratchet_short_takes_the_lower_value():
    assert ratchet(TrailDirection.SHORT, Decimal("110"), Decimal("105")) == Decimal("105")
    assert ratchet(TrailDirection.SHORT, Decimal("110"), Decimal("115")) == Decimal("110")  # rejected


def test_ratchet_property_stop_never_loosens_across_1000_random_paths():
    """The checkpoint's own Verify line. For both directions, feed 1000
    independent random price paths through fixed_trail and assert the stop
    is monotonic (non-decreasing for LONG, non-increasing for SHORT) at
    every single step, not just at the end."""
    rng = random.Random(20260825)  # fixed seed -- a failure here reproduces
    for direction in (TrailDirection.LONG, TrailDirection.SHORT):
        for _path in range(1000):
            state = (
                _long_state(entry=100, stop=90, hwm=100)
                if direction == TrailDirection.LONG
                else _short_state(entry=100, stop=110, lwm=100)
            )
            prev_stop = state.stop
            for _step in range(30):
                price = Decimal(str(rng.uniform(50, 150)))
                state = observe_price(state, price)
                candidate = fixed_trail(state, Decimal("5"))
                state = apply_trail(state, candidate)
                if direction == TrailDirection.LONG:
                    assert state.stop >= prev_stop, "LONG stop loosened"
                else:
                    assert state.stop <= prev_stop, "SHORT stop loosened"
                prev_stop = state.stop


# ── fixed_trail ──────────────────────────────────────────────────────────

def test_fixed_trail_long_trails_below_high_water_mark():
    state = _long_state(entry=100, stop=90, hwm=120)
    candidate = fixed_trail(state, Decimal("5"))
    assert candidate == Decimal("115")


def test_fixed_trail_never_produces_a_candidate_below_current_stop_after_ratchet():
    state = _long_state(entry=100, stop=90, hwm=92)  # barely above entry
    candidate = fixed_trail(state, Decimal("10"))  # would be 82, below current stop 90
    assert candidate == Decimal("90")  # ratchet rejected it


# ── r_ladder_trail ───────────────────────────────────────────────────────

def test_r_ladder_moves_to_breakeven_at_1r():
    state = _long_state(entry=100, stop=90, hwm=110, risk=10)  # +1.0R exactly
    candidate = r_ladder_trail(state)
    assert candidate == Decimal("100")  # locked_r=0.0 -> entry_price


def test_r_ladder_locks_partial_profit_at_2r():
    state = _long_state(entry=100, stop=90, hwm=120, risk=10)  # +2.0R
    candidate = r_ladder_trail(state)
    assert candidate == Decimal("110")  # entry + 1.0 * risk


def test_r_ladder_leaves_stop_untouched_below_first_rung():
    state = _long_state(entry=100, stop=90, hwm=105, risk=10)  # +0.5R
    candidate = r_ladder_trail(state)
    assert candidate == Decimal("90")


def test_r_ladder_short_direction():
    state = _short_state(entry=100, stop=110, lwm=80, risk=10)  # +2.0R
    candidate = r_ladder_trail(state)
    assert candidate == Decimal("90")  # entry - 1.0*risk


# ── credit_trail (credit-spread structure, CP11 integration point) ────────

def test_credit_trail_does_nothing_below_capture_threshold():
    state = _short_state(entry=25, stop=50, lwm=25, risk=25)  # stop = 2x credit
    # Only 30% captured -- below the 50% default threshold.
    candidate = credit_trail(state, credit_received=Decimal("25"), current_spread_value=Decimal("17.5"))
    assert candidate == state.stop


def test_credit_trail_tightens_past_capture_threshold():
    state = _short_state(entry=25, stop=50, lwm=25, risk=25)
    # 60% captured (spread value fallen from 25 to 10).
    candidate = credit_trail(state, credit_received=Decimal("25"), current_spread_value=Decimal("10"))
    # captured=0.6, candidate_value = 25*(1-0.6*0.5) = 25*0.7 = 17.5 -- tighter than 50.
    assert candidate == Decimal("17.5")


def test_credit_trail_never_loosens_even_if_spread_value_bounces_back_up():
    state = _short_state(entry=25, stop=17.5, lwm=25, risk=25)  # already tightened once
    # Spread value bounced back up (captured% dropped) -- ratchet must hold.
    candidate = credit_trail(state, credit_received=Decimal("25"), current_spread_value=Decimal("15"))
    assert candidate == Decimal("17.5")  # unchanged, not loosened


def test_credit_trail_zero_credit_is_a_noop():
    state = _short_state(entry=0, stop=0, lwm=0, risk=1)
    assert credit_trail(state, credit_received=Decimal("0"), current_spread_value=Decimal("5")) == state.stop


# ── breakeven_shift (T05) ────────────────────────────────────────────────

def test_breakeven_shift_fires_at_trigger_r():
    state = _long_state(entry=100, stop=90, hwm=110, risk=10)  # exactly +1.0R
    candidate = breakeven_shift(state)
    assert candidate == Decimal("100")


def test_breakeven_shift_returns_none_below_trigger():
    state = _long_state(entry=100, stop=90, hwm=105, risk=10)  # +0.5R
    assert breakeven_shift(state) is None


def test_breakeven_shift_returns_none_once_already_moved():
    state = TrailState(
        direction=TrailDirection.LONG, entry_price=Decimal("100"), stop=Decimal("100"),
        high_water_mark=Decimal("130"), low_water_mark=Decimal("100"),
        initial_risk_per_unit=Decimal("10"), breakeven_moved=True,
    )
    assert breakeven_shift(state) is None


def test_apply_breakeven_shift_sets_the_flag():
    state = _long_state(entry=100, stop=90, hwm=110, risk=10)
    new_state = apply_breakeven_shift(state)
    assert new_state.stop == Decimal("100")
    assert new_state.breakeven_moved is True
    # Calling again must not move it further even if price keeps rising.
    new_state2 = apply_breakeven_shift(observe_price(new_state, Decimal("200")))
    assert new_state2.stop == Decimal("100")


# ── apply_trail min_stop_move ───────────────────────────────────────────

def test_apply_trail_skips_small_moves():
    state = _long_state(entry=100, stop=90, hwm=100)
    result = apply_trail(state, Decimal("90.5"), min_stop_move=Decimal("1"))
    assert result.stop == Decimal("90")  # unchanged -- move was < min_stop_move


def test_apply_trail_applies_moves_past_the_threshold():
    state = _long_state(entry=100, stop=90, hwm=100)
    result = apply_trail(state, Decimal("95"), min_stop_move=Decimal("1"))
    assert result.stop == Decimal("95")


def test_r_multiple_zero_when_no_initial_risk():
    state = _long_state(entry=100, stop=90, hwm=120, risk=0)
    assert state.r_multiple == Decimal("0")

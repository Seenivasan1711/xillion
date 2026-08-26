"""
Trailing-stop algorithms (CP12 / automation-platform-spec T03 + T05). Two
rules govern everything here, quoted directly from
docs/architecture/automation-platform-spec/07-JOBS-INTRADE.md T03:

  (1) A trailing stop only ever moves in the favourable direction. It never
      loosens.
  (2) What you trail ON depends on the structure -- trailing an options
      credit spread on the underlying's price is a category error. A credit
      spread trails on its own net spread value (see credit_trail below and
      xillion/core/protective_orders.py's spread_value()), never spot.

Pure functions + dataclasses, no I/O -- persistence (the actual "survives a
restart" half of CP12's watchdog-gap-closing) is StrategyContext.state,
which now round-trips through StrategyInstance.state_blob (see
xillion/engine/strategy_engine.py) rather than resetting to {} on every
spawn as it silently did before this checkpoint.
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum


class TrailDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class TrailState:
    """Everything a trailing algorithm needs, and nothing it can mutate in
    place -- every update returns a NEW TrailState (frozen), so "did the
    stop change" is always an explicit comparison, never an accidental
    in-place edit that could bypass the ratchet."""

    direction: TrailDirection
    entry_price: Decimal
    stop: Decimal
    high_water_mark: Decimal  # best price seen so far, LONG-relevant
    low_water_mark: Decimal  # best price seen so far, SHORT-relevant
    initial_risk_per_unit: Decimal  # |entry_price - initial_stop|, for R-multiple calcs
    breakeven_moved: bool = False

    @property
    def r_multiple(self) -> Decimal:
        if self.initial_risk_per_unit <= 0:
            return Decimal("0")
        if self.direction == TrailDirection.LONG:
            move = self.high_water_mark - self.entry_price
        else:
            move = self.entry_price - self.low_water_mark
        return move / self.initial_risk_per_unit


def ratchet(direction: TrailDirection, current_stop: Decimal, candidate: Decimal) -> Decimal:
    """The only way a stop is ever written. A LONG stop can only move up; a
    SHORT stop can only move down. Called by every algorithm below, and
    safe to call again on an already-ratcheted value (idempotent)."""
    if direction == TrailDirection.LONG:
        return max(current_stop, candidate)
    return min(current_stop, candidate)


def observe_price(state: TrailState, price: Decimal) -> TrailState:
    """Update the water marks for a new price tick/bar close -- call this
    BEFORE running a trailing algorithm off high_water_mark/low_water_mark,
    since the algorithms themselves don't see raw prices."""
    return replace(
        state,
        high_water_mark=max(state.high_water_mark, price),
        low_water_mark=min(state.low_water_mark, price),
    )


# ── Algorithms (each returns a candidate stop; caller applies ratchet) ─────
# automation-platform-spec 07-JOBS-INTRADE.md §3.2 lists six; these three
# cover the cases this codebase actually has strategies for today (a fixed
# trail as the generic baseline, the spec's own "recommended default"
# R-multiple ladder, and the credit-spread-specific trail CP11's protective
# orders needs). ATR/chandelier and swing-structure trails need bar history
# + indicators this module doesn't otherwise depend on -- a natural next
# addition, not required for "at least one algorithm" (this checkpoint's
# own Verify line).


def fixed_trail(state: TrailState, trail_amount: Decimal) -> Decimal:
    """Algorithm 1 (spec §3.2.1): trail a fixed distance behind the best
    price seen. Simplest, most broadly applicable -- works for any
    price-quoted instrument (directional futures, XAUUSD, long options on
    premium)."""
    if state.direction == TrailDirection.LONG:
        candidate = state.high_water_mark - trail_amount
    else:
        candidate = state.low_water_mark + trail_amount
    return ratchet(state.direction, state.stop, candidate)


# Spec's own "recommended default" -- discrete, auditable, easy to backtest.
R_LADDER: list[tuple[Decimal, Decimal]] = [
    (Decimal("1.0"), Decimal("0.0")),  # at +1.0R -> stop to breakeven
    (Decimal("1.5"), Decimal("0.5")),  # at +1.5R -> lock +0.5R
    (Decimal("2.0"), Decimal("1.0")),  # at +2.0R -> lock +1.0R
    (Decimal("3.0"), Decimal("2.0")),  # at +3.0R -> lock +2.0R
]


def r_ladder_trail(state: TrailState, ladder: list[tuple[Decimal, Decimal]] = R_LADDER) -> Decimal:
    """Algorithm 4 (spec §3.2.4, "recommended default"): stop moves in
    discrete steps as R-multiple profit accrues, rather than continuously."""
    locked: Decimal | None = None
    for trigger_r, lock_r in ladder:
        if state.r_multiple >= trigger_r:
            locked = lock_r
    if locked is None:
        return state.stop  # not yet triggered -- leave the initial stop alone
    sign = Decimal("1") if state.direction == TrailDirection.LONG else Decimal("-1")
    candidate = state.entry_price + (locked * state.initial_risk_per_unit * sign)
    return ratchet(state.direction, state.stop, candidate)


def credit_trail(
    state: TrailState,
    credit_received: Decimal,
    current_spread_value: Decimal,
    lock_ratio: Decimal = Decimal("0.5"),
    capture_threshold: Decimal = Decimal("0.5"),
) -> Decimal:
    """Algorithm 6 (spec §3.2.6): the credit-spread-specific trail. Trails
    on how much of the collected credit has been captured, NOT on the
    underlying's price (spec's own explicit warning, §3.1: trailing a
    credit spread on spot is a category error). Once `capture_threshold`
    (default 50%) of the credit is captured, tighten the stop so a full
    reversal back to the original loss can't happen. `state.direction` is
    conceptually SHORT here -- the position is short the spread's value,
    profiting as spread_value falls, so the stop ratchets DOWNWARD as more
    credit is captured, same as any other SHORT trail."""
    if credit_received <= 0:
        return state.stop
    captured = (credit_received - current_spread_value) / credit_received
    if captured < capture_threshold:
        return state.stop
    candidate_value = credit_received * (Decimal("1") - captured * lock_ratio)
    return ratchet(TrailDirection.SHORT, state.stop, candidate_value)


def breakeven_shift(
    state: TrailState,
    trigger_r: Decimal = Decimal("1.0"),
    buffer: Decimal = Decimal("0"),
) -> Decimal | None:
    """T05 -- fires once, separate from T03 because its semantics differ
    (a threshold crossing, not a continuous trail). `buffer` should cover
    round-trip cost so "breakeven" is truly zero, not a small guaranteed
    loss. Returns None if not yet triggered or already moved -- callers
    should treat None as "no update", never as "move to zero"."""
    if state.breakeven_moved or state.r_multiple < trigger_r:
        return None
    sign = Decimal("1") if state.direction == TrailDirection.LONG else Decimal("-1")
    candidate = state.entry_price + (buffer * sign)
    return ratchet(state.direction, state.stop, candidate)


def apply_trail(
    state: TrailState, candidate: Decimal, min_stop_move: Decimal = Decimal("0")
) -> TrailState:
    """Spec §3.3 step 3: skip the update unless it moves by more than
    min_stop_move (prevents order-modify spam / OPS burn on a noisy price
    series). Always applies the ratchet regardless of min_stop_move, so a
    caller can't accidentally loosen a stop by passing a bad candidate."""
    ratcheted = ratchet(state.direction, state.stop, candidate)
    if abs(ratcheted - state.stop) < min_stop_move:
        return state
    return replace(state, stop=ratcheted)


def apply_breakeven_shift(
    state: TrailState,
    trigger_r: Decimal = Decimal("1.0"),
    buffer: Decimal = Decimal("0"),
) -> TrailState:
    candidate = breakeven_shift(state, trigger_r, buffer)
    if candidate is None:
        return state
    return replace(state, stop=candidate, breakeven_moved=True)

"""
Signed-quantity position arithmetic, shared by the live engine and the
backtest engine.

This exists because the two engines had drifted: the live path
(strategy_engine.py) handled shorts and average-in correctly, while the
backtest path tracked only longs and silently dropped short sells. Any
divergence here means a strategy backtests differently from how it trades,
which is the worst class of bug in this system -- so both now call the same
function.

Conventions:
  - `qty` is SIGNED: positive = long, negative = short.
  - `multiplier` is the contract/lot multiplier (NIFTY options = 65, FX lots
    = 100_000, cash equity = 1). P&L is always scaled by it; getting this
    wrong misprices every derivative trade by the lot size.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from xillion.core.events import Side
from xillion.engine.metrics import ClosedTrade


@dataclass
class PositionState:
    """Net position in one symbol. qty is signed; qty == 0 means flat."""

    qty: int = 0
    avg_price: Decimal = Decimal("0")
    realised_pnl: Decimal = Decimal("0")
    opened_ts: datetime | None = None

    @property
    def is_flat(self) -> bool:
        return self.qty == 0

    @property
    def direction(self) -> int:
        """+1 long, -1 short, 0 flat."""
        if self.qty > 0:
            return 1
        if self.qty < 0:
            return -1
        return 0


@dataclass
class FillOutcome:
    """Result of applying one fill: the new state, plus a ClosedTrade if this
    fill closed (fully or partially) an existing position."""

    state: PositionState
    closed_trade: ClosedTrade | None = None
    realised_pnl: Decimal = Decimal("0")


def apply_fill(
    state: PositionState | None,
    symbol: str,
    side: Side,
    quantity: int,
    price: Decimal,
    ts: datetime,
    *,
    multiplier: int = 1,
    tag: str = "",
) -> FillOutcome:
    """Apply one fill to a position, returning the new state and any closed trade.

    Handles all four cases: open, average-in, reduce, and reverse.
    """
    if quantity <= 0:
        raise ValueError(f"fill quantity must be positive, got {quantity}")

    qty_delta = quantity if side == Side.BUY else -quantity
    mult = Decimal(str(multiplier))

    # ── Open a new position ────────────────────────────────────────────────
    if state is None or state.qty == 0:
        return FillOutcome(
            state=PositionState(
                qty=qty_delta,
                avg_price=price,
                realised_pnl=state.realised_pnl if state else Decimal("0"),
                opened_ts=ts,
            )
        )

    # ── Add to the same direction — average in ─────────────────────────────
    if state.qty * qty_delta > 0:
        total_qty = state.qty + qty_delta
        state.avg_price = (state.avg_price * abs(state.qty) + price * abs(qty_delta)) / abs(
            total_qty
        )
        state.qty = total_qty
        return FillOutcome(state=state)

    # ── Reduce or reverse ──────────────────────────────────────────────────
    closed_qty = min(abs(state.qty), abs(qty_delta))
    direction = state.direction
    entry_price = state.avg_price
    entry_ts = state.opened_ts

    pnl = (price - entry_price) * closed_qty * direction * mult
    state.realised_pnl += pnl

    remaining = state.qty + qty_delta
    state.qty = remaining

    if remaining == 0:
        state.avg_price = Decimal("0")
        state.opened_ts = None
    elif remaining * direction < 0:
        # Reversed through zero: the leftover is a NEW position in the
        # opposite direction, so it must be repriced at this fill. The live
        # engine used to leave the old avg_price here, which mispriced every
        # subsequent P&L calculation on a reversal.
        state.avg_price = price
        state.opened_ts = ts
    # else: partial reduce — avg_price of the remainder is unchanged

    return FillOutcome(
        state=state,
        realised_pnl=pnl,
        closed_trade=ClosedTrade(
            pnl=float(pnl),
            entry_price=float(entry_price),
            exit_price=float(price),
            quantity=int(closed_qty),
            symbol=symbol,
            side="LONG" if direction == 1 else "SHORT",
            entry_ts=entry_ts,
            exit_ts=ts,
            tag=tag,
        ),
    )

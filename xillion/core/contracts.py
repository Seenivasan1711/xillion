"""
Contract specifications — the multiplier ("lot size", "point value",
"contract size") that converts a price move into money.

This is not cosmetic. NIFTY options trade in lots of 65, so a 1-point move on
one lot is worth ₹65, not ₹1. Without a multiplier every derivative backtest
understates P&L by the lot size. The same applies to futures (point value) and
FX (lot size, typically 100_000 units of base currency).

Cash equity is the only asset class where multiplier == 1, which is why this
went unnoticed while only spot strategies were being tested.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    multiplier: int = 1
    tick_size: Decimal = Decimal("0.05")
    instrument_type: str = "equity"   # equity | future | option | forex | crypto
    currency: str = "INR"


#: Used when a symbol can't be resolved. Deliberately 1 (not a guess) so that
#: an unresolved symbol produces obviously-unscaled numbers rather than
#: plausible-but-wrong ones.
DEFAULT_SPEC = ContractSpec(symbol="", multiplier=1)


def spec_from_instrument_row(row) -> ContractSpec:
    """Build a ContractSpec from a cached `instrument` row (see
    xillion/core/instruments.py::InstrumentRow or the Instrument ORM model).
    Both expose .tradingsymbol / .lot_size / .tick_size / .segment."""
    segment = (getattr(row, "segment", "") or "").upper()
    if getattr(row, "option_type", None):
        instrument_type = "option"
    elif "FUT" in segment:
        instrument_type = "future"
    else:
        instrument_type = "equity"

    lot_size = getattr(row, "lot_size", 1) or 1
    tick = getattr(row, "tick_size", None)
    return ContractSpec(
        symbol=row.tradingsymbol,
        multiplier=int(lot_size),
        tick_size=Decimal(str(tick)) if tick else Decimal("0.05"),
        instrument_type=instrument_type,
    )


def resolve_specs(
    symbols: Iterable[str],
    instrument_rows: Optional[Iterable] = None,
) -> dict[str, ContractSpec]:
    """Map symbols → ContractSpec using cached instrument rows where available.

    Symbols with no matching row fall back to multiplier 1. Callers running
    derivative backtests should ensure the instrument cache is populated
    (see xillion/core/instrument_cache.py) or pass specs explicitly.
    """
    by_symbol: dict[str, ContractSpec] = {}
    if instrument_rows:
        for row in instrument_rows:
            try:
                spec = spec_from_instrument_row(row)
            except Exception:
                continue
            by_symbol[spec.symbol] = spec

    return {
        sym: by_symbol.get(sym, ContractSpec(symbol=sym, multiplier=1))
        for sym in symbols
    }

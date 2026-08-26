"""
Options instrument resolution: turns "ATM call, this week's expiry" into a
concrete tradable instrument. Expiry and strike-ladder logic is entirely
driven by the instrument dump actually present -- never a hardcoded weekday
or strike interval, since SEBI's 2024-25 rationalization already changed
weekly-expiry rules once (Nifty/Sensex weekly only, everything else monthly)
and could again. Pure logic, no I/O -- callers supply the dump as data.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


class ExpirySelectionError(ValueError):
    """An expiry selector doesn't match reality for the underlying -- e.g.
    "this_week" requested for an underlying that only has monthly expiries."""


class StrikeResolutionError(ValueError):
    """No instrument row matches the resolved (underlying, expiry,
    option_type, strike) tuple."""


@dataclass(frozen=True)
class InstrumentRow:
    """One row from a broker's instrument dump."""

    instrument_token: int
    exchange: str
    tradingsymbol: str
    name: str  # underlying, e.g. "NIFTY"
    expiry: date | None
    strike: Decimal | None
    option_type: str | None  # "CE" | "PE"
    segment: str
    lot_size: int
    tick_size: Decimal


@dataclass(frozen=True)
class ResolvedInstrument:
    tradingsymbol: str
    instrument_token: int
    exchange: str
    underlying: str
    expiry: date
    strike: Decimal
    option_type: str
    lot_size: int


_WEEKLY_SELECTORS = {"this_week", "next_week"}
_MONTHLY_SELECTORS = {"this_month", "next_month"}
# If the nearest future expiry is farther out than this, the underlying isn't
# actually weekly -- reject rather than silently treat a monthly as a weekly.
_WEEKLY_MAX_DAYS_OUT = 10


def select_expiry(
    rows: Sequence[InstrumentRow],
    underlying: str,
    selector: str,
    as_of: date,
) -> date:
    """Pick a concrete expiry date for `underlying` from the dump."""
    if selector not in _WEEKLY_SELECTORS | _MONTHLY_SELECTORS:
        raise ValueError(f"unknown expiry selector: {selector!r}")

    expiries = sorted(
        {
            r.expiry
            for r in rows
            if r.name == underlying and r.expiry is not None and r.expiry >= as_of
        }
    )
    if not expiries:
        raise ExpirySelectionError(
            f"no future expiries found for {underlying!r} in the instrument dump"
        )

    if selector in _WEEKLY_SELECTORS:
        nth = 0 if selector == "this_week" else 1
        if len(expiries) <= nth:
            raise ExpirySelectionError(
                f"{selector!r} requested for {underlying!r} but only "
                f"{len(expiries)} future expiry(ies) exist"
            )
        candidate = expiries[nth]
        days_out = (candidate - as_of).days
        if days_out > _WEEKLY_MAX_DAYS_OUT:
            raise ExpirySelectionError(
                f"{selector!r} requested for {underlying!r}, but its nearest "
                f"expiry ({candidate}) is {days_out} days out -- this "
                "underlying looks monthly-only, not weekly. Use "
                "'this_month'/'next_month' instead."
            )
        return candidate

    # Monthly selectors: last expiry within the target calendar month.
    target_month_offset = 0 if selector == "this_month" else 1
    target_year = as_of.year
    target_month = as_of.month + target_month_offset
    if target_month > 12:
        target_month -= 12
        target_year += 1

    month_expiries = [e for e in expiries if e.year == target_year and e.month == target_month]
    if month_expiries:
        return month_expiries[-1]

    # "this_month" but that month's own expiry has already passed (as_of is
    # past it) -- the caller's intent ("current/nearest monthly contract") is
    # still satisfiable by falling back to the nearest future expiry.
    if selector == "this_month":
        return expiries[0]

    raise ExpirySelectionError(
        f"no expiry found for {underlying!r} in target month {target_year}-{target_month:02d}"
    )


def nearest_strike(spot: Decimal, strikes: Sequence[Decimal], offset: int) -> Decimal:
    """ATM (offset=0) or N-strikes ITM/OTM (offset != 0), walking the actual
    strike ladder present in the dump -- strike gaps differ per underlying,
    never assume a fixed interval."""
    if not strikes:
        raise StrikeResolutionError("no strikes available to resolve against")
    ladder = sorted(set(strikes))
    atm_index = min(range(len(ladder)), key=lambda i: abs(ladder[i] - spot))
    target_index = atm_index + offset
    if not (0 <= target_index < len(ladder)):
        raise StrikeResolutionError(
            f"strike offset {offset} from ATM ({ladder[atm_index]}) is out of "
            f"range for the {len(ladder)}-strike ladder available"
        )
    return ladder[target_index]


def resolve_option(
    rows: Sequence[InstrumentRow],
    underlying: str,
    selector: str,
    strike_offset: int,
    option_type: str,
    spot_price: Decimal,
    as_of: date | None = None,
) -> ResolvedInstrument:
    """Resolve an "N-strikes-from-ATM call/put, this week's/month's expiry"
    request into a concrete, currently-listed instrument."""
    if option_type not in ("CE", "PE"):
        raise ValueError(f"option_type must be 'CE' or 'PE', got {option_type!r}")

    as_of = as_of if as_of is not None else date.today()
    expiry = select_expiry(rows, underlying, selector, as_of)

    candidates = [
        r
        for r in rows
        if r.name == underlying and r.expiry == expiry and r.option_type == option_type
    ]
    if not candidates:
        raise StrikeResolutionError(
            f"no {option_type} instruments found for {underlying!r} expiry {expiry}"
        )

    strikes = [r.strike for r in candidates if r.strike is not None]
    strike = nearest_strike(spot_price, strikes, strike_offset)

    match = next((r for r in candidates if r.strike == strike), None)
    if match is None:
        raise StrikeResolutionError(
            f"resolved strike {strike} not found among {underlying!r} "
            f"{option_type} instruments for expiry {expiry}"
        )

    return ResolvedInstrument(
        tradingsymbol=match.tradingsymbol,
        instrument_token=match.instrument_token,
        exchange=match.exchange,
        underlying=underlying,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        lot_size=match.lot_size,
    )
